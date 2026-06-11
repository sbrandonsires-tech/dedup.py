"""SQLite access layer. One connection per process, row factory = dict-like."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from typing import Any, Iterable

from . import normalize, settings

_TODAY = lambda: date.today().isoformat()
_NOW = lambda: datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    with open(settings.SCHEMA_PATH, "r", encoding="utf-8") as fh:
        conn.executescript(fh.read())
    conn.commit()


def reset_new_flags(conn: sqlite3.Connection) -> None:
    conn.execute("UPDATE companies SET new_this_run = 0")
    conn.commit()


def upsert_company(conn: sqlite3.Connection, record: dict[str, Any]) -> tuple[int, bool]:
    """Insert or merge a company on the dedup key. Returns (company_id, is_new).

    `record` may carry any companies-table column plus name/state/domain. On a
    merge, non-empty incoming values fill blanks but never clobber existing data.
    """
    name = record.get("name", "")
    state = normalize.normalize_state(record.get("state"))
    domain = normalize.normalize_domain(record.get("domain"))
    key = normalize.dedup_key(name, state, domain)
    norm_name = normalize.normalize_name(name)

    row = conn.execute(
        "SELECT * FROM companies WHERE dedup_key = ?", (key,)
    ).fetchone()

    merge_cols = [
        "domain", "county", "city", "naics_code", "naics_label", "sic_code",
        "employee_count", "employee_band", "revenue_estimate", "ebitda_estimate",
        "revenue_basis", "founded_year", "years_in_business", "owner_age_estimate",
        "institutional_owned", "excluded", "exclusion_reason",
    ]

    if row is None:
        cols = {
            "dedup_key": key,
            "name": name,
            "normalized_name": norm_name,
            "domain": domain or None,
            "state": state or None,
            "first_source": record.get("source", "unknown"),
            "first_seen": _TODAY(),
            "last_seen": _TODAY(),
            "new_this_run": 1,
        }
        for c in merge_cols:
            if c in record and record[c] not in (None, ""):
                cols[c] = record[c]
        placeholders = ", ".join("?" for _ in cols)
        conn.execute(
            f"INSERT INTO companies ({', '.join(cols)}) VALUES ({placeholders})",
            tuple(cols.values()),
        )
        cid = conn.execute("SELECT id FROM companies WHERE dedup_key = ?", (key,)).fetchone()["id"]
        return cid, True

    cid = row["id"]
    updates = {"last_seen": _TODAY()}
    for c in merge_cols:
        incoming = record.get(c)
        if incoming not in (None, "") and (row[c] in (None, "", 0)):
            updates[c] = incoming
    set_clause = ", ".join(f"{c} = ?" for c in updates)
    conn.execute(
        f"UPDATE companies SET {set_clause} WHERE id = ?",
        (*updates.values(), cid),
    )
    return cid, False


def add_signal(conn: sqlite3.Connection, company_id: int, *, signal_type: str,
               value: str | None, source: str, source_url: str | None = None,
               fetch_date: str | None = None, confidence: float = 0.5) -> None:
    conn.execute(
        """INSERT OR IGNORE INTO signals
           (company_id, signal_type, value, source, source_url, fetch_date, confidence)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (company_id, signal_type, value, source, source_url,
         fetch_date or _TODAY(), confidence),
    )


def add_contact(conn: sqlite3.Connection, company_id: int, **kw) -> None:
    conn.execute(
        """INSERT OR IGNORE INTO contacts
           (company_id, name, title, email, phone, source, source_url, fetch_date)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (company_id, kw.get("name"), kw.get("title"), kw.get("email"),
         kw.get("phone"), kw.get("source"), kw.get("source_url"),
         kw.get("fetch_date") or _TODAY()),
    )


def write_score(conn: sqlite3.Connection, company_id: int, run_id: int | None,
                breakdown: dict) -> None:
    conn.execute(
        """INSERT INTO scores
           (company_id, run_id, scored_at, total, niche_fit, size_fit,
            succession, geography, data_confidence, breakdown_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(company_id, run_id) DO UPDATE SET
            scored_at=excluded.scored_at, total=excluded.total,
            niche_fit=excluded.niche_fit, size_fit=excluded.size_fit,
            succession=excluded.succession, geography=excluded.geography,
            data_confidence=excluded.data_confidence,
            breakdown_json=excluded.breakdown_json""",
        (company_id, run_id, _NOW(), breakdown["total"], breakdown["niche_fit"],
         breakdown["size_fit"], breakdown["succession"], breakdown["geography"],
         breakdown["data_confidence"], breakdown["json"]),
    )


def log_run(conn: sqlite3.Connection, source: str, *, pulled: int = 0, new: int = 0,
            updated: int = 0, notes: str = "", duration: float = 0.0) -> int:
    cur = conn.execute(
        """INSERT INTO run_log
           (run_date, source, records_pulled, records_new, records_updated,
            notes, duration_seconds)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (_NOW(), source, pulled, new, updated, notes, duration),
    )
    conn.commit()
    return cur.lastrowid


def signals_for(conn: sqlite3.Connection, company_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM signals WHERE company_id = ?", (company_id,)
    ).fetchall()


def all_companies(conn: sqlite3.Connection, include_excluded: bool = False
                  ) -> list[sqlite3.Row]:
    sql = "SELECT * FROM companies"
    if not include_excluded:
        sql += " WHERE excluded = 0"
    return conn.execute(sql).fetchall()


def latest_run_id(conn: sqlite3.Connection) -> int | None:
    row = conn.execute("SELECT MAX(id) AS m FROM run_log").fetchone()
    return row["m"] if row else None
