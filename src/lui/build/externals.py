"""Promote external coauthors (not LUI staff) to light-weight person nodes.

An external gets a node when they share at least one core publication, or two publications of
any kind, with a LUI person, excluding mass-author papers (> MAX_AUTHORS authors). Attributes kept:
name, Cristin id, affiliation (institution name + country), ORCID for frequent coauthors,
number of joint publications. Category: former_lui (affiliated with 215.4.*), oslomet (other
OsloMet units) or external.
"""
from __future__ import annotations

import hashlib
from collections import Counter, defaultdict

from ..db import connect, run_log, upsert
from ..http import Fetcher
from ..identity import norm

API = "https://api.cristin.no/v2"
MAX_AUTHORS = 30
ORCID_MIN_JOINT = 3


def lui_ids(con) -> set[str]:
    return {r[0] for r in con.execute("SELECT person_id FROM person WHERE is_listed=1 OR resolved_by='cristin_only'")}


def merge_name_duplicates(con) -> int:
    """Merge name-only nodes (ext:*) into an existing identified person with the same normalised name."""
    by_name: dict[str, list[str]] = defaultdict(list)
    for pid, name in con.execute("SELECT person_id, name_full FROM person WHERE person_id NOT LIKE 'ext:%'"):
        by_name[norm(name)].append(pid)
    merged = 0
    for pid, name in con.execute("SELECT person_id, name_full FROM person WHERE person_id LIKE 'ext:%'").fetchall():
        targets = by_name.get(norm(name), [])
        if len(targets) != 1:
            continue
        target = targets[0]
        con.execute("UPDATE publication_author SET person_id=? WHERE person_id=?", (target, pid))
        for t in ("person_topic", "person_theory", "person_method", "person_keyword", "person_edge"):
            col = "src_person_id" if t == "person_edge" else "person_id"
            con.execute(f"DELETE FROM {t} WHERE {col}=?", (pid,))
        con.execute("DELETE FROM person_edge WHERE dst_person_id=?", (pid,))
        con.execute("DELETE FROM person WHERE person_id=?", (pid,))
        merged += 1
    con.commit()
    return merged


