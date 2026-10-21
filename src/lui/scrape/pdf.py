"""Download open-access PDFs (NVA open files, OpenAlex OA links) and extract abstract/intro/conclusion."""
from __future__ import annotations

import hashlib
import re
import time

import httpx
import pymupdf

from ..db import connect, init_db, run_log, upsert
from ..http import USER_AGENT
from ..paths import PDF_DIR

NVA = "https://api.nva.unit.no"
MAX_BYTES = 60_000_000
MAX_WORDS = 1500

HEAD_INTRO = re.compile(r"^(?:\d+(?:\.\d+)*\.?\s*)?(introduction|innledning|innleiing|introduksjon|bakgrunn|background|"
                        r"innledning og bakgrunn|introduction and background)\s*:?$", re.I)
HEAD_CONCL = re.compile(r"^(?:\d+(?:\.\d+)*\.?\s*)?(conclusions?|concluding remarks|conclusion and implications|"
                        r"discussion and conclusions?|konklusjon(?:er)?|avslutning|avsluttende (?:refleksjoner|kommentarer|betraktninger)|"
                        r"oppsummering(?: og konklusjon)?|avsluttande (?:refleksjonar|kommentarar)|implications|final remarks|"
                        r"summary and conclusions?|konkluderende bemerkninger)\s*:?$", re.I)
HEAD_ABS = re.compile(r"^(abstract|sammendrag|samandrag|summary|resumé|resumen)\s*:?$", re.I)
HEAD_REFS = re.compile(r"^(?:\d+\.?\s*)?(references|referanser|litteratur(?:liste)?|bibliography|kilder|litteraturliste|"
                       r"referanseliste|notes|noter|acknowledg(e)?ments|takk)\s*:?$", re.I)
HEAD_ANY = re.compile(r"^(?:\d+(?:\.\d+)*\.?\s+)[A-ZÆØÅ][^.]{2,80}$")


def pdf_lines(path) -> tuple[list[str], int]:
    doc = pymupdf.open(path)
    lines: list[str] = []
    for page in doc:
        txt = page.get_text("text")
        txt = re.sub(r"-\n(?=[a-zæøå])", "", txt)       # de-hyphenate line breaks
        lines += [l.strip() for l in txt.split("\n")]
    n = doc.page_count
    doc.close()
    return lines, n


def is_heading(line: str) -> bool:
    return bool(line) and len(line) < 90 and (HEAD_ANY.match(line) or HEAD_INTRO.match(line) or HEAD_CONCL.match(line)
                                               or HEAD_REFS.match(line) or HEAD_ABS.match(line)) is not None


def section_after(lines: list[str], start: int, stop_pat: re.Pattern | None = None) -> str:
    """Collect text after a heading until the next heading-like line or word cap."""
    out: list[str] = []
    words = 0
    for l in lines[start + 1:]:
        if not l:
            continue
        if is_heading(l) and (stop_pat is None or stop_pat.match(l) or HEAD_ANY.match(l) or HEAD_REFS.match(l)
                              or HEAD_CONCL.match(l) or HEAD_INTRO.match(l)):
            if out:
                break
            continue
        out.append(l)
        words += len(l.split())
        if words >= MAX_WORDS:
            break
    return re.sub(r"\s+", " ", " ".join(out)).strip()


def extract_sections(path) -> dict:
    lines, n_pages = pdf_lines(path)
    res = {"pages": n_pages}
    idx_intro = next((i for i, l in enumerate(lines) if HEAD_INTRO.match(l)), None)
    # conclusion: take the LAST matching heading before references
    idx_refs = next((i for i in range(len(lines) - 1, -1, -1) if HEAD_REFS.match(lines[i])), len(lines))
    idx_concl = next((i for i in range(min(idx_refs, len(lines)) - 1, -1, -1) if HEAD_CONCL.match(lines[i])), None)
    idx_abs = next((i for i, l in enumerate(lines[:400]) if HEAD_ABS.match(l)), None)
    if idx_intro is not None:
        res["intro"] = section_after(lines, idx_intro)
    if idx_concl is not None:
        res["conclusion"] = section_after(lines, idx_concl, HEAD_REFS)
    if idx_abs is not None:
        res["abstract"] = section_after(lines, idx_abs)[:4000]
    return res


