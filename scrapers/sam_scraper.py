"""
SAM.gov Scraper — federal contractor registry (Entity Management API v3).

Requires a free API key (set SAM_API_KEY in the environment / .env). Register
at https://sam.gov. Docs: https://open.gsa.gov/api/entity-api/

What it pulls:
  * Businesses registered for federal contracting by NAICS code
  * Real average annual revenue and employee count (assertions.sizeMetrics) —
    this is actual size data, not a self-reported band
  * State / city / address, UEI
  * Registration expiration (lapsed => possible exit / transition signal)

API specifics (confirmed against the live API):
  * NAICS must be a full 6-digit code; 3-digit prefixes and wildcards return
    nothing. We query config.SAM_NAICS_CODES, one request per code.
  * The state filter parameter is `physicalAddressProvinceOrStateCode`.
  * The public key is rate limited; a full run can exhaust the daily quota.

Limitations:
  * Only covers entities registered for federal work.
  * sizeMetrics revenue is a 5-year average of receipts (SBA size basis), close
    to but not identical to a single-year top line.
  * A lapsed registration does not necessarily mean the business is closing.
"""

import logging

from config import (
    SAM_NAICS_CODES,
    SAM_API_KEY,
    SAM_ENTITY_URL,
    MAX_RESULTS_PER_SOURCE,
    REVENUE_MIN,
    REVENUE_MAX,
)
from scrapers.http_client import make_session, get_json, polite_sleep

# Heavy responses (assertions section) need a longer timeout than the default.
_SAM_TIMEOUT = 90
_PAGE_SIZE = 10


def _to_number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class SAMScraper:
    source = "sam"

    def __init__(self):
        self.session = make_session()

    def run(self):
        if not SAM_API_KEY:
            logging.warning("SAM_API_KEY not set; skipping SAM.gov scraper.")
            return []

        results = []
        for naics in SAM_NAICS_CODES:
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
            "naicsCode": naics_code,  # must be a full 6-digit code
            "registrationStatus": "A",  # active registrations
            "includeSections": "entityRegistration,coreData,assertions",
            "page": 0,
            "size": _PAGE_SIZE,
        }
        data = get_json(self.session, SAM_ENTITY_URL, params=params, timeout=_SAM_TIMEOUT)
        return data.get("entityData", []) or []

    def _parse_entity(self, entity):
        try:
            reg = entity.get("entityRegistration", {}) or {}
            core = entity.get("coreData", {}) or {}
            geo = core.get("physicalAddress", {}) or {}
            assertions = entity.get("assertions", {}) or {}
            goods = assertions.get("goodsAndServices", {}) or {}
            size = assertions.get("sizeMetrics", {}) or {}

            revenue = _to_number(size.get("averageAnnualRevenue"))
            employees = _to_number(size.get("averageNumberOfEmployees"))

            # Trim the obviously-out-of-range entities so the result cap isn't
            # spent on tiny shops or large primes. Keep records with no revenue
            # data (unknown) for the scorer to weigh.
            if revenue is not None and not (
                REVENUE_MIN * 0.5 <= revenue <= REVENUE_MAX * 2
            ):
                return None

            exp_date = reg.get("registrationExpirationDate", "") or ""
            lapsed = bool(exp_date) and exp_date < "2025-01-01"

            return {
                "company_name": reg.get("legalBusinessName", ""),
                "source": self.source,
                "source_id": reg.get("ueiSAM", ""),
                "state": (geo.get("stateOrProvinceCode", "") or "").upper()[:2],
                "city": geo.get("city", ""),
                "zip": geo.get("zipCode", ""),
                "address": geo.get("addressLine1", ""),
                "naics_code": goods.get("primaryNaics", "")
                or reg.get("primaryNaics", ""),
                "revenue_estimate_low": revenue,
                "revenue_estimate_high": revenue,
                "employee_count_low": int(employees) if employees else None,
                "employee_count_high": int(employees) if employees else None,
                "filing_status": "lapsed" if lapsed else "active",
                "raw_data": entity,
            }
        except Exception as e:  # noqa: BLE001
            logging.warning("SAM entity parse error: %s", e)
            return None
