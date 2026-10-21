"""Assign topics (from the frozen taxonomy), theories and methods to publications, and
aggregate person profiles (person_topic / person_theory / person_method).

Inputs: config/taxonomy/{macro_topics,micro_topics,theories,methods}.yaml,
        data/derived/embeddings.npz, data/derived/clusters_k<k>.npz
"""
from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from datetime import date

import numpy as np
import yaml

import csv

from ..db import connect, run_log, upsert
from ..paths import CONFIG_DIR, DERIVED_DIR
from .embed import EMB_PATH, MODEL

TAX = CONFIG_DIR / "taxonomy"
TOP_N = 3
TEMP = 0.02              # softmax temperature over cosine similarities
MARGIN = 0.025           # secondary topics must be within this cosine distance of the best
HALF_LIFE = 8.0          # years; recency weight = 0.5 ** (age / HALF_LIFE)
PRIMARY_MIN = 0.15
KW_TITLE = 0.30          # topic keyword found in title / author keywords
KW_ABSTRACT = 0.15       # topic keyword found in abstract
BIO_KW_WEIGHT = 2.0      # a topic named in the bio counts like two publications
CRISTIN_KW_WEIGHT = 1.0  # a topic matching a self-chosen Cristin keyword


def topic_regexes(micro: list[dict]) -> dict[str, re.Pattern]:
    """One case-insensitive, word-bounded regex per topic from its keyword list (>= 4 chars)."""
    out = {}
    for t in micro:
        kws = [k for k in t.get("keywords", []) if len(k) >= 4]
        if kws:
            out[t["id"]] = re.compile(r"(?<![\wæøåÆØÅ])(?:" + "|".join(re.escape(k) for k in sorted(kws, key=len, reverse=True)) + r")(?![\wæøåÆØÅ])", re.I)
    return out


def load_yaml(name):
    return yaml.safe_load((TAX / name).read_text(encoding="utf-8"))


def softmax_top(scores: np.ndarray, n: int, temp: float) -> list[tuple[int, float]]:
    top = np.argsort(-scores)[:n]
    top = top[scores[top] >= scores[top[0]] - MARGIN]
    z = np.exp((scores[top] - scores[top].max()) / temp)
    z /= z.sum()
    return [(int(i), float(w)) for i, w in zip(top, z) if w >= 0.08]


def compile_vocab(items: list[dict]) -> list[tuple[str, str, list[re.Pattern]]]:
    return [(it["id"], it["label"], [re.compile(p, re.I) for p in it["patterns"]]) for it in items]


