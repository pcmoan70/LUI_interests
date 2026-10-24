"""Enrich publications with OpenAlex: topics, keywords, abstracts, references, citations, OA pdf links."""
from __future__ import annotations

import json
from urllib.parse import quote

from ..db import connect, init_db, run_log, upsert
from ..http import Fetcher
from ..identity import tokens

API = "https://api.openalex.org"
MAILTO = "pcmoan@gmail.com"
SELECT = ",".join(["id", "doi", "title", "publication_year", "language", "cited_by_count", "fwci",
                   "referenced_works", "topics", "keywords", "authorships", "best_oa_location",
                   "abstract_inverted_index", "open_access"])


def abstract_from_index(inv: dict | None) -> str | None:
    if not inv:
        return None
    pos = sorted((p, w) for w, ps in inv.items() for p in ps)
    return " ".join(w for _, w in pos) or None


def store_work(con, w: dict, pub_id: str, name_to_person: dict[str, list[str]]) -> None:
    wid = w["id"].rsplit("/", 1)[-1]
    con.execute("UPDATE publication SET openalex_work_id=?, cited_by_count=?, fwci=? WHERE pub_id=?",
                (wid, w.get("cited_by_count"), w.get("fwci"), pub_id))
    for t in w.get("topics") or []:
        upsert(con, "openalex_topic", {
            "pub_id": pub_id, "topic_id": t["id"].rsplit("/", 1)[-1], "topic_name": t["display_name"],
            "subfield": (t.get("subfield") or {}).get("display_name"), "field": (t.get("field") or {}).get("display_name"),
            "domain": (t.get("domain") or {}).get("display_name"), "score": t.get("score")}, keys=["pub_id", "topic_id"])
    for k in w.get("keywords") or []:
        upsert(con, "publication_keyword", {"pub_id": pub_id, "keyword": k["display_name"], "source": "openalex",
                                            "score": k.get("score")}, keys=["pub_id", "keyword", "source"])
    has_abs = con.execute("SELECT 1 FROM publication_text WHERE pub_id=? AND kind='abstract'", (pub_id,)).fetchone()
    abs_txt = abstract_from_index(w.get("abstract_inverted_index"))
    if abs_txt and not has_abs:
        upsert(con, "publication_text", {"pub_id": pub_id, "kind": "abstract", "source": "openalex", "lang": w.get("language"),
                                         "text": abs_txt, "char_count": len(abs_txt)})
    for ref in w.get("referenced_works") or []:
        con.execute("INSERT OR IGNORE INTO openalex_ref(work_id, ref_work_id) VALUES (?,?)", (wid, ref.rsplit("/", 1)[-1]))
    loc = w.get("best_oa_location") or {}
    if loc.get("pdf_url"):
        upsert(con, "publication_file", {"pub_id": pub_id, "file_id": "openalex_oa", "source": "openalex",
                                         "url": loc["pdf_url"], "licence": loc.get("license"), "mime": "application/pdf"},
               keys=["pub_id", "file_id"])
    # map OpenAlex author ids onto our internal authors by surname
    for a in w.get("authorships") or []:
        au = a.get("author") or {}
        if not au.get("id"):
            continue
        inst_ids = {i.get("id", "").rsplit("/", 1)[-1] for i in a.get("institutions") or []}
        if "I184531372" not in inst_ids:
            continue
        toks = tokens(au.get("display_name"))
        if not toks:
            continue
        row = con.execute("""SELECT pa.author_order, pa.person_id FROM publication_author pa WHERE pa.pub_id=? AND pa.person_id IS NOT NULL""",
                          (pub_id,)).fetchall()
        for order, person_id in row:
            pn = con.execute("SELECT name_last, name_first FROM person WHERE person_id=?", (person_id,)).fetchone()
            if pn and tokens(pn[0]) and tokens(pn[0])[-1] == toks[-1] and (not tokens(pn[1]) or tokens(pn[1])[0] == toks[0]):
                con.execute("UPDATE publication_author SET openalex_author_id=? WHERE pub_id=? AND author_order=?",
                            (au.get("id", "").rsplit("/", 1)[-1], pub_id, order))
                name_to_person.setdefault(person_id, []).append(au.get("id", "").rsplit("/", 1)[-1])
                if au.get("orcid"):
                    con.execute("UPDATE person SET orcid=COALESCE(orcid,?) WHERE person_id=?",
                                (au["orcid"].rsplit("/", 1)[-1], person_id))


