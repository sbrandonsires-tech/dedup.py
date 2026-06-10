"""
Census Scraper — County Business Patterns (CBP), free API.

IMPORTANT: CBP is aggregate market data, not a company directory. It reports
how many establishments and employees exist per NAICS code per geography. It
does NOT name individual businesses, so it cannot generate deal leads on its
own. `run()` therefore returns no company rows; use `get_market_stats()` to
size markets and prioritize which states / sectors to mine with the other
scrapers.

A free API key (CENSUS_API_KEY) is effectively required: the API now returns a
"Missing Key" page for keyless requests. get_market_stats() logs and returns
empty results when no key is configured.

Docs: https://www.census.gov/data/developers/data-sets/cbp-nonemp-zbp/cbp-api.html
"""

import logging

from config import (
    CENSUS_API_KEY,
    CENSUS_CBP_URL,
    CENSUS_CBP_YEAR,
    NAICS_TARGET,
    TARGET_STATES,
)
from scrapers.http_client import make_session, get_json, polite_sleep

# FIPS state code -> USPS abbreviation (target states only; extend as needed).
_STATE_FIPS = {
    "01": "AL", "04": "AZ", "05": "AR", "08": "CO", "12": "FL", "13": "GA",
    "16": "ID", "17": "IL", "18": "IN", "19": "IA", "20": "KS", "21": "KY",
    "22": "LA", "26": "MI", "27": "MN", "28": "MS", "29": "MO", "30": "MT",
    "31": "NE", "35": "NM", "37": "NC", "38": "ND", "39": "OH", "40": "OK",
    "41": "OR", "45": "SC", "46": "SD", "47": "TN", "48": "TX", "49": "UT",
    "51": "VA", "54": "WV", "55": "WI", "56": "WY",
}
_FIPS_BY_ABBR = {v: k for k, v in _STATE_FIPS.items()}


class CensusScraper:
    source = "census"

    def __init__(self):
        self.session = make_session()

    def run(self):
        """CBP yields no individual companies; not a lead source."""
        logging.info(
            "Census CBP is aggregate-only; no company leads produced. "
            "Use get_market_stats() for market sizing."
        )
        return []

    def get_market_stats(self, states=None, naics_codes=None, year=None):
        """Establishment + employment counts per (state, NAICS).

        Returns a list of dicts: {state, naics, establishments, employees}.
        """
        states = states or TARGET_STATES
        naics_codes = naics_codes or NAICS_TARGET
        year = year or CENSUS_CBP_YEAR
        url = CENSUS_CBP_URL.format(year=year)

        out = []
        for abbr in states:
            fips = _FIPS_BY_ABBR.get(abbr)
            if not fips:
                continue
            for naics in naics_codes:
                try:
                    rows = self._query(url, fips, naics)
                except Exception as e:  # noqa: BLE001
                    logging.warning("Census %s/%s error: %s", abbr, naics, e)
                    continue
                for r in rows:
                    out.append(
                        {
                            "state": abbr,
                            "naics": naics,
                            "establishments": r.get("ESTAB"),
                            "employees": r.get("EMP"),
                            "year": year,
                        }
                    )
                polite_sleep()
        return out

    def _query(self, url, state_fips, naics):
        params = {
            "get": "ESTAB,EMP,NAME",
            "for": f"state:{state_fips}",
            "NAICS2017": naics,
        }
        if CENSUS_API_KEY:
            params["key"] = CENSUS_API_KEY
        data = get_json(self.session, url, params=params)
        if not data or len(data) < 2:
            return []
        header = data[0]
        return [dict(zip(header, row)) for row in data[1:]]
