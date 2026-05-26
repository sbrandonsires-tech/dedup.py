"""
SAM.gov Scraper — federal contractor registry (Entity Management API v3).

Requires a free API key (set SAM_API_KEY in the environment / .env). Register
at https://sam.gov. Docs: https://open.gsa.gov/api/entity-api/

What it pulls:
  * Businesses registered for federal contracting by NAICS code
  * Self-reported revenue size band -> revenue estimate range
  * State / city / address, UEI
  * Registration expiration (lapsed => possible exit / transition signal)
  * Small-business flag

Limitations:
  * Only covers entities that registered for federal work.
  * Revenue is self-reported and banded, not precise.
  * A lapsed registration does not necessarily mean the business is closing.
"""

import logging

from config import (
    NAICS_TARGET,
    SAM_API_KEY,
    SAM_ENTITY_URL,
    MAX_RESULTS_PER_SOURCE,
    REVENUE_MIN,
    REVENUE_MAX,
)
from scrapers.http_client import make_session, get_json, polite_sleep

# SAM receipts band code -> (revenue low, revenue high) in dollars.
_REVENUE_BANDS = {
    "A": (0, 100_000),
    "B": (100_000, 250_000),
    "C": (250_000, 500_000),
    "D": (500_000, 1_000_000),
    "E": (1_000_000, 2_000_000),
    "F": (2_000_000, 5_000_000),
    "G": (5_000_000, 10_000_000),
    "H": (10_000_000, 17_000_000),
    "I": (17_000_000, 25_000_000),
    "J": (25_000_000, 38_500_000),
    "K": (38_500_000, 100_000_000),
}


class SAMScraper:
    source = "sam"

    def __init__(self):
        self.session = make_session()

    def run(self):
        if not SAM_API_KEY:
            logging.warning("SAM_API_KEY not set; skipping SAM.gov scraper.")
            return []

        results = []
        for naics in NAICS_TARGET:
            if len(results) >= MAX_RESULTS_PER_SOURCE:
                break
            try:
                entities = self._search_by_naics(naics)
            except Exception as e:  # noqa: BLE001
                logging.error("SAM NAICS %s error: %s", naics, e)
                continue
            for entity in entities:
                parsed = self._parse_entity(entity)
                if parsed:
                    results.append(parsed)
                if len(results) >= MAX_RESULTS_PER_SOURCE:
                    break
            polite_sleep()
        return results

    def _search_by_naics(self, naics_code):
        params = {
            "api_key": SAM_API_KEY,
            "primaryNaics": naics_code,
            "registrationStatus": "A",  # Active registrations
            "includeSections": "entityRegistration,coreData,assertions",
            "page": 0,
            "size": 100,
        }
        data = get_json(self.session, SAM_ENTITY_URL, params=params)
        return data.get("entityData", []) or []

    def _parse_entity(self, entity):
        try:
            reg = entity.get("entityRegistration", {}) or {}
            core = entity.get("coreData", {}) or {}
            geo = core.get("physicalAddress", {}) or {}
            assertions = entity.get("assertions", {}) or {}
            goods = assertions.get("goodsAndServices", {}) or {}

            receipts = goods.get("receiptsTotalValue", "")
            rev_low, rev_high = _REVENUE_BANDS.get(receipts, (0, 0))

            # Skip if the band is clearly outside TRS criteria.
            if rev_high > 0 and (rev_high < REVENUE_MIN or rev_low > REVENUE_MAX):
                return None

            exp_date = reg.get("registrationExpirationDate", "") or ""
            lapsed = bool(exp_date) and exp_date < "2025-01-01"
            biz_types = (core.get("businessTypes", {}) or {}).get(
                "businessTypeList", []
            ) or []
            type_codes = {bt.get("businessTypeCode") for bt in biz_types}

            return {
                "company_name": reg.get("legalBusinessName", ""),
                "source": self.source,
                "source_id": reg.get("ueiSAM", ""),
                "state": (geo.get("stateOrProvinceCode", "") or "").upper()[:2],
                "city": geo.get("city", ""),
                "zip": geo.get("zipCode", ""),
                "address": geo.get("addressLine1", ""),
                "naics_code": reg.get("primaryNaics", ""),
                "revenue_estimate_low": rev_low or None,
                "revenue_estimate_high": rev_high or None,
                "filing_status": "lapsed" if lapsed else "active",
                # Common small-business type codes (e.g. 27 = small business).
                "sba_loan_flag": 1 if "27" in type_codes else 0,
                "raw_data": entity,
            }
        except Exception as e:  # noqa: BLE001
            logging.warning("SAM entity parse error: %s", e)
            return None
