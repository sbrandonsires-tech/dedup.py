"""Post-ingest processing: hard exclusion filters, size estimates, and rescoring.

Kept separate from ingestion so `rescore` can re-apply edited YAML weights to the
existing database without re-fetching anything.
"""

from __future__ import annotations

from . import db, scoring, settings


def apply_filters_and_estimates(conn) -> None:
    """Set excluded flags and fill revenue/EBITDA estimates from headcount."""
    tgt = settings.targets()
    excl = tgt.get("exclusions", {})
    size = tgt.get("size", {})
    floor = excl.get("employee_floor", 10)
    ceiling = excl.get("employee_ceiling", 250)
    blocklist = [b.lower() for b in excl.get("name_blocklist", [])]
    rpe = float(size.get("revenue_per_employee", 250000))
    m_lo = float(size.get("ebitda_margin_low", 0.08))
    m_hi = float(size.get("ebitda_margin_high", 0.15))

    for comp in conn.execute("SELECT * FROM companies").fetchall():
        reason = comp["exclusion_reason"]
        excluded = comp["excluded"]

        name_l = (comp["name"] or "").lower()
        if not excluded:
            if any(b in name_l for b in blocklist):
                excluded, reason = 1, "name blocklist (staffing/construction pass-through)"
            elif comp["employee_count"] is not None and comp["employee_count"] < floor:
                excluded, reason = 1, f"under {floor} employees"
            elif comp["employee_count"] is not None and comp["employee_count"] > ceiling:
                excluded, reason = 1, f"over {ceiling} employees"
            elif comp["institutional_owned"]:
                excluded, reason = 1, "institutionally owned"

        # Estimate revenue/EBITDA from headcount when missing.
        rev = comp["revenue_estimate"]
        basis = comp["revenue_basis"]
        ebitda = comp["ebitda_estimate"]
        emp = comp["employee_count"]
        if (rev is None or rev == 0) and emp:
            rev = emp * rpe
            basis = f"{emp} employees x ${rpe:,.0f}/employee benchmark"
        if rev and (ebitda is None or ebitda == 0):
            ebitda = rev * (m_lo + m_hi) / 2

        conn.execute(
            """UPDATE companies SET excluded=?, exclusion_reason=?,
               revenue_estimate=?, revenue_basis=?, ebitda_estimate=? WHERE id=?""",
            (excluded, reason, rev, basis, ebitda, comp["id"]),
        )
    conn.commit()


def rescore(conn, run_id: int | None = None) -> int:
    """Recompute and persist scores for every company. Returns count scored."""
    settings.reload()
    if run_id is None:
        run_id = db.latest_run_id(conn) or 0
    n = 0
    for comp in conn.execute("SELECT * FROM companies").fetchall():
        company = dict(comp)
        sigs = [dict(s) for s in db.signals_for(conn, comp["id"])]
        breakdown = scoring.score_company(company, sigs)
        db.write_score(conn, comp["id"], run_id, breakdown)
        n += 1
    conn.commit()
    return n
