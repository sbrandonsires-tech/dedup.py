"""
USPTO Scraper — patent activity via the PatentsView Search API.

Patent/IP activity is a supporting signal (an operating company with granted
patents is a real, R&D-active business), not a primary lead source: USPTO data
has no revenue or ownership fields. `run()` therefore returns no company rows;
`find_by_assignee()` is used as an enrichment helper to confirm IP activity for
a known company.

The current PatentsView Search API requires a free API key. Set USPTO_API_KEY
in the environment to enable it; without a key the scraper skips cleanly.

Docs: https://search.patentsview.org/docs/
"""

import json
import logging
import os

from config import USPTO_PATENT_URL
from scrapers.http_client import make_session, polite_sleep, get

USPTO_API_KEY = os.getenv("USPTO_API_KEY", "")


class USPTOScraper:
    source = "uspto"

    def __init__(self):
        headers = {"X-Api-Key": USPTO_API_KEY} if USPTO_API_KEY else None
        self.session = make_session(headers)

    def run(self):
        """Patents alone are not a lead source; nothing to insert."""
        logging.info("USPTO is an enrichment signal only; no company leads produced.")
        return []

    def find_by_assignee(self, organization_name, limit=25):
        """Return recent patents whose assignee matches the organization name.

        Result: {'patent_count': int, 'latest_patent_date': str|None,
                 'patents': [{patent_id, title, date}, ...]}.
        """
        if not USPTO_API_KEY:
            logging.info("USPTO_API_KEY not set; skipping patent lookup.")
            return {"patent_count": 0, "latest_patent_date": None, "patents": []}
        if not organization_name:
            return {"patent_count": 0, "latest_patent_date": None, "patents": []}

        query = {"assignees.assignee_organization": organization_name}
        fields = ["patent_id", "patent_title", "patent_date"]
        params = {
            "q": json.dumps(query),
            "f": json.dumps(fields),
            "o": json.dumps({"size": limit}),
        }
        try:
            resp = get(self.session, USPTO_PATENT_URL, params=params)
            data = resp.json()
        except Exception as e:  # noqa: BLE001
            logging.warning("USPTO lookup failed for %s: %s", organization_name, e)
            return {"patent_count": 0, "latest_patent_date": None, "patents": []}
        finally:
            polite_sleep()

        patents = data.get("patents", []) or []
        dates = [p.get("patent_date") for p in patents if p.get("patent_date")]
        return {
            "patent_count": data.get("total_hits", len(patents)),
            "latest_patent_date": max(dates) if dates else None,
            "patents": [
                {
                    "patent_id": p.get("patent_id"),
                    "title": p.get("patent_title"),
                    "date": p.get("patent_date"),
                }
                for p in patents
            ],
        }
