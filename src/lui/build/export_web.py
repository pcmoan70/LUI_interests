"""Export JSON bundles for the static web app (web/data/*.json). Never exports e-mail or full text."""
from __future__ import annotations

import json
import shutil
from collections import defaultdict
from datetime import date

from ..db import connect
from ..paths import DERIVED_DIR, WEB_DATA_DIR


def dump(name: str, obj) -> None:
    WEB_DATA_DIR.mkdir(parents=True, exist_ok=True)
    p = WEB_DATA_DIR / name
    p.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"  {name:14s} {p.stat().st_size / 1e6:6.2f} MB")


def run(refresh=False, max_age=None, limit=None) -> None:
    con = connect()
    units = {r["unit_id"]: dict(r) for r in con.execute("SELECT * FROM unit")}

    # ---- topics / taxonomy
    macro = [dict(r) for r in con.execute("SELECT * FROM macro_topic ORDER BY macro_id")]
    topics = [dict(r) for r in con.execute("SELECT topic_id, slug, label_nb, label_en, definition_nb, definition_en, macro_id, keywords_json FROM topic ORDER BY macro_id, topic_id")]
    for t in topics:
        t["keywords"] = json.loads(t.pop("keywords_json") or "[]")
    theories = [dict(r) for r in con.execute("SELECT theory_id, label FROM theory ORDER BY label")]
    methods = [dict(r) for r in con.execute("SELECT method_id, label FROM method ORDER BY label")]
    topic_counts = defaultdict(lambda: {"n_pubs": 0, "n_persons": 0})
    for t, n in con.execute("SELECT topic_id, COUNT(*) FROM pub_topic GROUP BY 1"):
        topic_counts[t]["n_pubs"] = n
    for t, n in con.execute("SELECT topic_id, COUNT(*) FROM person_topic WHERE score>=0.05 GROUP BY 1"):
        topic_counts[t]["n_persons"] = n
    for t in topics:
        t.update(topic_counts[t["topic_id"]])

    # ---- persons
    person_topics = defaultdict(list)
    for p, t, s, n, prim in con.execute("SELECT person_id, topic_id, score, n_pubs, is_primary FROM person_topic ORDER BY score DESC"):
        person_topics[p].append({"t": t, "s": round(s, 3), "n": n, "p": prim})
    person_theories = defaultdict(list)
    for p, t, s in con.execute("SELECT person_id, theory_id, score FROM person_theory ORDER BY score DESC"):
        person_theories[p].append({"t": t, "s": round(s, 3)})
    person_methods = defaultdict(list)
    for p, t, s in con.execute("SELECT person_id, method_id, score FROM person_method ORDER BY score DESC"):
        person_methods[p].append({"t": t, "s": round(s, 3)})
    person_kw = defaultdict(list)
    for p, k in con.execute("SELECT person_id, keyword FROM person_keyword"):
        person_kw[p].append(k)
    person_groups = defaultdict(list)
    for g, p, role in con.execute("SELECT group_id, person_id, role FROM group_member WHERE person_id IS NOT NULL"):
        person_groups[p].append({"g": g, "r": role})
    person_projects = defaultdict(list)
    for prj, p, role in con.execute("SELECT project_id, person_id, role FROM project_participant WHERE person_id IS NOT NULL"):
        person_projects[p].append({"p": prj, "r": role})
    n_pubs = dict(con.execute("SELECT person_id, COUNT(*) FROM publication_author WHERE person_id IS NOT NULL GROUP BY 1"))
    n_core = dict(con.execute("""SELECT pa.person_id, COUNT(*) FROM publication_author pa JOIN publication p ON p.pub_id=pa.pub_id
                                 WHERE pa.person_id IS NOT NULL AND p.is_core=1 GROUP BY 1"""))
    years = {r[0]: (r[1], r[2]) for r in con.execute("""SELECT pa.person_id, MIN(p.year), MAX(p.year) FROM publication_author pa
                                 JOIN publication p ON p.pub_id=pa.pub_id WHERE pa.person_id IS NOT NULL GROUP BY 1""")}
    yrs_core = defaultdict(set); yrs_all = defaultdict(set)
    for pid_, y, core in con.execute("""SELECT pa.person_id, p.year, p.is_core FROM publication_author pa JOIN publication p ON p.pub_id=pa.pub_id
                                        WHERE pa.person_id IS NOT NULL AND p.year IS NOT NULL"""):
        yrs_all[pid_].add(y)
        if core:
            yrs_core[pid_].add(y)
    collab = {}
    if con.execute("SELECT 1 FROM sqlite_master WHERE name='person_collab'").fetchone():
        for r in con.execute("SELECT * FROM person_collab"):
            collab[r["person_id"]] = {"n": [r["n_pubs"], r["n_solo"], r["n_lui"], r["n_oslomet"], r["n_norway"], r["n_international"], r["n_unknown"]],
                                      "r": [r["r_pubs"], r["r_solo"], r["r_lui"], r["r_oslomet"], r["r_norway"], r["r_international"]],
                                      "countries": json.loads(r["countries_json"] or "[]"), "insts": json.loads(r["institutions_json"] or "[]"),
                                      "partners": [r["partners_lui"], r["partners_ext"]], "cites": [r["cites_total"], r["cites_internal"], r["cites_external"]]}
    persons = []
    for r in con.execute("SELECT * FROM person"):
        pid = r["person_id"]
        bio = r["bio_nb"] or r["bio_en"] or r["cristin_background"]
        lui = r["is_listed"] or r["resolved_by"] == "cristin_only"
        if not lui:   # external coauthor: few attributes, short topic list
            persons.append({"id": pid, "name": r["name_full"], "type": r["staff_type"], "listed": 0, "unit": r["unit_id"],
                            "unitShort": (units.get(r["unit_id"]) or {}).get("short_code"), "orcid": r["orcid"], "cristin": r["cristin_person_id"],
                            "nPubs": n_pubs.get(pid, 0), "nCore": n_core.get(pid, 0), "years": years.get(pid),
                            "yrs": sorted(yrs_core[pid]), "yrsAll": sorted(yrs_all[pid]),
                            "topics": person_topics.get(pid, [])[:5], "theories": [], "methods": [], "keywords": [], "groups": [], "projects": [],
                            "thin": 1, "aff": r["affiliation"], "country": r["country"], "nJoint": r["n_joint"]})
            continue
        persons.append({
            "id": pid, "name": r["name_full"], "title": r["title_nb"] or r["title_en"], "unit": r["unit_id"],
            "unitShort": (units.get(r["unit_id"]) or {}).get("short_code"), "type": r["staff_type"], "listed": r["is_listed"],
            "bio": bio, "orcid": r["orcid"], "url": r["profile_url"], "cristin": r["cristin_person_id"],
            "nPubs": n_pubs.get(pid, 0), "nCore": n_core.get(pid, 0), "years": years.get(pid),
            "topics": person_topics.get(pid, []), "theories": person_theories.get(pid, []), "methods": person_methods.get(pid, []),
            "keywords": person_kw.get(pid, []), "groups": person_groups.get(pid, []), "projects": person_projects.get(pid, []),
            "thin": int(n_core.get(pid, 0) < 2 and not bio),
            "aff": r["affiliation"], "country": r["country"], "nJoint": r["n_joint"],
            "yrs": sorted(yrs_core[pid]), "yrsAll": sorted(yrs_all[pid]),
            "collab": collab.get(pid),
        })

    # ---- publications (metadata only; those with at least one known person)
    authors = defaultdict(list)
    pname = dict(con.execute("SELECT person_id, name_full FROM person"))
    for pub_id, person_id, name, order in con.execute(
            "SELECT pub_id, person_id, name_raw, author_order FROM publication_author ORDER BY pub_id, author_order"):
        nm = (name or "").strip(", ") or pname.get(person_id) or "ukjent forfatter"
        authors[pub_id].append({"p": person_id, "n": nm})
    pub_topics = defaultdict(list)
    for pub_id, t, w in con.execute("SELECT pub_id, topic_id, weight FROM pub_topic"):
        pub_topics[pub_id].append({"t": t, "w": round(w, 2)})
    pub_theories = defaultdict(list)
    for pub_id, t in con.execute("SELECT pub_id, theory_id FROM pub_theory"):
        pub_theories[pub_id].append(t)
    pub_methods = defaultdict(list)
    for pub_id, t in con.execute("SELECT pub_id, method_id FROM pub_method"):
        pub_methods[pub_id].append(t)
    has_abs = {r[0] for r in con.execute("SELECT DISTINCT pub_id FROM publication_text WHERE kind='abstract'")}
    subfield = {}
    for pub_id, sf, field in con.execute("""SELECT pub_id, subfield, field FROM openalex_topic t WHERE score = (SELECT MAX(score) FROM openalex_topic WHERE pub_id=t.pub_id)"""):
        subfield.setdefault(pub_id, sf or field)
    tags = defaultdict(list)
    for pub_id, kw in con.execute("SELECT pub_id, keyword FROM publication_keyword WHERE source='nva_tag'"):
        if len(tags[pub_id]) < 8:
            tags[pub_id].append(kw)
    pubs = []
    for r in con.execute("""SELECT * FROM publication p WHERE EXISTS
                            (SELECT 1 FROM publication_author a WHERE a.pub_id=p.pub_id AND a.person_id IS NOT NULL)"""):
        pubs.append({
            "id": r["pub_id"], "title": r["title"], "year": r["year"], "group": r["category_group"], "core": r["is_core"],
            "venue": r["venue_name"], "nvi": r["nvi_level"], "doi": r["doi"], "nva": r["nva_id"], "lang": r["language"],
            "cited": r["cited_by_count"], "authors": authors.get(r["pub_id"], []), "topics": pub_topics.get(r["pub_id"], []),
            "theories": pub_theories.get(r["pub_id"], []), "methods": pub_methods.get(r["pub_id"], []),
            "abs": int(r["pub_id"] in has_abs), "sf": subfield.get(r["pub_id"]), "kw": tags.get(r["pub_id"], []),
        })
    # per-person OpenAlex subfield counts (top 6) for filtering
    sf_count = defaultdict(lambda: defaultdict(int))
    for pub in pubs:
        if pub["sf"]:
            for a in pub["authors"]:
                if a["p"]:
                    sf_count[a["p"]][pub["sf"]] += 1
    for person in persons:
        person["subfields"] = sorted(sf_count[person["id"]].items(), key=lambda x: -x[1])[:6]

    edges = [[r[0], r[1], r[2], r[3], r[4], r[6], r[7], (json.loads(r[5])[:8] if r[2] in ("shared_group", "shared_project", "topic_similarity", "second_degree") else None)]
             for r in con.execute("SELECT src_person_id, dst_person_id, edge_type, weight, n_evidence, evidence_json, first_year, last_year FROM person_edge")]
    groups = [dict(r) for r in con.execute("SELECT group_id AS id, name, url, description FROM research_group")]
    projects = [dict(r) for r in con.execute("SELECT project_id AS id, title_nb, title_en, summary, start_date, end_date, status, url FROM project WHERE project_id IN (SELECT project_id FROM project_participant WHERE person_id IS NOT NULL)")]
    citations = [list(r) for r in con.execute("SELECT citing_pub_id, cited_pub_id FROM citation")]

    # shard publications: per person, per topic, plus a compact index for the search page
    by_person = defaultdict(list)
    for pub in pubs:
        for a in pub["authors"]:
            if a["p"]:
                by_person[a["p"]].append(pub)
    by_topic = defaultdict(list)
    for pub in pubs:
        if pub["core"]:
            for t in pub["topics"]:
                by_topic[t["t"]].append({"id": pub["id"], "title": pub["title"], "year": pub["year"], "group": pub["group"], "core": 1, "abs": pub["abs"], "lang": pub["lang"], "venue": pub["venue"],
                                         "doi": pub["doi"], "nva": pub["nva"], "cited": pub["cited"], "w": t["w"], "authors": pub["authors"], "topics": pub["topics"]})
    pub_dir = WEB_DATA_DIR / "pubs"
    shutil.rmtree(pub_dir, ignore_errors=True)
    (pub_dir / "by_person").mkdir(parents=True, exist_ok=True)
    (pub_dir / "by_topic").mkdir(parents=True, exist_ok=True)
    for pid, lst in by_person.items():
        (pub_dir / "by_person" / f"{pid.replace(':', '_')}.json").write_text(json.dumps(lst, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    for tid, lst in by_topic.items():
        (pub_dir / "by_topic" / f"{tid}.json").write_text(json.dumps(lst, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    index = [[p["id"], p["title"], p["year"], p["group"], p["core"], p["venue"], p["doi"], p["nva"], p["lang"], p["cited"],
              [a["p"] for a in p["authors"] if a["p"]], len(p["authors"]), [t["t"] for t in p["topics"]], p["theories"], p["methods"], p["sf"], p["abs"]]
             for p in pubs]
    print("exporting web data:")
    dump("meta.json", {"generated": date.today().isoformat(), "nPersons": len(persons), "nPubs": len(pubs), "nEdges": len(edges),
                       "units": [dict(u) for u in units.values()], "faculty": "Fakultet for lærerutdanning og internasjonale studier (LUI), OsloMet"})
    dump("taxonomy.json", {"macro": macro, "topics": topics, "theories": theories, "methods": methods})
    dump("persons.json", persons)
    dump("pubs_index.json", index)
    (WEB_DATA_DIR / "pubs.json").unlink(missing_ok=True)
    print(f"  pubs/          {len(by_person)} per-person files, {len(by_topic)} per-topic files")
    dump("edges.json", edges)
    dump("groups.json", groups)
    dump("projects.json", projects)
    dump("citations.json", citations)
    orders_p = DERIVED_DIR / "orders.json"
    dump("orders.json", json.loads(orders_p.read_text(encoding="utf-8")) if orders_p.exists() else {})
