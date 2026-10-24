"""CLI: python -m lui <stage> [--refresh] [--max-age DAYS] [--fresh PREFIX,...] [--since YYYY-MM-DD|auto]"""
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
    "scrape-openalex-cites": "lui.scrape.openalex_cites:run",
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
    ap.add_argument("--fresh", default="", help="scrape stages: comma-separated cache-key prefixes to always refetch (listings)")
    ap.add_argument("--since", default=None, help="scrape-cristin/-nva: only records modified since this date (YYYY-MM-DD or 'auto' = day before last run)")
    a = ap.parse_args()
    mod, fn = STAGES[a.stage].split(":")
    func = getattr(importlib.import_module(mod), fn)
    if a.stage == "db-init":
        func()
    else:
        kw = {"k": a.k} if a.stage in ("cluster", "tag") else {}
        if a.stage.startswith("scrape-") and a.stage != "scrape-pdf":
            kw["fresh"] = tuple(x for x in a.fresh.split(",") if x)
        if a.stage in ("scrape-cristin", "scrape-nva"):
            kw["since"] = a.since
        func(refresh=a.refresh, max_age=a.max_age, limit=a.limit, **kw)


if __name__ == "__main__":
    main()
