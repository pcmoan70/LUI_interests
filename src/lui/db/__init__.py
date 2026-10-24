from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import yaml

from ..paths import CONFIG_DIR, DB_PATH

SCHEMA = Path(__file__).with_name("schema.sql")


def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    con = sqlite3.connect(path, timeout=120)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def init_db(path: Path = DB_PATH) -> None:
    con = connect(path)
    con.executescript(SCHEMA.read_text(encoding="utf-8"))
    # additive migrations for columns added after the first release
    for table, col, decl in [("publication_file", "url", "TEXT"), ("person", "affiliation", "TEXT"), ("person", "country", "TEXT"), ("person", "n_joint", "INTEGER")]:
        if col not in {r[1] for r in con.execute(f"PRAGMA table_info({table})")}:
            con.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
    units = yaml.safe_load((CONFIG_DIR / "units.yaml").read_text(encoding="utf-8"))["units"]
    for uid, u in units.items():
        con.execute("INSERT OR REPLACE INTO unit(unit_id,parent_unit_id,name_nb,name_en,short_code) VALUES (?,?,?,?,?)",
                    (uid, u.get("parent"), u["name_nb"], u["name_en"], u["short"]))
    con.commit()
    con.close()


def upsert(con: sqlite3.Connection, table: str, row: dict, keys: list[str] | None = None) -> None:
    """INSERT ... ON CONFLICT DO UPDATE for the given primary/unique key columns.
    Only non-NULL incoming values overwrite existing ones."""
    cols = list(row)
    placeholders = ",".join("?" * len(cols))
    if keys is None:
        sql = f"INSERT OR REPLACE INTO {table} ({','.join(cols)}) VALUES ({placeholders})"
    else:
        updates = ",".join(f"{c}=COALESCE(excluded.{c},{table}.{c})" for c in cols if c not in keys)
        sql = (f"INSERT INTO {table} ({','.join(cols)}) VALUES ({placeholders}) "
               f"ON CONFLICT({','.join(keys)}) DO UPDATE SET {updates}" if updates else
               f"INSERT OR IGNORE INTO {table} ({','.join(cols)}) VALUES ({placeholders})")
    con.execute(sql, [row[c] for c in cols])


def since_date(con: sqlite3.Connection, stage: str, since: str | None, fallback_days: int = 8) -> str | None:
    """Resolve a --since value: None → None, 'auto' → the day before the last run of `stage`
    (or `fallback_days` ago when the stage never ran), otherwise the given YYYY-MM-DD."""
    from datetime import date, timedelta
    if not since:
        return None
    if since != "auto":
        return since
    row = con.execute("SELECT MAX(started_at) FROM run_log WHERE stage=?", (stage,)).fetchone()
    last = date.fromisoformat(row[0][:10]) if row and row[0] else date.today() - timedelta(days=fallback_days - 1)
    return (last - timedelta(days=1)).isoformat()


@contextmanager
def run_log(con: sqlite3.Connection, stage: str):
    started = datetime.now(timezone.utc).isoformat()
    info = {"rows": 0, "notes": ""}
    yield info
    con.execute("INSERT INTO run_log(stage, started_at, finished_at, rows, notes) VALUES (?,?,?,?,?)",
                (stage, started, datetime.now(timezone.utc).isoformat(), info["rows"], info["notes"]))
    con.commit()
