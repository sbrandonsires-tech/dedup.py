"""
EDGAR financials enricher — extract revenue / EBITDA proxy from XBRL.

Uses the SEC company-facts API (data.sec.gov/api/xbrl/companyfacts), which
returns structured XBRL values reported in 10-K/10-Q filings. Far more reliable
than text-parsing MD&A. Pulls the most recent annual (10-K) figures for:

  * Revenue        (Revenues or RevenueFromContractWithCustomer...)
  * Operating income, depreciation & amortization -> EBITDA proxy
  * Net income (fallback context)

EBITDA proxy = OperatingIncomeLoss + DepreciationDepletionAndAmortization.
Only populated when both inputs are present; otherwise left as None.

Note: only SEC filers have XBRL data (generally larger companies). Returns
empty dict when nothing usable is found.
"""

import logging

from config import EDGAR_FACTS_URL
from scrapers.http_client import make_session, get, polite_sleep

_REVENUE_CONCEPTS = [
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
]


def _latest_annual(units_usd):
    """Most recent 10-K (FY) value from a us-gaap concept's USD unit list."""
    annual = [
        u
        for u in units_usd
        if u.get("form") == "10-K" and u.get("fp") == "FY" and u.get("val") is not None
    ]
    if not annual:
        annual = [u for u in units_usd if u.get("val") is not None]
    if not annual:
        return None
    return max(annual, key=lambda u: u.get("end", ""))


class EDGARFinancials:
    def __init__(self):
        self.session = make_session(
            {"Accept": "application/json"}
        )

    def enrich(self, cik):
        if not cik:
            return {}
        try:
            url = EDGAR_FACTS_URL.format(cik=int(cik))
            data = get(self.session, url).json()
        except Exception as e:  # noqa: BLE001
            logging.warning("EDGAR financials failed for CIK %s: %s", cik, e)
            return {}
        finally:
            polite_sleep()

        usgaap = data.get("facts", {}).get("us-gaap", {})

        def latest(concept):
            unit = usgaap.get(concept, {}).get("units", {}).get("USD", [])
            entry = _latest_annual(unit) if unit else None
            return entry.get("val") if entry else None

        revenue = next(
            (latest(c) for c in _REVENUE_CONCEPTS if latest(c) is not None), None
        )
        op_income = latest("OperatingIncomeLoss")
        dep_amort = latest("DepreciationDepletionAndAmortization")

        ebitda = None
        if op_income is not None and dep_amort is not None:
            ebitda = op_income + dep_amort

        out = {}
        if revenue is not None:
            out["revenue_estimate_low"] = revenue
            out["revenue_estimate_high"] = revenue
        if ebitda is not None:
            out["ebitda_estimate"] = ebitda
        return out
