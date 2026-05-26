"""
EDGAR Scraper — SEC company discovery by SIC code.

Uses two free, no-key SEC endpoints:
  * browse-edgar (getcompany, output=atom) to list companies by SIC code
  * data.sec.gov submissions API to enrich each hit with address + filing
    history (a proxy for active vs. lapsed status)

SEC asks for a descriptive User-Agent with a contact email (set in config) and
a request rate at or below 10/sec; we add a polite delay between calls.

Limitations:
  * Only covers entities that have filed with the SEC (generally $10M+ revenue,
    or private companies with public debt / 500+ shareholders).
  * Names are legal entity names; one holding company can appear several times.
  * Revenue is not pulled here — see enrichment/edgar_financials.py for XBRL.

Docs: https://www.sec.gov/os/accessing-edgar-data
"""

import logging
import xml.etree.ElementTree as ET

from config import (
    ALL_TARGET_SIC,
    EDGAR_BROWSE_URL,
    EDGAR_SUBMISSIONS_URL,
    MAX_RESULTS_PER_SOURCE,
)
from scrapers.http_client import make_session, get, polite_sleep


def _strip_ns(tag: str) -> str:
    """'{http://www.w3.org/2005/Atom}entry' -> 'entry'."""
    return tag.rsplit("}", 1)[-1].lower()


class EDGARScraper:
    source = "edgar"

    def __init__(self):
        self.session = make_session(
            {"Accept": "application/atom+xml, application/json"}
        )

    def run(self):
        results = []
        seen_ciks = set()
        for sic in ALL_TARGET_SIC:
            if len(results) >= MAX_RESULTS_PER_SOURCE:
                break
            try:
                companies = self._search_by_sic(sic)
            except Exception as e:  # noqa: BLE001 - log and continue per SIC
                logging.error("EDGAR SIC %s search error: %s", sic, e)
                continue

            for c in companies:
                cik = c.get("cik")
                if cik in seen_ciks:
                    continue
                seen_ciks.add(cik)
                enriched = self._enrich_company(c)
                # The atom feed's name field is unreliable (a known SEC bug);
                # only keep records the submissions API could name.
                if enriched.get("company_name"):
                    results.append(enriched)
                if len(results) >= MAX_RESULTS_PER_SOURCE:
                    break
            polite_sleep()
        return results

    def _search_by_sic(self, sic_code):
        """List companies registered under a SIC code via the atom feed."""
        params = {
            "action": "getcompany",
            "SIC": sic_code,
            "type": "10-K",
            "dateb": "",
            "owner": "include",
            "count": "100",
            "output": "atom",
        }
        resp = get(self.session, EDGAR_BROWSE_URL, params=params)
        return self._parse_atom(resp.text, sic_code)

    def _parse_atom(self, xml_text, sic_code):
        """Extract CIK / SIC / state per company-info entry.

        The feed's company name is unreliable (SEC serializes it as a broken
        "ARRAY(0x...)" string), so the name is resolved later from the
        submissions API. We only need a CIK to proceed.
        """
        companies = []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            logging.error("EDGAR XML parse error (SIC %s): %s", sic_code, e)
            return companies

        for el in root.iter():
            if _strip_ns(el.tag) != "company-info":
                continue
            fields = {
                _strip_ns(child.tag): (child.text or "").strip() for child in el
            }
            cik = fields.get("cik")
            if not cik:
                continue
            name_attr = el.get("name", "") or ""
            name = "" if name_attr.startswith("ARRAY(") else name_attr
            companies.append(
                {
                    "company_name": name,
                    "source": self.source,
                    "source_id": cik,
                    "cik": cik,
                    "sic_code": fields.get("sic") or sic_code,
                    "state": (fields.get("state") or "").upper()[:2],
                }
            )
        return companies

    def _enrich_company(self, company):
        """Pull address + filing recency from the submissions API."""
        cik = company.get("cik")
        if not cik:
            return company
        try:
            url = EDGAR_SUBMISSIONS_URL.format(cik=int(cik))
            data = get(self.session, url).json()
        except Exception as e:  # noqa: BLE001
            logging.warning(
                "EDGAR enrichment failed for %s: %s", company.get("company_name"), e
            )
            return company

        # The submissions API holds the authoritative company name.
        if data.get("name"):
            company["company_name"] = data["name"]

        biz = data.get("addresses", {}).get("business", {}) or {}
        company["city"] = biz.get("city", company.get("city", ""))
        state = biz.get("stateOrCountry") or company.get("state", "")
        company["state"] = (state or "")[:2].upper()
        company["zip"] = biz.get("zipCode", "")
        if data.get("sic"):
            company["sic_code"] = data["sic"]

        recent = data.get("filings", {}).get("recent", {})
        dates = recent.get("filingDate", []) or []
        company["filing_status"] = (
            "active" if any(d >= "2024-01-01" for d in dates[:10]) else "lapsed"
        )
        company.pop("cik", None)  # internal only; not a schema column
        company["raw_data"] = {
            "cik": cik,
            "sic": data.get("sic"),
            "sicDescription": data.get("sicDescription"),
            "recent_forms": (recent.get("form", []) or [])[:5],
        }
        polite_sleep()
        return company
