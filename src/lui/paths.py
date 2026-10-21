from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PDF_DIR = DATA_DIR / "pdf"
DB_PATH = DATA_DIR / "db" / "lui.sqlite"
DERIVED_DIR = DATA_DIR / "derived"
CONFIG_DIR = ROOT / "config"
WEB_DATA_DIR = ROOT / "web" / "data"

for _d in (RAW_DIR, PDF_DIR, DB_PATH.parent, DERIVED_DIR):
    _d.mkdir(parents=True, exist_ok=True)
