"""Cached, rate-limited HTTP client. Every response is stored under data/raw/<source>/."""
from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx

from .paths import RAW_DIR

USER_AGENT = "LUI-research-map/0.1 (OsloMet internal research mapping; contact pcmoan@gmail.com)"

# minimum seconds between requests, per host
_MIN_INTERVAL = {
    "www.oslomet.no": 1.0,
    "api.cristin.no": 0.2,
    "api.nva.unit.no": 0.2,
    "api.openalex.org": 0.25,
}
_last_call: dict[str, float] = {}


def _throttle(host: str) -> None:
    interval = _MIN_INTERVAL.get(host, 1.0)
    wait = _last_call.get(host, 0) + interval - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    _last_call[host] = time.monotonic()


def safe_key(s: str, maxlen: int = 150) -> str:
    """Turn a URL or id into a filesystem-safe key (adds a hash when truncated)."""
    k = re.sub(r"[^A-Za-z0-9._-]+", "_", s).strip("_")
    if len(k) > maxlen:
        k = k[:maxlen] + "_" + hashlib.sha1(s.encode()).hexdigest()[:10]
    return k


class Fetcher:
    def __init__(self, source: str, max_age_days: float | None = 30, refresh: bool = False):
        self.source = source
        self.dir = RAW_DIR / source
        self.dir.mkdir(parents=True, exist_ok=True)
        self.max_age = None if max_age_days is None else max_age_days * 86400
        self.refresh = refresh
        self.client = httpx.Client(
            headers={"User-Agent": USER_AGENT}, timeout=60, follow_redirects=True
        )
        self.n_network = 0
        self.n_cache = 0

    def _paths(self, key: str, ext: str) -> tuple[Path, Path]:
        base = self.dir / safe_key(key)
        return base.with_suffix(f".{ext}"), base.with_suffix(".meta.json")

    def get(self, url: str, key: str | None = None, ext: str = "json",
            headers: dict | None = None, ok_statuses=(200,)) -> bytes | None:
        """Return body bytes (from cache if fresh). None if the server answered 404."""
        key = key or url
        body_p, meta_p = self._paths(key, ext)
        if not self.refresh and meta_p.exists():
            meta = json.loads(meta_p.read_text(encoding="utf-8"))
            age = time.time() - meta["fetched_ts"]
            if self.max_age is None or age < self.max_age:
                self.n_cache += 1
                if meta["status"] == 404:
                    return None
                return body_p.read_bytes()

        host = urlparse(url).netloc
        for attempt in range(9):
            _throttle(host)
            try:
                r = self.client.get(url, headers=headers)
            except httpx.HTTPError as e:
                if attempt == 8:
                    raise
                time.sleep(2 ** attempt)
                continue
            if r.status_code == 429 and attempt < 8:          # rate limited: honour Retry-After, otherwise back off hard
                ra = r.headers.get("retry-after")
                time.sleep(float(ra) if ra and ra.replace(".", "", 1).isdigit() else min(120, 15 * (attempt + 1)))
                continue
            if r.status_code in (500, 502, 503, 504) and attempt < 8:
                time.sleep(min(60, 2 ** attempt * 2))
                continue
            break
        self.n_network += 1
        meta = {
            "url": url, "status": r.status_code, "fetched_at": datetime.now(timezone.utc).isoformat(),
            "fetched_ts": time.time(), "etag": r.headers.get("etag"),
            "content_type": r.headers.get("content-type"),
        }
        if r.status_code in (401, 403, 404, 410):   # missing or access-restricted record
            meta["status"] = 404
            meta_p.write_text(json.dumps(meta), encoding="utf-8")
            return None
        if r.status_code not in ok_statuses:
            raise httpx.HTTPStatusError(f"{r.status_code} for {url}", request=r.request, response=r)
        body_p.write_bytes(r.content)
        meta_p.write_text(json.dumps(meta), encoding="utf-8")
        return r.content

    def get_json(self, url: str, key: str | None = None, headers: dict | None = None):
        b = self.get(url, key, "json", headers={"Accept": "application/json", **(headers or {})})
        return None if b is None else json.loads(b.decode("utf-8"))

    def get_text(self, url: str, key: str | None = None, ext: str = "html", headers=None) -> str | None:
        b = self.get(url, key, ext, headers=headers)
        return None if b is None else b.decode("utf-8", errors="replace")

    def stats(self) -> str:
        return f"{self.source}: {self.n_network} network, {self.n_cache} cached"
