"""Build one text document per core publication (and per person bio) and embed them
with a multilingual sentence-embedding model. Output: data/derived/embeddings.npz + doc table."""
from __future__ import annotations

import os

import numpy as np

from ..db import connect, init_db, run_log
from ..paths import DATA_DIR, DERIVED_DIR

# keep the model cache inside the project (the user cache dir is not writable here)
os.environ.setdefault("HF_HOME", str(DATA_DIR / "hf_cache"))
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

MODEL = "intfloat/multilingual-e5-base"   # 768-d, nb/nn/en in one space
MAX_CHARS = 6000
EMB_PATH = DERIVED_DIR / "embeddings.npz"

ABSTRACT_PRIORITY = {"nva": 0, "cristin": 1, "openalex": 2, "pdf": 3}


def build_docs(con) -> list[tuple[str, str, str]]:
    """Return [(doc_id, kind, text)] for core publications and persons with text."""
    docs: list[tuple[str, str, str]] = []
    pubs = con.execute("""SELECT pub_id, title, year FROM publication
                          WHERE is_core=1 OR (category_group='lecture' AND length(title) >= 40)""").fetchall()
    texts: dict[str, dict] = {}
    for pub_id, kind, source, text in con.execute(
            "SELECT pub_id, kind, source, text FROM publication_text WHERE kind IN ('abstract','intro','conclusion')"):
        d = texts.setdefault(pub_id, {})
        if kind == "abstract":
            cur = d.get("abstract")
            if cur is None or ABSTRACT_PRIORITY.get(source, 9) < cur[0]:
                d["abstract"] = (ABSTRACT_PRIORITY.get(source, 9), text)
        else:
            d[kind] = text
    kws: dict[str, list[str]] = {}
    for pub_id, kw in con.execute("SELECT pub_id, keyword FROM publication_keyword WHERE source IN ('nva_tag','openalex') ORDER BY score DESC"):
        kws.setdefault(pub_id, []).append(kw)
    for pub_id, title, year in pubs:
        t = texts.get(pub_id, {})
        parts = [title or ""]
        if t.get("abstract"):
            parts.append(t["abstract"][1])
        if kws.get(pub_id):
            parts.append("Keywords: " + "; ".join(kws[pub_id][:15]))
        if t.get("intro"):
            parts.append(t["intro"][:1500])
        if t.get("conclusion"):
            parts.append(t["conclusion"][:1500])
        text = "\n".join(p for p in parts if p).strip()
        if len(text) > 40:   # title alone is kept only if reasonably long
            docs.append((pub_id, "pub", text[:MAX_CHARS]))

    for person_id, bio_nb, bio_en, bg in con.execute(
            "SELECT person_id, bio_nb, bio_en, cristin_background FROM person"):
        kw = [r[0] for r in con.execute("SELECT keyword FROM person_keyword WHERE person_id=?", (person_id,))]
        text = "\n".join(x for x in [bio_nb or bio_en, bg, ("Keywords: " + "; ".join(kw)) if kw else None] if x)
        if len(text) > 60:
            docs.append((person_id, "person", text[:MAX_CHARS]))
    return docs


def run(refresh=False, max_age=None, limit=None) -> None:
    init_db()
    con = connect()
    docs = build_docs(con)
    if limit:
        docs = docs[:limit]
    print(f"embedding {len(docs)} docs ({sum(k == 'pub' for _, k, _ in docs)} pubs, "
          f"{sum(k == 'person' for _, k, _ in docs)} persons) with {MODEL}", flush=True)
    con.execute("DELETE FROM doc")
    con.executemany("INSERT INTO doc(doc_id, kind, text, n_chars) VALUES (?,?,?,?)",
                    [(i, k, t, len(t)) for i, k, t in docs])
    con.commit()

    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(MODEL)
    # incremental: reuse vectors of docs already embedded (same id and same text length) unless --refresh
    old: dict[str, np.ndarray] = {}
    if EMB_PATH.exists() and not refresh:
        z = np.load(EMB_PATH, allow_pickle=False)
        for i, e in zip(z["ids"].tolist(), z["emb"]):
            old[i] = e
    todo = [(i, k, t) for i, k, t in docs if i not in old]
    print(f"  reusing {len(docs) - len(todo)} vectors, embedding {len(todo)} new docs", flush=True)
    with run_log(con, "embed") as log:
        new = model.encode(["passage: " + t for _, _, t in todo], batch_size=16, show_progress_bar=True,
                           normalize_embeddings=True) if todo else np.zeros((0, 768), dtype=np.float32)
        new_map = {i: e for (i, _, _), e in zip(todo, new)}
        emb = np.stack([old.get(i, new_map.get(i)) for i, _, _ in docs]).astype(np.float32)
        np.savez_compressed(EMB_PATH, ids=np.array([i for i, _, _ in docs]), kinds=np.array([k for _, k, _ in docs]), emb=emb)
        log["rows"] = len(docs)
        log["notes"] = f"{MODEL} -> {EMB_PATH.name} {emb.shape}"
    print("done:", log["notes"])
