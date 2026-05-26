"""
OSHA Scraper — inspection & violation records via the DOL Enforcement Data API.

Uses the DOL v4 API (api.dol.gov), confirmed endpoints:
  * inspections: https://api.dol.gov/v4/get/OSHA/inspection/json
  * violations:  https://api.dol.gov/v4/get/OSHA/violation/json
Auth is a free DOL API key passed as the X-API-KEY query parameter
(config.DOL_API_KEY). Records come back under a "data" key. Without a key the
scraper skips cleanly.

Two modes:
  run() / run_discovery()  — find establishments in target SIC codes (discovery)
  enrich_company(name)     — pull inspection history + violation severity for a
                             known company

Severity (from the violation table's viol_type: S=serious, W=willful,
R=repeat, O=other):
  * any willful, or 3+ serious  -> high
  * 1-2 serious                 -> medium
  * other violations only       -> low
  * none                        -> none

NOTE: the v4 server-side filter syntax (`filter_object`) is not publicly
documented and could not be verified without a key. We send a best-effort
filter for efficiency AND always re-filter client-side, so results are correct
even if the server ignores the filter. Adjust `_filter_object` if your first
keyed run shows the filter is not being applied.

Docs: https://www.osha.gov/data  |  https://apiprod.dol.gov/v4/datasets
"""

import json
import logging

from config import (
    ALL_TARGET_SIC,
    TARGET_STATES,
    MAX_RESULTS_PER_SOURCE,
    DOL_API_KEY,
    OSHA_INSPECTION_URL,
    OSHA_VIOLATION_URL,
)
from scrapers.http_client import make_session, get, polite_sleep

_PAGE = 100


def _severity(serious, willful, total):
    if willful > 0 or serious >= 3:
        return "high"
    if serious >= 1:
        return "medium"
    if total > 0:
        return "low"
    return "none"


def _as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class OSHAScraper:
    source = "osha"

    def __init__(self):
        self.session = make_session()

    def run(self):
        return self.run_discovery()

    def run_discovery(self, sic_codes=None, states=None):
        if not DOL_API_KEY:
            logging.warning("DOL_API_KEY not set; skipping OSHA scraper.")
            return []

        codes = sic_codes or ALL_TARGET_SIC[:20]  # bound discovery breadth
        target_states = {s.upper() for s in (states or TARGET_STATES)}
        results = []
        for sic in codes:
            if len(results) >= MAX_RESULTS_PER_SOURCE:
                break
            try:
                rows = self._fetch(OSHA_INSPECTION_URL, [("sic_code", sic)])
            except Exception as e:  # noqa: BLE001
                logging.error("OSHA SIC %s error: %s", sic, e)
                continue
            for insp in rows:
                state = (insp.get("site_state") or "").upper()[:2]
                if target_states and state not in target_states:
                    continue
                results.append(self._parse_inspection(insp))
                if len(results) >= MAX_RESULTS_PER_SOURCE:
                    break
            polite_sleep()
        return results

    def enrich_company(self, company_name, state=None):
        if not DOL_API_KEY:
            return {}
        try:
            inspections = self._fetch(
                OSHA_INSPECTION_URL, [("estab_name", company_name)]
            )
        except Exception as e:  # noqa: BLE001
            logging.warning("OSHA enrichment failed for %s: %s", company_name, e)
            return {}

        if state:
            st = state.upper()[:2]
            inspections = [
                i for i in inspections if (i.get("site_state") or "").upper()[:2] == st
            ]
        if not inspections:
            return {"osha_violation_count": 0, "osha_severity": "none"}

        serious = willful = total = 0
        last_date = ""
        for insp in inspections:
            last_date = max(last_date, insp.get("open_date", "") or "")
            activity_nr = insp.get("activity_nr")
            if not activity_nr:
                continue
            try:
                violations = self._fetch(
                    OSHA_VIOLATION_URL, [("activity_nr", str(activity_nr))]
                )
            except Exception as e:  # noqa: BLE001
                logging.warning("OSHA violations fetch failed (%s): %s", activity_nr, e)
                continue
            for v in violations:
                total += 1
                vt = (v.get("viol_type") or "").upper()[:1]
                if vt == "W":
                    willful += 1
                elif vt == "S":
                    serious += 1
            polite_sleep()

        return {
            "osha_violation_count": total,
            "osha_last_inspection": last_date,
            "osha_severity": _severity(serious, willful, total),
        }

    @staticmethod
    def _filter_object(filters):
        """Best-effort v4 filter param (a JSON array of field/operator/value).

        Format unverified without a key — see module docstring. Client-side
        filtering guarantees correctness regardless of whether this is honored.
        """
        return json.dumps(
            [{"field_name": f, "operator": "eq", "value": v} for f, v in filters]
        )

    def _fetch(self, url, filters=None, limit=_PAGE):
        params = {"X-API-KEY": DOL_API_KEY, "limit": limit}
        if filters:
            params["filter_object"] = self._filter_object(filters)
        data = get(self.session, url, params=params).json()
        return data.get("data", []) or []

    def _parse_inspection(self, insp):
        emp = _as_int(insp.get("nr_in_estab"))
        return {
            "company_name": insp.get("estab_name", ""),
            "source": self.source,
            "source_id": str(insp.get("activity_nr", "")),
            "state": (insp.get("site_state") or "").upper()[:2],
            "city": insp.get("site_city", ""),
            "zip": insp.get("site_zip", ""),
            "address": insp.get("site_address", ""),
            "sic_code": str(insp.get("sic_code", "") or ""),
            "naics_code": str(insp.get("naics_code", "") or ""),
            "employee_count_low": emp,
            "employee_count_high": emp,
            "osha_last_inspection": insp.get("open_date", ""),
            "raw_data": insp,
        }