def run(refresh=False, max_age=90, limit=None) -> None:
    con = connect()
    f = Fetcher("cristin", max_age_days=max_age, refresh=refresh)
    core = lui_ids(con)
    print(f"merged {merge_name_duplicates(con)} name-only duplicates into identified persons", flush=True)
    # normalised names of every identified person: name-only author rows are attached to them instead of new nodes
    name_to_pid: dict[str, list[str]] = defaultdict(list)
    for pid, name in con.execute("SELECT person_id, name_full FROM person WHERE person_id NOT LIKE 'ext:%'"):
        name_to_pid[norm(name)].append(pid)

    # publications with at least one LUI author, excluding mass-author papers
    joint_pubs = {r[0]: (r[1], r[2]) for r in con.execute(f"""
        SELECT p.pub_id, p.is_core, p.year FROM publication p
        WHERE COALESCE(p.n_authors, 0) <= {MAX_AUTHORS}
          AND EXISTS (SELECT 1 FROM publication_author a WHERE a.pub_id=p.pub_id AND a.person_id IN ({",".join("?" * len(core))}))""",
        list(core))}

    groups: dict[str, dict] = {}
    for pub_id, cid, name, aff in con.execute(
            "SELECT pub_id, cristin_person_id, name_raw, affiliation_unit_id FROM publication_author WHERE person_id IS NULL"):
        if pub_id not in joint_pubs or not name:
            continue
        if not cid and len(name_to_pid.get(norm(name), [])) == 1:      # known person, row just lacks the Cristin id
            con.execute("UPDATE publication_author SET person_id=? WHERE pub_id=? AND person_id IS NULL AND cristin_person_id IS NULL AND name_raw=?",
                        (name_to_pid[norm(name)][0], pub_id, name))
            continue
        key = f"cristin:{cid}" if cid else f"ext:{hashlib.sha1(norm(name).encode()).hexdigest()[:12]}"
        g = groups.setdefault(key, {"cid": cid, "names": Counter(), "affs": Counter(), "pubs": set(), "core": 0, "years": []})
        g["names"][name] += 1
        if aff and aff != "0.0.0.0":
            g["affs"][aff] += 1
        if pub_id not in g["pubs"]:
            g["pubs"].add(pub_id)
            g["core"] += int(joint_pubs[pub_id][0] or 0)
            if joint_pubs[pub_id][1]:
                g["years"].append(joint_pubs[pub_id][1])
    keep = {k: g for k, g in groups.items() if g["core"] >= 1 or len(g["pubs"]) >= 2}
    if limit:
        keep = dict(list(keep.items())[:limit])
    print(f"external coauthors: {len(groups)} candidates, {len(keep)} kept", flush=True)

    # institution names (cached Cristin lookups)
    inst_cache: dict[str, tuple[str | None, str | None]] = {}

    def institution(unit_id: str) -> tuple[str | None, str | None]:
        iid = unit_id.split(".")[0]
        if iid not in inst_cache:
            d = f.get_json(f"{API}/institutions/{iid}", key=f"institution_{iid}") or {}
            name = d.get("institution_name") or {}
            inst_cache[iid] = (name.get("nb") or name.get("en") or name.get("nn"), d.get("country"))
        return inst_cache[iid]

    units = {r[0] for r in con.execute("SELECT unit_id FROM unit")}
    n_new = n_orcid = 0
    with run_log(con, "externals") as log:
        for key, g in keep.items():
            name = g["names"].most_common(1)[0][0]
            last, _, first = name.partition(", ")
            aff = g["affs"].most_common(1)[0][0] if g["affs"] else None
            inst_name, country = institution(aff) if aff else (None, None)
            if aff and aff.startswith("215.4"):
                staff_type = "former_lui"
            elif aff and aff.startswith("215."):
                staff_type = "oslomet"
            else:
                staff_type = "external"
            orcid = None
            if g["cid"] and len(g["pubs"]) >= ORCID_MIN_JOINT:
                d = f.get_json(f"{API}/persons/{g['cid']}", key=f"person_{g['cid']}") or {}
                orcid = (d.get("orcid") or {}).get("id")
                n_orcid += bool(orcid)
            upsert(con, "person", {
                "person_id": key, "cristin_person_id": g["cid"], "name_full": f"{first} {last}".strip(),
                "name_first": first or None, "name_last": last or None, "staff_type": staff_type,
                "unit_id": aff if aff in units else None, "unit_name_raw": inst_name, "affiliation": inst_name, "country": country,
                "orcid": orcid, "is_listed": 0, "resolved_by": "coauthor", "resolution_confidence": 0.9 if g["cid"] else 0.6,
                "n_joint": len(g["pubs"]),
            }, keys=["person_id"])
            if g["cid"]:
                con.execute("UPDATE publication_author SET person_id=? WHERE person_id IS NULL AND cristin_person_id=?", (key, g["cid"]))
            else:
                for nm in g["names"]:
                    con.execute("UPDATE publication_author SET person_id=? WHERE person_id IS NULL AND cristin_person_id IS NULL AND name_raw=?", (key, nm))
            n_new += 1
            if n_new % 200 == 0:
                con.commit()
                print(f"  {n_new}/{len(keep)} ({f.stats()})", flush=True)
        con.commit()
        cats = dict(con.execute("SELECT staff_type, COUNT(*) FROM person WHERE resolved_by='coauthor' GROUP BY 1").fetchall())
        log["rows"] = n_new
        log["notes"] = f"{cats}; orcid for {n_orcid}; {len(inst_cache)} institutions; {f.stats()}"
    print("done:", log["notes"])
