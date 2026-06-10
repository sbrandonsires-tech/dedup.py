"""
UCC enricher — Uniform Commercial Code filing lookup by state.

UCC filings (a lender's security interest in a borrower's assets) are a useful
debt-pressure signal. The hard reality: there is no national UCC database, and
most Secretary of State systems require a CAPTCHA, a paid subscription, or
per-search fees and have no public API. This module therefore returns neutral
defaults and is structured so that states with a usable search can be wired in
one at a time (add a handler to STATE_HANDLERS).

Returns: {'ucc_filing_count': int, 'ucc_latest_maturity': str|None}.
"""

import logging

# Map of state code -> callable(company_name, state) -> dict. Empty until a
# specific state's search is implemented and confirmed permissible to query.
STATE_HANDLERS = {}


class UCCEnricher:
    def enrich(self, company_name, state=None):
        handler = STATE_HANDLERS.get((state or "").upper())
        if not handler:
            logging.debug(
                "No UCC handler for state %r; returning neutral defaults.", state
            )
            return {"ucc_filing_count": 0, "ucc_latest_maturity": None}
        try:
            return handler(company_name, state)
        except Exception as e:  # noqa: BLE001
            logging.warning("UCC lookup failed for %s (%s): %s", company_name, state, e)
            return {"ucc_filing_count": 0, "ucc_latest_maturity": None}
