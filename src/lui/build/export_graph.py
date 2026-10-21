"""Export the person graph as GraphML/GEXF (for Gephi, R, Python) and CSV edge/node lists."""
from __future__ import annotations

import csv

import networkx as nx

from ..db import connect
from ..paths import DERIVED_DIR


def run(refresh=False, max_age=None, limit=None) -> None:
    con = connect()
    G = nx.MultiDiGraph()
    topics = {}
    for pid, tid, s, prim in con.execute("SELECT person_id, topic_id, score, is_primary FROM person_topic ORDER BY score DESC"):
        topics.setdefault(pid, []).append((tid, s, prim))
    for r in con.execute("SELECT person_id, name_full, staff_type, unit_id, title_nb, is_listed, affiliation, country, n_joint, orcid FROM person"):
        t = topics.get(r[0], [])
        G.add_node(r[0], name=r[1] or "", staff_type=r[2] or "", unit=r[3] or "", title=r[4] or "", listed=int(r[5] or 0),
                   affiliation=r[6] or "", country=r[7] or "", n_joint=int(r[8] or 0), orcid=r[9] or "",
                   primary_topics=";".join(x[0] for x in t if x[2]), top_topic=t[0][0] if t else "")
    for s, t, typ, w, n, y0, y1 in con.execute("SELECT src_person_id, dst_person_id, edge_type, weight, n_evidence, first_year, last_year FROM person_edge"):
        G.add_edge(s, t, key=typ, type=typ, weight=float(w), n=int(n), first_year=y0 or 0, last_year=y1 or 0)
    nx.write_graphml(G, DERIVED_DIR / "person_graph.graphml")
    nx.write_gexf(G, DERIVED_DIR / "person_graph.gexf")
    with (DERIVED_DIR / "edges.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh); w.writerow(["source", "target", "type", "weight", "n_evidence", "first_year", "last_year"])
        for s, t, d in G.edges(data=True):
            w.writerow([s, t, d["type"], d["weight"], d["n"], d["first_year"], d["last_year"]])
    with (DERIVED_DIR / "nodes.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh); keys = ["name", "staff_type", "unit", "title", "listed", "affiliation", "country", "n_joint", "orcid", "primary_topics", "top_topic"]
        w.writerow(["id"] + keys)
        for n, d in G.nodes(data=True):
            w.writerow([n] + [d.get(k, "") for k in keys])
    print(f"graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges -> {DERIVED_DIR / 'person_graph.graphml'} (+ .gexf, nodes.csv, edges.csv)")
