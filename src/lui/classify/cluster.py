"""Cluster publication embeddings into candidate topics and write a human-readable report
(data/derived/clusters_k<k>.md + .json) used to design the taxonomy."""
from __future__ import annotations

import json
import re
from collections import Counter

import numpy as np
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer

from ..db import connect
from ..paths import DERIVED_DIR
from .embed import EMB_PATH

STOP_NO = """og i å på for av til er som med det en et de at den var har ble om fra kan vil skal ikke eller
men også dette disse denne der hvor hva hvordan når ved mellom under over etter før seg sin sitt sine
være blir bli hadde vært skulle kunne ville måtte må får få gjøre gjør gjort tar tatt mer mest mye
flere alle noen ingen hver både enn så bare her nå da ut inn opp ned mot innen slik samt gjennom
både blant hos vi oss vår våre du deg din dine han ham hans hun henne hennes dei deira dette desse
ein ei eit eller ikkje vere vert vart kva korleis kvar når av frå ved mellom òg berre nokon noko
artikkelen studien studie artikkel kapittel kapitlet boka bok resultatene resultata viser vise
undersøker undersøkelse analyse analysere data funn diskuterer diskusjon bidrag bidra basert
based study article paper chapter results findings analysis analyses discuss discusses using use
used also however within between among may can could would should this these those their there
which while whether through about into than more most such well one two three new way ways
norwegian norway norsk norske norge research forskning""".split()
STOP = set(STOP_NO) | set(__import__("sklearn.feature_extraction.text", fromlist=["ENGLISH_STOP_WORDS"]).ENGLISH_STOP_WORDS)


def run(refresh=False, max_age=None, limit=None, k: int = 150) -> None:
    con = connect()
    z = np.load(EMB_PATH, allow_pickle=False)
    mask = z["kinds"] == "pub"
    ids, emb = z["ids"][mask], z["emb"][mask]
    texts = dict(con.execute("SELECT doc_id, text FROM doc WHERE kind='pub'").fetchall())
    meta = {r[0]: r for r in con.execute("SELECT pub_id, title, year, category_group, language FROM publication")}
    print(f"clustering {len(ids)} pubs into k={k}", flush=True)

    km = KMeans(n_clusters=k, n_init=4, random_state=0).fit(emb)
    labels = km.labels_
    dist = np.linalg.norm(emb - km.cluster_centers_[labels], axis=1)

    # c-TF-IDF: one pseudo-document per cluster
    cluster_docs = [" ".join(texts[i] for i in ids[labels == c]) for c in range(k)]
    vec = TfidfVectorizer(ngram_range=(1, 2), min_df=2, max_df=0.5, stop_words=list(STOP),
                          token_pattern=r"(?u)\b[a-zA-ZæøåÆØÅéèüö][a-zA-ZæøåÆØÅéèüö-]{2,}\b", sublinear_tf=True)
    X = vec.fit_transform(cluster_docs)
    vocab = np.array(vec.get_feature_names_out())

    subfields = {}
    for pub_id, sf, score in con.execute("SELECT pub_id, subfield, score FROM openalex_topic"):
        subfields.setdefault(pub_id, []).append((sf, score))
    tags = {}
    for pub_id, kw in con.execute("SELECT pub_id, keyword FROM publication_keyword WHERE source='nva_tag'"):
        tags.setdefault(pub_id, []).append(kw)

    out = []
    for c in range(k):
        members = [i for i in np.where(labels == c)[0]]
        if not members:
            continue
        row = X[c].toarray().ravel()
        top_terms = [vocab[j] for j in row.argsort()[::-1][:14]]
        order = sorted(members, key=lambda i: dist[i])
        exemplars = [meta[ids[i]][1] for i in order[:6] if ids[i] in meta]
        years = [meta[ids[i]][2] for i in members if ids[i] in meta and meta[ids[i]][2]]
        langs = Counter(meta[ids[i]][4] for i in members if ids[i] in meta)
        sfc = Counter()
        for i in members:
            for sf, sc in subfields.get(ids[i], []):
                sfc[sf] += sc
        tc = Counter(t.lower() for i in members for t in tags.get(ids[i], []))
        out.append({
            "cluster": c, "n": len(members), "terms": top_terms, "exemplars": exemplars,
            "years": [min(years), max(years)] if years else None, "langs": dict(langs.most_common(3)),
            "subfields": [s for s, _ in sfc.most_common(3)], "tags": [t for t, _ in tc.most_common(8)],
            "pub_ids": [str(ids[i]) for i in members],
        })
    out.sort(key=lambda d: -d["n"])

    DERIVED_DIR.mkdir(exist_ok=True)
    (DERIVED_DIR / f"clusters_k{k}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    with (DERIVED_DIR / f"clusters_k{k}.md").open("w", encoding="utf-8") as fh:
        fh.write(f"# {len(ids)} core publications, k={k}\n\n")
        for d in out:
            fh.write(f"## C{d['cluster']}  n={d['n']}  years={d['years']}  langs={d['langs']}\n")
            fh.write(f"terms: {', '.join(d['terms'])}\n")
            if d["subfields"]:
                fh.write(f"openalex: {' | '.join(d['subfields'])}\n")
            if d["tags"]:
                fh.write(f"tags: {', '.join(d['tags'])}\n")
            for e in d["exemplars"]:
                fh.write(f"- {e}\n")
            fh.write("\n")
    np.savez_compressed(DERIVED_DIR / f"clusters_k{k}.npz", ids=ids, labels=labels, centers=km.cluster_centers_)
    print("wrote", DERIVED_DIR / f"clusters_k{k}.md")
