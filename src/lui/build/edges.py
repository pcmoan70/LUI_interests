"""Materialise person-person edges: coauthor, cites, shared_group, shared_project, topic_similarity."""
from __future__ import annotations

import json
from collections import defaultdict
from itertools import combinations

import numpy as np

from ..db import connect, run_log


def _add(edges: dict, a: str, b: str, typ: str, w: float, ev, year=None, directed=False):
    if a == b or not a or not b:
        return
    key = (a, b, typ) if directed else (min(a, b), max(a, b), typ)
    e = edges.setdefault(key, {"weight": 0.0, "evidence": [], "years": []})
    e["weight"] += w
    e["evidence"].append(ev)
    if year:
        e["years"].append(year)


def run(refresh=False, max_age=None, limit=None) -> None:
    con = connect()
    edges: dict = {}
    lui = {r[0] for r in con.execute("SELECT person_id FROM person WHERE is_listed=1 OR resolved_by='cristin_only'")}

    # --- coauthorship: weight = publication weight / (n_internal_authors - 1)
    pubs = defaultdict(list)
    for pub_id, person_id in con.execute(
            "SELECT pub_id, person_id FROM publication_author WHERE person_id IS NOT NULL"):
        pubs[pub_id].append(person_id)
    pmeta = {r[0]: (r[1], r[2]) for r in con.execute("SELECT pub_id, weight, year FROM publication WHERE COALESCE(n_authors,0) <= 30")}
    for pub_id, people in pubs.items():
        people = sorted(set(people))
        if len(people) < 2 or pub_id not in pmeta:
            continue
        w, year = pmeta[pub_id]
        for a, b in combinations(people, 2):
            if a in lui or b in lui:      # no external-external pairs
                _add(edges, a, b, "coauthor", w / (len(people) - 1), pub_id, year)

    # --- citations (directed: src cites dst), via publication authors
    for citing, cited in con.execute("SELECT citing_pub_id, cited_pub_id FROM citation"):
        for a in set(pubs.get(citing, [])):
            for b in set(pubs.get(cited, [])):
                if a in lui or b in lui:
                    _add(edges, a, b, "cites", 1.0, f"{citing}->{cited}", pmeta.get(citing, (0, None))[1], directed=True)

    # --- shared research group
    groups = defaultdict(set)
    for gid, pid in con.execute("SELECT group_id, person_id FROM group_member WHERE person_id IS NOT NULL"):
        groups[gid].add(pid)
    for gid, members in groups.items():
        for a, b in combinations(sorted(members), 2):
            _add(edges, a, b, "shared_group", 1.0, gid)

    # --- shared project
    projects = defaultdict(set)
    for prj, pid in con.execute("SELECT project_id, person_id FROM project_participant WHERE person_id IS NOT NULL"):
        projects[prj].add(pid)
    for prj, members in projects.items():
        if len(members) > 40:   # umbrella projects carry little signal
            continue
        for a, b in combinations(sorted(members), 2):
            _add(edges, a, b, "shared_project", 1.0, prj)

    # --- topic similarity (cosine of person x topic vectors), only when profiles exist
    rows = [r for r in con.execute("SELECT person_id, topic_id, score FROM person_topic").fetchall() if r[0] in lui]
    if rows:
        persons = sorted({r[0] for r in rows})
        topics = sorted({r[1] for r in rows})
        pi = {p: i for i, p in enumerate(persons)}
        ti = {t: i for i, t in enumerate(topics)}
        M = np.zeros((len(persons), len(topics)), dtype=np.float32)
        for p, t, s in rows:
            M[pi[p], ti[t]] = s
        M /= np.linalg.norm(M, axis=1, keepdims=True) + 1e-9
        S = M @ M.T
        for i in range(len(persons)):
            for j in range(i + 1, len(persons)):
                if S[i, j] >= 0.35:
                    shared = [topics[k] for k in np.argsort(-(M[i] * M[j]))[:3] if M[i, k] * M[j, k] > 0]
                    _add(edges, persons[i], persons[j], "topic_similarity", float(S[i, j]), shared)

    with run_log(con, "build-edges") as log:
        con.execute("DELETE FROM person_edge")
        con.executemany(
            "INSERT INTO person_edge(src_person_id, dst_person_id, edge_type, weight, n_evidence, evidence_json, first_year, last_year) VALUES (?,?,?,?,?,?,?,?)",
            [(a, b, t, round(e["weight"], 4), len(e["evidence"]), json.dumps(e["evidence"][:50], ensure_ascii=False),
              min(e["years"]) if e["years"] else None, max(e["years"]) if e["years"] else None)
             for (a, b, t), e in edges.items()])
        con.commit()
        counts = dict(con.execute("SELECT edge_type, COUNT(*) FROM person_edge GROUP BY 1").fetchall())
        log["rows"] = len(edges)
        log["notes"] = json.dumps(counts)
    print("edges:", log["notes"])
