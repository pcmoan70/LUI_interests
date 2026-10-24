"""Scrape Cristin API v2: LUI persons, their results, contributors, and OsloMet projects."""
from __future__ import annotations

import json

from ..db import connect, init_db, run_log, since_date, upsert
from ..http import Fetcher

API = "https://api.cristin.no/v2"
INST = "215"
FACULTY = "215.4.0.0"

CATEGORY_GROUP = {
    "ARTICLE": "article", "ARTICLEJOURNAL": "article", "ACADEMICREVIEW": "article",
    "ARTICLEFEATURE": "popular", "ARTICLEPOPULAR": "popular", "POPULARARTICLE": "popular",
    "CHAPTERACADEMIC": "chapter", "CHAPTER": "chapter", "CHAPTERARTICLE": "chapter",
    "MONOGRAPHACA": "monograph", "ANTHOLOGYACA": "monograph", "COMMENTARYACA": "monograph",
    "DOCTORALTHESIS": "phd", "THESISMASTER": "thesis", "THESISSECOND": "thesis",
    "REPORT": "report", "ACADEMICLECTURE": "lecture", "LECTURE": "lecture", "POSTER": "lecture",
    "LECTUREPOPULAR": "lecture", "OTHERPRES": "lecture",
    "TEXTBOOK": "textbook", "NONFICTIONBOOK": "textbook", "COMPENDIUM": "textbook",
    "POPULARBOOK": "popular", "MEDIAINTERVIEW": "media", "PROGRAMPARTICIPATION": "media",
    "PROGRAMMANAGEMENT": "media", "INTERVIEW": "media", "WRITTENINTERVIEW": "media",
    "READERADVICE": "media", "CHRONICLE": "popular", "EDITORIAL": "popular",
    "ARTICLELETTER": "popular", "ABSTRACT": "lecture", "DATASET": "other",
    "OTHER": "other", "ARCHITECTEXHIBIT": "other", "MUSICALPERFORMANCE": "other",
}
CORE_GROUPS = {"article", "chapter", "monograph", "phd", "report"}
WEIGHTS = {"article": 1.0, "chapter": 0.9, "monograph": 1.2, "phd": 1.2, "report": 0.7,
           "thesis": 0.3, "lecture": 0.3, "textbook": 0.5, "popular": 0.2, "media": 0.05, "other": 0.1}


LANG = {"nob": "nb", "nno": "nn", "nor": "no", "eng": "en", "swe": "sv", "dan": "da", "ger": "de", "deu": "de",
        "fra": "fr", "fre": "fr", "spa": "es", "mul": "mul", "und": None, "": None}


def norm_lang(code: str | None) -> str | None:
    if not code:
        return None
    c = code.lower().rsplit("/", 1)[-1]
    return LANG.get(c, c[:2] if len(c) <= 3 else None)


def norm_year(y) -> int | None:
    try:
        y = int(y)
    except (TypeError, ValueError):
        return None
    return y if 1900 <= y <= 2035 else None


def lang_text(d: dict | None) -> tuple[str | None, str | None]:
    """Pick (lang, text) from a Cristin {lang: text} map, preferring nb, en, nn."""
    if not d:
        return None, None
    for k in ("nb", "no", "en", "nn"):
        if d.get(k):
            return k, d[k]
    k, v = next(iter(d.items()))
    return k, v


def paged(f: Fetcher, url: str, key: str, per_page: int = 100):
    page = 1
    while True:
        data = f.get_json(f"{url}&per_page={per_page}&page={page}", key=f"{key}_p{page:03d}")
        if not data or isinstance(data, dict):
            break
        yield from data
        if len(data) < per_page:
            break
        page += 1


