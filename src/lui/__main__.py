"""CLI: python -m lui <stage> [--refresh] [--max-age DAYS]"""
from __future__ import annotations

import argparse
import importlib

STAGES = {
    "db-init": "lui.db:init_db",
    "scrape-oslomet": "lui.scrape.oslomet:run",
    "scrape-cristin": "lui.scrape.cristin:run",
    "scrape-nva": "lui.scrape.nva:run",
    "scrape-openalex": "lui.scrape.openalex:run",
    "scrape-pdf": "lui.scrape.pdf:run",
    "identity": "lui.identity:run",
    "embed": "lui.classify.embed:run",
    "cluster": "lui.classify.cluster:run",
    "tag": "lui.classify.tag:run",
    "externals": "lui.build.externals:run",
    "build-edges": "lui.build.edges:run",
    "build-matrices": "lui.build.matrices:run",
    "build-collab": "lui.build.collab:run",
    "export-web": "lui.build.export_web:run",
    "export-graph": "lui.build.export_graph:run",
    "verify": "lui.verify:run",
}


def main() -> None:
    ap = argparse.ArgumentParser(prog="lui")
    ap.add_argument("stage", choices=STAGES)
    ap.add_argument("--refresh", action="store_true", help="ignore cache")
    ap.add_argument("--max-age", type=float, default=30, help="cache max age in days")
    ap.add_argument("--limit", type=int, default=None, help="process only N items (debug)")
    ap.add_argument("-k", type=int, default=150, help="number of clusters (cluster stage)")
    a = ap.parse_args()
    mod, fn = STAGES[a.stage].split(":")
    func = getattr(importlib.import_module(mod), fn)
    if a.stage == "db-init":
        func()
    else:
        kw = {"k": a.k} if a.stage in ("cluster", "tag") else {}
        func(refresh=a.refresh, max_age=a.max_age, limit=a.limit, **kw)


if __name__ == "__main__":
    main()
