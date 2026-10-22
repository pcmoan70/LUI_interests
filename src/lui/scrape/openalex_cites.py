"""Fetch the works that cite our OpenAlex-indexed publications and classify each citation by the
citing authors' institutions: lui / oslomet / norway / international / unknown (plus our own db id)."""
from __future__ import annotations

import json

from ..db import connect, init_db, run_log
from ..http import Fetcher

API = "https://api.openalex.org"
MAILTO = "pcmoan@gmail.com"
OSLOMET = "I184531372"


def ensure_table(con) -> None:
    con.execute("""CREATE TABLE IF NOT EXISTS citing_work (
        cited_pub_id TEXT, citing_work_id TEXT, citing_pub_id TEXT, scope TEXT, countries_json TEXT, institutions_json TEXT, year INTEGER,
        PRIMARY KEY (cited_pub_id, citing_work_id))""")
    con.execute("CREATE INDEX IF NOT EXISTS ix_citing_cited ON citing_work(cited_pub_id)")


def classify(w: dict, ours: dict[str, str]) -> tuple[str, list, list, str | None]:
    wid = w["id"].rsplit("/", 1)[-1]
    inst_ids, countries, names = set(), [], []
    for a in w.get("authorships") or []:
        for i in a.get("institutions") or []:
            iid = (i.get("id") or "").rsplit("/", 1)[-1]
            if iid:
                inst_ids.add(iid); names.append(i.get("display_name"))
            if i.get("country_code"):
                countries.append(i["country_code"])
    if wid in ours:
        scope = "lui"
    elif OSLOMET in inst_ids:
        scope = "oslomet"
    elif countries and all(c == "NO" for c in countries):
        scope = "norway"
    elif countries:
        scope = "international" if any(c != "NO" for c in countries) else "norway"
    else:
        scope = "unknown"
    return scope, sorted(set(countries)), sorted(set(n for n in names if n))[:8], ours.get(wid)


def run(refresh=False, max_age=30, limit=None) -> None:
    init_db()
    con = connect()
    ensure_table(con)
    f = Fetcher("openalex", max_age_days=max_age, refresh=refresh)
    ours = dict(con.execute("SELECT openalex_work_id, pub_id FROM publication WHERE openalex_work_id IS NOT NULL"))
    todo = [(w, p) for w, p in con.execute("SELECT openalex_work_id, pub_id FROM publication WHERE openalex_work_id IS NOT NULL AND COALESCE(cited_by_count,0) > 0")]
    if limit:
        todo = todo[:limit]
    print(f"citing works for {len(todo)} cited publications", flush=True)
    n_rows = 0
    with run_log(con, "scrape-openalex-cites") as log:
        for i, (wid, pub_id) in enumerate(todo, 1):
            cursor = "*"; page = 0
            while cursor:
                url = f"{API}/works?filter=cites:{wid}&select=id,publication_year,authorships&per-page=200&cursor={cursor}&mailto={MAILTO}"
                d = f.get_json(url, key=f"cites_{wid}_{page}")
                if not d:
                    break
                for w in d.get("results", []):
                    scope, countries, names, our_pid = classify(w, ours)
                    con.execute("INSERT OR REPLACE INTO citing_work VALUES (?,?,?,?,?,?,?)",
                                (pub_id, w["id"].rsplit("/", 1)[-1], our_pid, scope, json.dumps(countries), json.dumps(names, ensure_ascii=False), w.get("publication_year")))
                    n_rows += 1
                cursor = (d.get("meta") or {}).get("next_cursor") if len(d.get("results", [])) == 200 else None
                page += 1
            con.commit()
            if i % 200 == 0:
                print(f"  {i}/{len(todo)} cited works, {n_rows} citations ({f.stats()})", flush=True)
        log["rows"] = n_rows
        log["notes"] = f"{len(todo)} cited works; {n_rows} citing works; {f.stats()}"
    print("done:", log["notes"])