def store_result(con, r: dict) -> str:
    rid = r["cristin_result_id"]
    cat = (r.get("category") or {}).get("code", "OTHER")
    grp = CATEGORY_GROUP.get(cat, "other")
    links = {l["url_type"]: l["url"] for l in r.get("links", [])}
    doi = links.get("DOI")
    if doi:
        doi = doi.lower().replace("https://doi.org/", "").replace("http://doi.org/", "").replace("http://dx.doi.org/", "")
    _, title = lang_text(r.get("title"))
    journal = r.get("journal") or {}
    publisher = r.get("publisher") or {}
    slang, summary = lang_text(r.get("summary"))
    is_core = int(grp in CORE_GROUPS or (grp == "lecture" and bool(summary)))
    upsert(con, "publication", {
        "pub_id": rid, "cristin_result_id": rid, "nva_id": r.get("nva_result_id"), "doi": doi,
        "handle": links.get("ARKIV"), "title": title, "year": norm_year(r.get("year_published")),
        "language": norm_lang(r.get("original_language")), "category_code": cat, "category_group": grp,
        "venue_name": journal.get("name") or publisher.get("name"), "venue_id": journal.get("cristin_journal_id"),
        "nvi_level": journal.get("nvi_level") or publisher.get("nvi_level"),
        "is_core": is_core, "weight": WEIGHTS.get(grp, 0.1),
        "n_authors": (r.get("contributors") or {}).get("count"),
    }, keys=["pub_id"])
    if summary:
        upsert(con, "publication_text", {"pub_id": rid, "kind": "abstract", "source": "cristin", "lang": slang,
                                         "text": summary, "char_count": len(summary)})
    return rid


def store_contributors(con, rid: str, contribs: list[dict]) -> None:
    for c in contribs:
        affs = c.get("affiliations") or []
        units = [a.get("unit", {}).get("cristin_unit_id") for a in affs if a.get("unit")]
        internal = int(any(u and u.startswith("215.") for u in units))
        upsert(con, "publication_author", {
            "pub_id": rid, "author_order": c.get("order"), "cristin_person_id": c.get("cristin_person_id"),
            "name_raw": f"{c.get('surname','')}, {c.get('first_name','')}".strip(", "),
            "affiliation_unit_id": next((u for u in units if u and u.startswith("215.")), units[0] if units else None),
            "is_internal": internal,
        }, keys=["pub_id", "author_order"])


def update_modified(con, f: Fetcher, since: str, lui_ids: set[str]) -> tuple[int, int]:
    """What's new: results and projects modified in Cristin since `since` (YYYY-MM-DD). Contributor lists of
    modified results are replaced, so author changes and affiliation corrections are picked up."""
    n_res = n_proj = 0
    for r in paged(f, f"{API}/results?unit={FACULTY}&modified_since={since}&fields=all", f"results_modified_{since}", per_page=500):
        rid = r["cristin_result_id"]
        contribs = f.get_json(f"{API}/results/{rid}/contributors", key=f"contrib_{rid}", force=True)
        store_result(con, r)
        if isinstance(contribs, list):
            con.execute("DELETE FROM publication_author WHERE pub_id=?", (rid,))
            store_contributors(con, rid, contribs)
        con.commit()
        n_res += 1
    for pr in paged(f, f"{API}/projects?institution={INST}&modified_since={since}", f"projects_modified_{since}", per_page=500):
        cid = pr["cristin_project_id"]
        d = f.get_json(f"{API}/projects/{cid}", key=f"project_{cid}", force=True) or {}
        coord = (d.get("coordinating_institution") or {}).get("unit", {}).get("cristin_unit_id", "")
        if coord.startswith("215.4") or any(x.get("cristin_person_id") in lui_ids for x in d.get("participants", [])):
            n_proj += 1
    return n_res, n_proj