def download(client: httpx.Client, url: str, dest) -> bool:
    try:
        with client.stream("GET", url, timeout=120) as r:
            if r.status_code != 200 or "pdf" not in (r.headers.get("content-type") or "").lower() and not url.lower().endswith(".pdf"):
                # some OA links serve pdf without the header; sniff first bytes
                first = next(r.iter_bytes(8), b"")
                if not first.startswith(b"%PDF"):
                    return False
                data = first
                for chunk in r.iter_bytes(1 << 16):
                    data += chunk
                    if len(data) > MAX_BYTES:
                        return False
            else:
                data = b""
                for chunk in r.iter_bytes(1 << 16):
                    data += chunk
                    if len(data) > MAX_BYTES:
                        return False
                if not data.startswith(b"%PDF"):
                    return False
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return True
    except httpx.HTTPError:
        return False


def run(refresh=False, max_age=30, limit=None) -> None:
    init_db()
    con = connect()
    client = httpx.Client(headers={"User-Agent": USER_AGENT}, follow_redirects=True)
    # one file per publication: prefer NVA open file, then OpenAlex OA
    rows = con.execute("""
        SELECT pf.pub_id, pf.file_id, pf.source, pf.url, pf.local_path, pf.extracted_ok
        FROM publication_file pf JOIN publication p ON p.pub_id=pf.pub_id
        WHERE p.is_core=1
        ORDER BY pf.pub_id, CASE pf.source WHEN 'nva' THEN 0 ELSE 1 END""").fetchall()
    seen: set[str] = set()
    todo = []
    for r in rows:
        if r["pub_id"] in seen:
            continue
        seen.add(r["pub_id"])
        todo.append(r)
    if limit:
        todo = todo[:limit]
    print(f"pdf: {len(todo)} publications with a candidate file", flush=True)

    n_dl = n_ok = n_fail = 0
    with run_log(con, "scrape-pdf") as log:
        for i, r in enumerate(todo, 1):
            dest = PDF_DIR / r["pub_id"] / f"{hashlib.sha1(r['file_id'].encode()).hexdigest()[:12]}.pdf"
            if not dest.exists():
                url = r["url"]
                if r["source"] == "nva":
                    nva_id = con.execute("SELECT nva_id FROM publication WHERE pub_id=?", (r["pub_id"],)).fetchone()[0]
                    try:
                        time.sleep(0.2)
                        resp = client.get(f"{NVA}/publication/{nva_id}/filelink/{r['file_id']}", headers={"Accept": "application/json"})
                        url = resp.json().get("id") if resp.status_code == 200 else None
                    except (httpx.HTTPError, ValueError):
                        url = None
                else:
                    time.sleep(1.0)
                if not url or not download(client, url, dest):
                    n_fail += 1
                    con.execute("UPDATE publication_file SET extracted_ok=0 WHERE pub_id=? AND file_id=?", (r["pub_id"], r["file_id"]))
                    con.commit()
                    continue
                n_dl += 1
            if r["extracted_ok"] == 1 and not refresh:
                continue
            try:
                sec = extract_sections(dest)
            except Exception as e:  # corrupt pdf
                con.execute("UPDATE publication_file SET local_path=?, extracted_ok=0 WHERE pub_id=? AND file_id=?",
                            (str(dest), r["pub_id"], r["file_id"]))
                con.commit()
                n_fail += 1
                continue
            for kind in ("intro", "conclusion"):
                if sec.get(kind) and len(sec[kind]) > 200:
                    upsert(con, "publication_text", {"pub_id": r["pub_id"], "kind": kind, "source": "pdf", "lang": None,
                                                     "text": sec[kind], "char_count": len(sec[kind])})
            has_abs = con.execute("SELECT 1 FROM publication_text WHERE pub_id=? AND kind='abstract'", (r["pub_id"],)).fetchone()
            if sec.get("abstract") and len(sec["abstract"]) > 200 and not has_abs:
                upsert(con, "publication_text", {"pub_id": r["pub_id"], "kind": "abstract", "source": "pdf", "lang": None,
                                                 "text": sec["abstract"], "char_count": len(sec["abstract"])})
            ok = int(bool(sec.get("intro") or sec.get("conclusion")))
            n_ok += ok
            con.execute("UPDATE publication_file SET local_path=?, pages=?, extracted_ok=? WHERE pub_id=? AND file_id=?",
                        (str(dest), sec["pages"], ok, r["pub_id"], r["file_id"]))
            con.commit()
            if i % 50 == 0:
                print(f"  {i}/{len(todo)} downloaded {n_dl}, sections ok {n_ok}, failed {n_fail}", flush=True)
        log["rows"] = len(todo)
        log["notes"] = f"downloaded {n_dl}, sections ok {n_ok}, failed {n_fail}"
    print("done:", log["notes"])
