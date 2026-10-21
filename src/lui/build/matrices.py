"""Materialise matrices (.npz) and block orderings (communities, co-clusters) used to seriate
the person x topic and person x person matrices so that structure appears as diagonal blocks."""
from __future__ import annotations

import json
from collections import defaultdict

import networkx as nx
import numpy as np

from ..db import connect, run_log
from ..paths import DERIVED_DIR

EDGE_W = {"coauthor": 1.0, "cites": 0.7, "shared_project": 0.5, "shared_group": 0.3, "topic_similarity": 0.4}


def spectral_order(M: np.ndarray) -> np.ndarray:
    """Order rows of a similarity matrix by the Fiedler vector (falls back to degree)."""
    n = M.shape[0]
    if n < 3:
        return np.arange(n)
    d = M.sum(axis=1)
    L = np.diag(d) - M
    with np.errstate(divide="ignore", invalid="ignore"):
        Dm = np.diag(1 / np.sqrt(np.where(d > 0, d, 1)))
    vals, vecs = np.linalg.eigh(Dm @ L @ Dm)
    return np.argsort(vecs[:, 1] if vals.size > 1 else d)


def run(refresh=False, max_age=None, limit=None) -> None:
    con = connect()
    persons = [r[0] for r in con.execute("SELECT person_id FROM person ORDER BY person_id")]
    pi = {p: i for i, p in enumerate(persons)}
    topics = [r[0] for r in con.execute("SELECT topic_id FROM topic ORDER BY macro_id, topic_id")]
    ti = {t: i for i, t in enumerate(topics)}

    # ---- person x topic
    PT = np.zeros((len(persons), len(topics)), dtype=np.float32)
    for p, t, s in con.execute("SELECT person_id, topic_id, score FROM person_topic"):
        if p in pi and t in ti:
            PT[pi[p], ti[t]] = s

    # ---- person x person per edge type
    PP: dict[str, np.ndarray] = defaultdict(lambda: np.zeros((len(persons), len(persons)), dtype=np.float32))
    for s, t, typ, w in con.execute("SELECT src_person_id, dst_person_id, edge_type, weight FROM person_edge"):
        if s in pi and t in pi:
            PP[typ][pi[s], pi[t]] += w
            if typ != "cites":
                PP[typ][pi[t], pi[s]] += w

    # ---- combined weighted graph -> Louvain communities
    G = nx.Graph()
    G.add_nodes_from(persons)
    for typ, M in PP.items():
        sym = M + M.T if typ == "cites" else M
        for i, j in zip(*np.nonzero(np.triu(sym, 1))):
            w = float(sym[i, j]) * EDGE_W.get(typ, 0.3)
            if G.has_edge(persons[i], persons[j]):
                G[persons[i]][persons[j]]["weight"] += w
            else:
                G.add_edge(persons[i], persons[j], weight=w)
    comms = nx.community.louvain_communities(G, weight="weight", resolution=1.0, seed=0) if G.number_of_edges() else [set(persons)]
    comms = sorted(comms, key=len, reverse=True)
    community = {}
    person_order: list[str] = []
    for ci, members in enumerate(comms):
        members = sorted(members)
        for m in members:
            community[m] = ci
        if len(members) > 2:
            sub = nx.to_numpy_array(G.subgraph(members), nodelist=members, weight="weight")
            members = [members[k] for k in spectral_order(sub)]
        person_order += members
    # singletons (no edges) go last, sorted by unit
    unit = dict(con.execute("SELECT person_id, unit_id FROM person"))
    isolated = [p for p in persons if G.degree(p) == 0]
    person_order = [p for p in person_order if p not in set(isolated)] + sorted(isolated, key=lambda p: (unit.get(p) or "", p))

    # ---- person x topic co-clustering (spectral) for the interest matrix
    topic_order, person_order_topic, cocluster = topics, [], {}
    if len(topics) >= 4 and PT.sum() > 0:
        from sklearn.cluster import SpectralCoclustering
        rows_ok = np.where(PT.sum(axis=1) > 0)[0]
        n_cl = max(2, min(12, len(topics) // 6))
        model = SpectralCoclustering(n_clusters=n_cl, random_state=0).fit(PT[rows_ok] + 1e-6)
        r_order = rows_ok[np.argsort(model.row_labels_, kind="stable")]
        c_order = np.argsort(model.column_labels_, kind="stable")
        person_order_topic = [persons[i] for i in r_order] + [p for p in persons if PT[pi[p]].sum() == 0]
        topic_order = [topics[j] for j in c_order]
        cocluster = {"persons": {persons[i]: int(model.row_labels_[k]) for k, i in enumerate(rows_ok)},
                     "topics": {topics[j]: int(model.column_labels_[j]) for j in range(len(topics))}}

    np.savez_compressed(DERIVED_DIR / "matrices.npz", persons=np.array(persons), topics=np.array(topics), person_topic=PT,
                        **{f"pp_{k}": v for k, v in PP.items()})
    orders = {"community": community, "nCommunities": len(comms), "personOrder": person_order,
              "personOrderTopic": person_order_topic, "topicOrder": topic_order, "cocluster": cocluster}
    (DERIVED_DIR / "orders.json").write_text(json.dumps(orders, ensure_ascii=False), encoding="utf-8")
    with run_log(con, "build-matrices") as log:
        log["rows"] = len(persons)
        log["notes"] = f"{len(comms)} communities, {len(topics)} topics, edges={G.number_of_edges()}"
    print("matrices:", log["notes"], "->", DERIVED_DIR / "orders.json")