def run(refresh=False, max_age=30, limit=None, fresh=()) -> None:
    init_db()
    con = connect()
    f = Fetcher("openalex", max_age_days=max_age, refresh=refresh, fresh=fresh)
    # OpenAlex offers "updated since" only on paid plans, so our diff is the citation count: works whose
    # cited_by_count changed since the last run are queued for a fresh download of their citing works.
    con.execute("CREATE TABLE IF NOT EXISTS cite_refresh_queue (work_id TEXT PRIMARY KEY, queued_at TEXT)")
    old_counts = dict(con.execute("SELECT openalex_work_id, COALESCE(cited_by_count,0) FROM publication WHERE openalex_work_id IS NOT NULL"))
    rows = con.execute("SELECT pub_id, doi FROM publication WHERE doi IS NOT NULL AND doi NOT LIKE '%,%' AND doi NOT LIKE '%|%'").fetchall()
    if limit:
        rows = rows[:limit]
    by_doi = {d.lower(): p for p, d in rows}
    dois = sorted(by_doi)
    print(f"openalex: {len(dois)} DOIs", flush=True)
    name_to_person: dict[str, list[str]] = {}
    found = 0
    with run_log(con, "scrape-openalex") as log:
        for i in range(0, len(dois), 50):
            batch = dois[i:i + 50]
            flt = "|".join(quote(d, safe="") for d in batch)
            url = f"{API}/works?filter=doi:{flt}&per-page=50&select={SELECT}&mailto={MAILTO}"
            d = f.get_json(url, key=f"works_batch_{i // 50:05d}_{len(dois)}")
            for w in (d or {}).get("results", []):
                doi = (w.get("doi") or "").lower().replace("https://doi.org/", "")
                pub_id = by_doi.get(doi)
                if pub_id:
                    store_work(con, w, pub_id, name_to_person)
                    found += 1
            con.commit()
            if (i // 50) % 10 == 0:
                print(f"  batches {i // 50 + 1}/{(len(dois) + 49) // 50}, found {found}  ({f.stats()})", flush=True)
        # person-level OpenAlex author id = most frequent id seen on their papers
        for person_id, ids in name_to_person.items():
            best = max(set(ids), key=ids.count)
            con.execute("UPDATE person SET openalex_author_id=? WHERE person_id=?", (best, person_id))
        # internal citations
        con.execute("DELETE FROM citation WHERE source='openalex'")
        con.execute("""INSERT OR IGNORE INTO citation(citing_pub_id, cited_pub_id, source)
                       SELECT a.pub_id, b.pub_id, 'openalex' FROM openalex_ref r
                       JOIN publication a ON a.openalex_work_id=r.work_id
                       JOIN publication b ON b.openalex_work_id=r.ref_work_id""")
        con.commit()
        n_cit = con.execute("SELECT COUNT(*) FROM citation").fetchone()[0]
        changed = [(w,) for w, n in con.execute("SELECT openalex_work_id, COALESCE(cited_by_count,0) FROM publication WHERE openalex_work_id IS NOT NULL")
                   if n > 0 and n != old_counts.get(w, 0)]
        from datetime import date
        con.executemany("INSERT OR IGNORE INTO cite_refresh_queue VALUES (?, ?)", [(w, date.today().isoformat()) for (w,) in changed])
        con.commit()
        log["rows"] = found
        log["notes"] = f"{found}/{len(dois)} DOIs found in OpenAlex; {n_cit} internal citations; {len(changed)} works with changed citation count queued; {f.stats()}"
    print("done:", log["notes"])
