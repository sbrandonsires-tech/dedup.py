"""
OSHA Scraper — inspection and violation records (free, no key).

Two modes:
  run() / run_discovery()  — find establishments in target SIC codes with
                             recent inspections (discovery of new targets)
  enrich_company(name)     — pull inspection history for a known company

Signal logic (severity flag):
  * any willful violation                -> high
  * 3+ serious violations                -> high
  * 1-2 serious violations               -> medium
  * other violations only                -> low
  * none                                 -> none

Caveat: OSHA records are address/establishment matched, not entity matched,
so a company that relocated may look clean when it isn't.

Docs: https://www.osha.gov/data
"""

import logging

from config import ALL_TARGET_SIC, MAX_RESULTS_PER_SOURCE, OSHA_BASE_URL
from scrapers.http_client import make_session, get_json, polite_sleep


def _viol_counts(record):
    serious = int(record.get("nr_serious", 0) or 0)
    willful = int(record.get("nr_willful", 0) or 0)
    repeat = int(record.get("nr_repeat", 0) or 0)
    other = int(record.get("nr_other", 0) or 0)
    return serious, willful, repeat, other


def _severity(serious, willful, total):
    if willful > 0 or serious >= 3:
        return "high"
    if serious >= 1:
        return "medium"
    if total > 0:
        return "low"
    return "none"


class OSHAScraper:
    source = "osha"

    def __init__(self):
        self.session = make_session()

    def run(self):
        return self.run_discovery()

    def run_discovery(self, sic_codes=None, states=None):
        results = []
        codes = sic_codes or ALL_TARGET_SIC[:20]  # bound discovery breadth
        for sic in codes:
            if len(results) >= MAX_RESULTS_PER_SOURCE:
                break
            try:
                inspections = self._search(sic=sic, state=(states[0] if states else None))
            except Exception as e:  # noqa: BLE001
                logging.error("OSHA SIC %s error: %s", sic, e)
                continue
            for insp in inspections:
                parsed = self._parse_inspection(insp)
                if parsed:
                    results.append(parsed)
                if len(results) >= MAX_RESULTS_PER_SOURCE:
                    break
            polite_sleep()
        return results

    def enrich_company(self, company_name, state=None):
        try:
            inspections = self._search(establishment=company_name, state=state)
        except Exception as e:  # noqa: BLE001
            logging.warning("OSHA enrichment failed for %s: %s", company_name, e)
            return {}
        if not inspections:
            return {"osha_violation_count": 0, "osha_severity": "none"}

        total_serious = total_willful = total_all = 0
        last_date = ""
        for insp in inspections:
            s, w, r, o = _viol_counts(insp)
            total_serious += s
            total_willful += w
            total_all += s + w + r + o
            d = insp.get("open_date", "") or ""
            last_date = max(last_date, d)
        return {
            "osha_violation_count": total_all,
            "osha_last_inspection": last_date,
            "osha_severity": _severity(total_serious, total_willful, total_all),
        }

    def _search(self, sic=None, establishment=None, state=None):
        params = {"limit": 100, "offset": 0}
        if sic:
            params["sic_code"] = sic
        if establishment:
            params["establishment_name"] = establishment
        if state:
            params["state"] = state
        data = get_json(self.session, OSHA_BASE_URL, params=params)
        return data.get("list", []) or data.get("data", []) or []

    def _parse_inspection(self, insp):
        s, w, r, o = _viol_counts(insp)
        total = s + w + r + o
        return {
            "company_name": insp.get("estab_name")
            or insp.get("establishment_name", ""),
            "source": self.source,
            "source_id": str(insp.get("activity_nr", "")),
            "state": (insp.get("site_state") or insp.get("state") or "").upper()[:2],
            "city": insp.get("site_city") or insp.get("city", ""),
            "zip": insp.get("site_zip") or insp.get("zip_code", ""),
            "sic_code": str(insp.get("sic_code", "") or ""),
            "naics_code": str(insp.get("naics_code", "") or ""),
            "osha_violation_count": total,
            "osha_last_inspection": insp.get("open_date", ""),
            "osha_severity": _severity(s, w, total),
            "raw_data": insp,
        }
