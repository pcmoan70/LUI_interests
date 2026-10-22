"""Collaboration profile per person: coauthorship scope (LUI / other OsloMet / other Norwegian /
international) from Cristin affiliations, partner institutions and countries, internal vs external citations."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date

from ..db import connect, run_log
from ..http import Fetcher

API = "https://api.cristin.no/v2"
MAX_AUTHORS = 30
RECENT_YEARS = 5


def ensure_table(con) -> None:
    con.execute("""CREATE TABLE IF NOT EXISTS person_collab (
        person_id TEXT PRIMARY KEY,
        n_pubs INTEGER, n_solo INTEGER, n_lui INTEGER, n_oslomet INTEGER, n_norway INTEGER, n_international INTEGER, n_unknown INTEGER,
        r_pubs INTEGER, r_solo INTEGER, r_lui INTEGER, r_oslomet INTEGER, r_norway INTEGER, r_international INTEGER,
        n_countries INTEGER, countries_json TEXT, institutions_json TEXT, partners_lui INTEGER, partners_ext INTEGER,
        cites_total INTEGER, cites_internal INTEGER, cites_external INTEGER)""")
    con.execute("""CREATE TABLE IF NOT EXISTS institution (inst_id TEXT PRIMARY KEY, name TEXT, country TEXT)""")


def run(refresh=False, max_age=365, limit=None) -> None:
    con = connect()
    ensure_table(con)
    f = Fetcher("cristin", max_age_days=max_age, refresh=refresh)

    # ---- institutions (country + name) for every affiliation seen on author rows
    inst_ids = {r[0].split(".")[0] for r in con.execute(
        "SELECT DISTINCT affiliation_unit_id FROM publication_author WHERE affiliation_unit_id IS NOT NULL AND affiliation_unit_id NOT LIKE '0.%'")}
    known = {r[0]: (r[1], r[2]) for r in con.execute("SELECT inst_id, name, country FROM institution")}
    todo = sorted(i for i in inst_ids if i not in known)
    print(f"institutions: {len(inst_ids)} seen, {len(todo)} to look up", flush=True)
    for i, iid in enumerate(todo, 1):
        d = f.get_json(f"{API}/institutions/{iid}", key=f"institution_{iid}") or {}
        name = d.get("institution_name") or {}
        known[iid] = (name.get("nb") or name.get("en") or name.get("nn"), d.get("country"))
        con.execute("INSERT OR REPLACE INTO institution(inst_id, name, country) VALUES (?,?,?)", (iid, *known[iid]))
        if i % 100 == 0:
            con.commit(); print(f"  {i}/{len(todo)}", flush=True)
    con.commit()

    def scope(unit_id: str | None) -> str:
        if not unit_id or unit_id.startswith("0."):
            return "unknown"
        if unit_id.startswith("215.4."):
            return "lui"
        if unit_id.startswith("215."):
            return "oslomet"
        country = known.get(unit_id.split(".")[0], (None, None))[1]
        if country == "NO":
            return "norway"
        return "international" if country else "unknown"

    lui = {r[0] for r in con.execute("SELECT person_id FROM person WHERE is_listed=1 OR resolved_by='cristin_only'")}
    pubmeta = {r[0]: (r[1], r[2]) for r in con.execute(f"SELECT pub_id, year, cited_by_count FROM publication WHERE COALESCE(n_authors,0) <= {MAX_AUTHORS}")}
    authors: dict[str, list[tuple]] = defaultdict(list)
    for pub_id, pid, unit in con.execute("SELECT pub_id, person_id, affiliation_unit_id FROM publication_author"):
        if pub_id in pubmeta:
            authors[pub_id].append((pid, unit))
    internal_cites = Counter()
    for (cited,) in con.execute("SELECT cited_pub_id FROM citation"):
        internal_cites[cited] += 1

    year_now = date.today().year
    rows = []
    for pid in lui:
        pubs = [p for p, al in authors.items() if any(a == pid for a, _ in al)]
        if not pubs:
            continue
        c = Counter(); r = Counter(); countries = Counter(); insts = Counter(); partners_lui = set(); partners_ext = set()
        cites_total = cites_int = 0
        for p in pubs:
            year, cited = pubmeta[p]
            recent = year and year >= year_now - RECENT_YEARS
            others = [(a, u) for a, u in authors[p] if a != pid]
            c["pubs"] += 1; r["pubs"] += recent
            if not others:
                c["solo"] += 1; r["solo"] += recent
            scopes = set()
            for a, u in others:
                sc = scope(u); scopes.add(sc)
                if a:
                    (partners_lui if sc == "lui" else partners_ext).add(a)
                if sc in ("norway", "international", "oslomet") and u:
                    iid = u.split(".")[0]; insts[known.get(iid, (iid, None))[0] or iid] += 1
                if sc == "international" and u:
                    countries[known.get(u.split(".")[0], (None, None))[1]] += 1
            for sc in scopes:
                c[sc] += 1; r[sc] += recent
            cites_total += cited or 0
            cites_int += internal_cites.get(p, 0)
        rows.append((pid, c["pubs"], c["solo"], c["lui"], c["oslomet"], c["norway"], c["international"], c["unknown"],
                     r["pubs"], r["solo"], r["lui"], r["oslomet"], r["norway"], r["international"],
                     len(countries), json.dumps(countries.most_common(10)), json.dumps(insts.most_common(10), ensure_ascii=False),
                     len(partners_lui), len(partners_ext), cites_total, cites_int, max(0, cites_total - cites_int)))
    with run_log(con, "build-collab") as log:
        con.execute("DELETE FROM person_collab")
        con.executemany("INSERT INTO person_collab VALUES (" + ",".join("?" * 22) + ")", rows)
        con.commit()
        log["rows"] = len(rows)
        log["notes"] = f"{len(rows)} persons; {len(known)} institutions"
    print("collab:", log["notes"])