def run(refresh=False, max_age=30, limit=None, fresh=(), since=None) -> None:
    init_db()
    con = connect()
    f = Fetcher("cristin", max_age_days=max_age, refresh=refresh, fresh=fresh)
    since = since_date(con, "scrape-cristin", since)

    with run_log(con, "scrape-cristin") as log:
        persons = list(paged(f, f"{API}/persons?institution={INST}&parent_unit_id={FACULTY}", "persons_lui"))
        # staff listed under LUI on the web but registered elsewhere in Cristin (config/identity_overrides.csv)
        import csv
        from ..paths import CONFIG_DIR
        ov = CONFIG_DIR / "identity_overrides.csv"
        if ov.exists():
            known = {p["cristin_person_id"] for p in persons}
            for row in csv.DictReader(ov.open(encoding="utf-8")):
                cid = (row.get("cristin_person_id") or "").strip()
                if cid and cid not in known:
                    persons.append({"cristin_person_id": cid, "url": f"{API}/persons/{cid}"})
        print(f"cristin persons in LUI: {len(persons)}", flush=True)
        if limit:
            persons = persons[:limit]

        seen_results: set[str] = set()
        for i, p in enumerate(persons, 1):
            pid = p["cristin_person_id"]
            d = f.get_json(f"{API}/persons/{pid}", key=f"person_{pid}") or {}
            active = [a for a in d.get("affiliations", []) if a.get("active") and a.get("unit", {}).get("cristin_unit_id", "").startswith("215.4")]
            aff = active[0] if active else next((a for a in d.get("affiliations", []) if a.get("unit", {}).get("cristin_unit_id", "").startswith("215.4")), None)
            results = list(paged(f, f"{API}/persons/{pid}/results?fields=all", f"results_{pid}", per_page=500))
            upsert(con, "cristin_person", {
                "cristin_person_id": pid, "first_name": d.get("first_name", p.get("first_name")),
                "surname": d.get("surname", p.get("surname")), "orcid": (d.get("orcid") or {}).get("id"),
                "email": (d.get("email") or "").lower() or None,
                "background": lang_text(d.get("background"))[1],
                "keywords_json": json.dumps([lang_text(k.get("name"))[1] for k in d.get("keywords", [])], ensure_ascii=False),
                "affiliations_json": json.dumps(d.get("affiliations", []), ensure_ascii=False),
                "unit_id": aff["unit"]["cristin_unit_id"] if aff else None,
                "position": lang_text(aff.get("position")) [1] if aff else None,
                "active": int(bool(active)), "n_results": len(results),
            }, keys=["cristin_person_id"])
            for r in results:
                rid = r["cristin_result_id"]
                contribs = None
                if rid not in seen_results:
                    seen_results.add(rid)
                    contribs = f.get_json(f"{API}/results/{rid}/contributors", key=f"contrib_{rid}")
                store_result(con, r)
                if isinstance(contribs, list):
                    store_contributors(con, rid, contribs)
                con.commit()
            con.commit()
            if i % 10 == 0:
                print(f"  persons {i}/{len(persons)}  results so far {len(seen_results)}  ({f.stats()})", flush=True)
        con.commit()
        if since:
            n_res, n_proj = update_modified(con, f, since, {p["cristin_person_id"] for p in persons})
            print(f"modified since {since}: {n_res} results, {n_proj} LUI projects", flush=True)

        # projects: all OsloMet projects, keep those with a LUI participant or coordinator
        projects = list(paged(f, f"{API}/projects?institution={INST}", "projects_oslomet", per_page=500))
        print(f"oslomet projects: {len(projects)}", flush=True)
        kept = 0
        lui_ids = {p["cristin_person_id"] for p in persons}
        for pr in projects[: (limit * 5 if limit else None)]:
            cid = pr["cristin_project_id"]
            d = f.get_json(f"{API}/projects/{cid}", key=f"project_{cid}") or {}
            parts = d.get("participants", [])
            coord = (d.get("coordinating_institution") or {}).get("unit", {}).get("cristin_unit_id", "")
            if not (coord.startswith("215.4") or any(x.get("cristin_person_id") in lui_ids for x in parts)):
                continue
            kept += 1
            t = d.get("title") or {}
            upsert(con, "project", {
                "project_id": f"cristin:{cid}", "cristin_project_id": cid,
                "title_nb": t.get("nb") or t.get("no") or t.get("nn"), "title_en": t.get("en"),
                "summary": lang_text(d.get("academic_summary") or d.get("popular_scientific_summary"))[1],
                "start_date": d.get("start_date"), "end_date": d.get("end_date"), "status": d.get("status"),
                "coordinating_unit_id": coord or None, "url": f"https://app.cristin.no/projects/show.jsf?id={cid}",
            }, keys=["project_id"])
            for x in parts:
                upsert(con, "project_participant", {
                    "project_id": f"cristin:{cid}", "cristin_person_id": x.get("cristin_person_id"),
                    "name_raw": f"{x.get('surname','')}, {x.get('first_name','')}".strip(", "),
                    "role": ",".join(r.get("role_code", "") for r in x.get("roles", [])) or "participant",
                })
            for k in d.get("keywords", []):
                kw = lang_text(k.get("name"))[1]
                if kw:
                    upsert(con, "project_keyword", {"project_id": f"cristin:{cid}", "keyword": kw})
            con.commit()
        con.commit()
        log["rows"] = len(seen_results)
        log["notes"] = f"{len(persons)} persons, {len(seen_results)} results, {kept} projects; {f.stats()}"
    print("done:", log["notes"])
