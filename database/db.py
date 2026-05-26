"""
SQLite data access layer for the TRS pipeline.

One class, `Database`, owns the connection and every query. All scrapers,
the scorer, and the Excel/digest writers go through it. Rows are returned as
plain dicts so the rest of the codebase never touches sqlite3.Row.

Dedup contract: a company is identified by (company_name, state). Inserting a
duplicate is prevented by callers via `exists()`; `update()` refreshes the
machine-derived fields while preserving anything a human edited in Excel
(pipeline_stage, assigned_to, next_action, next_action_date, notes).
"""

import json
import logging
import sqlite3
from datetime import datetime, timezone

from config import DB_PATH, SCHEMA_PATH

# Fields a human owns once a record exists. Reruns must never clobber these.
USER_MANAGED_FIELDS = frozenset(
    {"pipeline_stage", "assigned_to", "next_action", "next_action_date", "notes"}
)
# Fields the database controls itself; callers cannot set them directly.
SYSTEM_FIELDS = frozenset({"id", "date_added", "last_updated"})


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, db_path=DB_PATH):
        self.db_path = str(db_path)
        self._columns_cache = None

    # ── connection ────────────────────────────────────────────────────────────
    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def initialize(self):
        """Create tables and indexes from schema.sql. Idempotent."""
        schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
        with self._connect() as conn:
            conn.executescript(schema_sql)
        logging.info("Database initialized at %s", self.db_path)
        return self.db_path

    def _company_columns(self):
        """Column names of the companies table (cached)."""
        if self._columns_cache is None:
            with self._connect() as conn:
                rows = conn.execute("PRAGMA table_info(companies);").fetchall()
            self._columns_cache = [r["name"] for r in rows]
        return self._columns_cache

    # ── helpers ────────────────────────────────────────────────────────────────
    @staticmethod
    def _to_dict(row):
        if row is None:
            return None
        d = dict(row)
        raw = d.get("raw_data")
        if raw:
            try:
                d["raw_data_parsed"] = json.loads(raw)
            except (ValueError, TypeError):
                pass
        return d

    def _filter_to_columns(self, record, drop=()):
        """Keep only keys that map to real columns, minus an optional drop set."""
        cols = set(self._company_columns())
        out = {}
        for k, v in record.items():
            if k not in cols or k in drop:
                continue
            # Serialize nested structures (e.g. raw_data passed as a dict).
            if isinstance(v, (dict, list)):
                v = json.dumps(v)
            out[k] = v
        return out

    # ── writes ──────────────────────────────────────────────────────────────────
    def insert(self, record: dict) -> int:
        data = self._filter_to_columns(record, drop=SYSTEM_FIELDS)
        data.setdefault("company_name", record.get("company_name", ""))
        data["date_added"] = _today()
        data["last_updated"] = _now()
        cols = list(data.keys())
        placeholders = ", ".join("?" for _ in cols)
        sql = f"INSERT INTO companies ({', '.join(cols)}) VALUES ({placeholders})"
        with self._connect() as conn:
            cur = conn.execute(sql, [data[c] for c in cols])
            return cur.lastrowid

    def update(self, record: dict) -> int:
        """Refresh machine-derived fields for an existing (name, state) record.

        Returns the number of rows updated. User-managed fields are preserved.
        """
        name = record.get("company_name")
        state = record.get("state")
        data = self._filter_to_columns(
            record, drop=SYSTEM_FIELDS | USER_MANAGED_FIELDS
        )
        # Don't let an update wipe a populated field with an empty value.
        data = {k: v for k, v in data.items() if v not in (None, "")}
        if not data:
            return 0
        data["last_updated"] = _now()
        set_clause = ", ".join(f"{c} = ?" for c in data)
        params = list(data.values())
        if state:
            where = "company_name = ? AND IFNULL(state, '') = ?"
            params += [name, state]
        else:
            where = "company_name = ?"
            params += [name]
        sql = f"UPDATE companies SET {set_clause} WHERE {where}"
        with self._connect() as conn:
            cur = conn.execute(sql, params)
            return cur.rowcount

    def exists(self, company_name: str, state=None) -> bool:
        if not company_name:
            return False
        with self._connect() as conn:
            if state:
                row = conn.execute(
                    "SELECT 1 FROM companies WHERE company_name = ? "
                    "AND IFNULL(state, '') = ? LIMIT 1",
                    (company_name, state),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT 1 FROM companies WHERE company_name = ? LIMIT 1",
                    (company_name,),
                ).fetchone()
        return row is not None

    def set_excel_exported(self, ids):
        """Mark a set of company ids as included in the latest Excel export."""
        ids = list(ids)
        with self._connect() as conn:
            conn.execute("UPDATE companies SET excel_exported = 0")
            if ids:
                conn.executemany(
                    "UPDATE companies SET excel_exported = 1 WHERE id = ?",
                    [(i,) for i in ids],
                )

    # ── reads ─────────────────────────────────────────────────────────────────
    def get_by_tier(self, tier: int):
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM companies WHERE tier = ? "
                "ORDER BY score_total DESC, company_name ASC",
                (tier,),
            ).fetchall()
        return [self._to_dict(r) for r in rows]

    def get_all(self):
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM companies "
                "ORDER BY tier ASC, score_total DESC, company_name ASC"
            ).fetchall()
        return [self._to_dict(r) for r in rows]

    def get_recent(self, since_date: str, tiers=(1, 2)):
        """Records added on/after since_date (ISO date) in the given tiers."""
        placeholders = ", ".join("?" for _ in tiers)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM companies WHERE date_added >= ? "
                f"AND tier IN ({placeholders}) "
                f"ORDER BY tier ASC, score_total DESC",
                (since_date, *tiers),
            ).fetchall()
        return [self._to_dict(r) for r in rows]

    def get_run_log(self, limit=200):
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM run_log ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def counts_by_tier(self):
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT tier, COUNT(*) AS n FROM companies GROUP BY tier"
            ).fetchall()
        return {r["tier"]: r["n"] for r in rows}

    # ── run logging ──────────────────────────────────────────────────────────
    def log_run(
        self,
        source,
        records_pulled=0,
        records_new=0,
        records_updated=0,
        tier1_count=0,
        tier2_count=0,
        errors="",
        duration_seconds=0.0,
    ):
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO run_log (run_date, source, records_pulled, "
                "records_new, records_updated, tier1_count, tier2_count, "
                "errors, duration_seconds) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    _now(),
                    source,
                    records_pulled,
                    records_new,
                    records_updated,
                    tier1_count,
                    tier2_count,
                    errors or "",
                    round(float(duration_seconds), 2),
                ),
            )
