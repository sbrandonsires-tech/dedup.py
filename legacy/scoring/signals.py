"""
Exit-readiness signal definitions.

Two signal families feed the scorer:

  Ownership signals  — proxies for "founder/family owned and possibly ready to
                       transition": business age, lapsed registrations, SBA /
                       small-business flags.
  Stress signals     — proxies for "pressure to sell": OSHA violation severity,
                       UCC debt filings, time a brokered listing has sat on the
                       market.

Each function returns a 0-100 sub-score. The scorer applies the configured
weights (WEIGHT_OWNERSHIP_SIGNAL, WEIGHT_STRESS_SIGNAL) on top. Keeping the
logic here lets the criteria be tuned without touching the scoring math.
"""

from datetime import datetime

CURRENT_YEAR = datetime.now().year


def ownership_score(company: dict) -> int:
    """Proxy for founder-owned / transition-ready. 0-100."""
    score = 0

    years = company.get("years_in_business")
    founded = company.get("founded_year")
    if not years and founded:
        try:
            years = CURRENT_YEAR - int(founded)
        except (TypeError, ValueError):
            years = None

    if years:
        if years >= 30:
            score += 50
        elif years >= 20:
            score += 40
        elif years >= 10:
            score += 20

    filing_status = company.get("filing_status")
    if filing_status == "lapsed":
        score += 30  # Lapsed registration can signal transition or wind-down.
    elif filing_status == "active":
        score += 10

    if company.get("sba_loan_flag"):
        score += 20  # Small-business / SBA flag => likely owner-operated.

    return min(score, 100)


def stress_score(company: dict) -> int:
    """Proxy for pressure to sell. 0-100."""
    score = 0

    severity = company.get("osha_severity", "none")
    score += {"high": 60, "medium": 40, "low": 20}.get(severity, 0)

    ucc_count = company.get("ucc_filing_count", 0) or 0
    if ucc_count >= 3:
        score += 30
    elif ucc_count >= 1:
        score += 15

    dom = company.get("days_on_market", 0) or 0
    if dom >= 365:
        score += 40  # Long on market => motivated seller.
    elif dom >= 180:
        score += 25

    return min(score, 100)