def run(refresh=False, max_age=None, limit=None, k: int = 150) -> None:
    con = connect()
    macro = load_yaml("macro_topics.yaml")["macro"]
    micro = load_yaml("micro_topics.yaml")["topics"]
    theories = compile_vocab(load_yaml("theories.yaml")["theories"])
    methods = compile_vocab(load_yaml("methods.yaml")["methods"])

    # ---------- taxonomy tables
    for t in ("pub_topic", "pub_theory", "pub_method", "person_topic", "person_theory", "person_method", "topic", "macro_topic", "theory", "method"):
        con.execute(f"DELETE FROM {t}")
    for i, m in enumerate(macro):
        upsert(con, "macro_topic", {"macro_id": m["id"], "slug": m["id"], "label_nb": m["label_nb"], "label_en": m["label_en"],
                                    "definition": m.get("definition"), "colour": m.get("colour")})
    for t in micro:
        upsert(con, "topic", {"topic_id": t["id"], "slug": t["id"], "label_nb": t["label_nb"], "label_en": t["label_en"],
                              "definition_nb": t.get("definition_nb"), "definition_en": t.get("definition_en"), "macro_id": t["macro"],
                              "keywords_json": json.dumps(t.get("keywords", []), ensure_ascii=False)})
    for tid, label, pats in theories:
        upsert(con, "theory", {"theory_id": tid, "label": label, "aliases_json": json.dumps([p.pattern for p in pats])})
    for mid, label, pats in methods:
        upsert(con, "method", {"method_id": mid, "label": label, "aliases_json": json.dumps([p.pattern for p in pats])})
    con.commit()

    # ---------- topic centroids: mean of member-cluster docs + embedded definition
    z = np.load(EMB_PATH, allow_pickle=False)
    ids, kinds, emb = z["ids"], z["kinds"], z["emb"]
    cl = np.load(DERIVED_DIR / f"clusters_k{k}.npz", allow_pickle=False)
    cl_ids, cl_labels = cl["ids"], cl["labels"]
    cluster_of = dict(zip(cl_ids.tolist(), cl_labels.tolist()))
    pos = {d: i for i, d in enumerate(ids.tolist())}

    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(MODEL)
    def_texts = [f"{t['label_en']}. {t.get('definition_en') or ''} Keywords: {', '.join(t.get('keywords', []))}" for t in micro]
    def_emb = model.encode(["passage: " + x for x in def_texts], normalize_embeddings=True, batch_size=16)

    topic_ids = [t["id"] for t in micro]
    cluster_to_topic: dict[int, str] = {}
    for t in micro:
        for c in t.get("clusters", []):
            cluster_to_topic[int(c)] = t["id"]
    centroids = np.zeros((len(micro), emb.shape[1]), dtype=np.float32)
    pub_rows = np.where(kinds == "pub")[0]
    for j, t in enumerate(micro):
        members = [pos[d] for d, c in cluster_of.items() if c in set(int(x) for x in t.get("clusters", [])) and d in pos]
        sims_all = emb[pub_rows] @ def_emb[j]
        nearest = pub_rows[np.argsort(-sims_all)[:40]].tolist()      # anchors the topic in both languages
        if len(members) > 20:   # trim noisy clusters: keep the 60 % of members closest to the topic definition
            sims_def = emb[members] @ def_emb[j]
            keep_n = max(20, int(len(members) * 0.6))
            members = [members[i] for i in np.argsort(-sims_def)[:keep_n]]
        cluster_mean = emb[members].mean(axis=0) if members else emb[nearest].mean(axis=0)
        vec = 0.35 * cluster_mean + 0.35 * emb[nearest].mean(axis=0) + 0.3 * def_emb[j]
        centroids[j] = vec / (np.linalg.norm(vec) + 1e-9)

    # ---------- publication -> topics (embedding + cluster + lexical evidence)
    rx = topic_regexes(micro)
    titles = dict(con.execute("SELECT pub_id, COALESCE(title,'') FROM publication"))
    tag_text: dict[str, str] = defaultdict(str)
    for pub_id, kw in con.execute("SELECT pub_id, keyword FROM publication_keyword WHERE source IN ('nva_tag','openalex')"):
        tag_text[pub_id] += " " + kw
    abstracts: dict[str, str] = {}
    for pub_id, txt in con.execute("SELECT pub_id, text FROM publication_text WHERE kind='abstract' ORDER BY CASE source WHEN 'nva' THEN 0 WHEN 'cristin' THEN 1 ELSE 2 END"):
        abstracts.setdefault(pub_id, txt)
    pub_mask = kinds == "pub"
    sims = emb[pub_mask] @ centroids.T
    pub_ids = ids[pub_mask].tolist()
    n_tagged = n_kw = 0
    for row, pub_id in enumerate(pub_ids):
        picks = softmax_top(sims[row], TOP_N, TEMP)
        mapped = cluster_to_topic.get(cluster_of.get(pub_id, -1))
        weights = {topic_ids[i]: w for i, w in picks}
        evidence = {tid: "embedding" for tid in weights}
        if mapped and mapped not in weights:          # the cluster's own topic always participates
            weights[mapped] = 0.25
        if mapped:
            weights[mapped] = weights.get(mapped, 0) + 0.15
            evidence[mapped] = "cluster+embedding"
        head = titles.get(pub_id, "") + " " + tag_text.get(pub_id, "")
        body = abstracts.get(pub_id, "")
        for tid, pat in rx.items():
            if pat.search(head):
                weights[tid] = weights.get(tid, 0) + KW_TITLE
                evidence[tid] = (evidence.get(tid, "") + "+keyword:title").strip("+")
                n_kw += 1
            elif body and pat.search(body):
                weights[tid] = weights.get(tid, 0) + KW_ABSTRACT
                evidence[tid] = (evidence.get(tid, "") + "+keyword:abstract").strip("+")
                n_kw += 1
        s = sum(weights.values())
        for tid, w in weights.items():
            upsert(con, "pub_topic", {"pub_id": pub_id, "topic_id": tid, "weight": round(w / s, 4),
                                      "evidence": evidence.get(tid, "embedding"), "rationale": None})
        n_tagged += 1
    con.commit()
    print(f"  lexical topic evidence on {n_kw} publication-topic pairs", flush=True)

    # ---------- publication -> theories / methods (regex over all text)
    texts: dict[str, list[str]] = defaultdict(list)
    for pub_id, title in con.execute("SELECT pub_id, title FROM publication WHERE is_core=1 OR (category_group='lecture' AND length(title) >= 40)"):
        texts[pub_id].append(title or "")
    for pub_id, txt in con.execute("SELECT pub_id, text FROM publication_text WHERE kind IN ('abstract','intro','conclusion')"):
        if pub_id in texts:
            texts[pub_id].append(txt)
    n_th = n_me = 0
    for pub_id, parts in texts.items():
        blob = "\n".join(parts)
        for tid, _, pats in theories:
            hits = sum(len(p.findall(blob)) for p in pats)
            if hits:
                m = next((p.search(blob) for p in pats if p.search(blob)), None)
                quote = blob[max(0, m.start() - 80): m.end() + 80].replace("\n", " ") if m else None
                upsert(con, "pub_theory", {"pub_id": pub_id, "theory_id": tid, "confidence": min(1.0, hits / 3), "quote": quote})
                n_th += 1
        for mid, _, pats in methods:
            hits = sum(len(p.findall(blob)) for p in pats)
            if hits:
                upsert(con, "pub_method", {"pub_id": pub_id, "method_id": mid, "confidence": min(1.0, hits / 3)})
                n_me += 1
    con.commit()

    # ---------- person profiles
    year_now = date.today().year
    pubmeta = {r[0]: (r[1] or 1.0, r[2]) for r in con.execute("SELECT pub_id, weight, year FROM publication")}

    def recency(year):
        return 0.5 ** (max(0, year_now - year) / HALF_LIFE) if year else 0.6

    person_pubs: dict[str, list[str]] = defaultdict(list)
    for pub_id, person_id in con.execute("SELECT pub_id, person_id FROM publication_author WHERE person_id IS NOT NULL"):
        person_pubs[person_id].append(pub_id)
    pub_topics = defaultdict(list)
    for pub_id, tid, w in con.execute("SELECT pub_id, topic_id, weight FROM pub_topic"):
        pub_topics[pub_id].append((tid, w))
    pub_th = defaultdict(list)
    for pub_id, tid, c in con.execute("SELECT pub_id, theory_id, confidence FROM pub_theory"):
        pub_th[pub_id].append((tid, c))
    pub_me = defaultdict(list)
    for pub_id, mid, c in con.execute("SELECT pub_id, method_id, confidence FROM pub_method"):
        pub_me[pub_id].append((mid, c))

    persons = [r[0] for r in con.execute("SELECT person_id FROM person")]
    bio_rows = {d: i for d, i in pos.items() if kinds[i] == "person"}
    stated_by_person: dict[str, dict] = {}
    n_profiles = 0
    for pid in persons:
        acc: dict[str, float] = defaultdict(float)
        cnt: dict[str, int] = defaultdict(int)
        th: dict[str, float] = defaultdict(float)
        me: dict[str, float] = defaultdict(float)
        for pub_id in set(person_pubs.get(pid, [])):
            w_cat, year = pubmeta.get(pub_id, (1.0, None))
            f = w_cat * recency(year)
            for tid, w in pub_topics.get(pub_id, []):
                acc[tid] += (w ** 1.5) * f      # emphasise each publication's primary topic
                if w >= 0.2:
                    cnt[tid] += 1
            for tid, c in pub_th.get(pub_id, []):
                th[tid] += c * f
            for mid, c in pub_me.get(pub_id, []):
                me[mid] += c * f
        # bio text contributes like one and a half publications so thin profiles still get a profile
        stated: dict[str, set] = {"topic": set(), "theory": set(), "method": set()}
        if pid in bio_rows:
            bsim = emb[bio_rows[pid]] @ centroids.T
            for i, w in softmax_top(bsim, TOP_N, TEMP):
                acc[topic_ids[i]] += 1.5 * w
                cnt[topic_ids[i]] += 0
            blob = con.execute("SELECT text FROM doc WHERE doc_id=?", (pid,)).fetchone()[0]
            # explicitly stated interests: topic keywords in the bio count like two publications each
            for tid, pat in rx.items():
                if pat.search(blob):
                    acc[tid] += BIO_KW_WEIGHT
                    stated["topic"].add(tid)
            for tid, _, pats in theories:
                if any(p.search(blob) for p in pats):
                    th[tid] += 0.8
                    stated["theory"].add(tid)
            for mid, _, pats in methods:
                if any(p.search(blob) for p in pats):
                    me[mid] += 0.8
                    stated["method"].add(mid)
        # self-chosen Cristin keywords
        for (kw,) in con.execute("SELECT keyword FROM person_keyword WHERE person_id=? AND source='cristin'", (pid,)):
            for tid, pat in rx.items():
                if pat.search(kw):
                    acc[tid] += CRISTIN_KW_WEIGHT
                    stated["topic"].add(tid)
        if any(stated.values()):
            stated_by_person[pid] = stated
        if not acc:
            continue
        total = sum(acc.values())
        ranked = sorted(acc.items(), key=lambda x: -x[1])
        for rank, (tid, v) in enumerate(ranked[:10]):
            score = v / total
            upsert(con, "person_topic", {"person_id": pid, "topic_id": tid, "score": round(score, 4), "n_pubs": cnt[tid],
                                         "is_primary": int(score >= PRIMARY_MIN or rank == 0)})
        for tid, v in sorted(th.items(), key=lambda x: -x[1])[:12]:
            upsert(con, "person_theory", {"person_id": pid, "theory_id": tid, "score": round(v / (sum(th.values()) or 1), 4)})
        for mid, v in sorted(me.items(), key=lambda x: -x[1])[:12]:
            upsert(con, "person_method", {"person_id": pid, "method_id": mid, "score": round(v / (sum(me.values()) or 1), 4)})
        n_profiles += 1
    con.commit()

    # ---------- audit: stated interests that did not make it into the profile
    misses = []
    for pid, st in stated_by_person.items():
        have_t = {r[0] for r in con.execute("SELECT topic_id FROM person_topic WHERE person_id=?", (pid,))}
        have_th = {r[0] for r in con.execute("SELECT theory_id FROM person_theory WHERE person_id=?", (pid,))}
        have_me = {r[0] for r in con.execute("SELECT method_id FROM person_method WHERE person_id=?", (pid,))}
        for kind, have in (("topic", have_t), ("theory", have_th), ("method", have_me)):
            for x in sorted(st[kind] - have):
                misses.append((pid, kind, x))
    with (DERIVED_DIR / "attribution_audit.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["person_id", "kind", "id", "note"])
        for pid, kind, x in misses:
            w.writerow([pid, kind, x, "stated in bio/keywords but absent from profile"])
    print(f"  attribution audit: {len(stated_by_person)} persons with stated interests, {len(misses)} misses -> attribution_audit.csv", flush=True)

    with run_log(con, "tag") as log:
        log["rows"] = n_tagged
        log["notes"] = f"{len(micro)} topics/{len(macro)} macro; {n_tagged} pubs tagged; {n_th} theory, {n_me} method assignments; {n_profiles} person profiles"
    print("done:", log["notes"])
