"""
Web enricher — basic company profile from a public website.

Given a website URL (or a best-guess domain), fetches the homepage and pulls
lightweight, low-risk signals: page title, meta description, and any
"founded/established YYYY" or "NN employees" phrasing in the visible text.
These are soft signals to help triage, never authoritative.

Only fetches a single page over HTTPS with a short timeout; no crawling.
"""

import logging
import re

from bs4 import BeautifulSoup

from scrapers.http_client import make_session, get

_FOUNDED_RE = re.compile(
    r"(?:founded|established|since|est\.?)\D{0,12}(19\d{2}|20[0-2]\d)", re.I
)
_EMPLOYEES_RE = re.compile(r"([\d,]{1,7})\+?\s+employees", re.I)


class WebEnricher:
    def __init__(self):
        self.session = make_session(
            {"User-Agent": "Mozilla/5.0 (compatible; TRS-Research-Bot/1.0)"}
        )

    def enrich(self, website_url):
        if not website_url:
            return {}
        url = website_url
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        try:
            resp = get(self.session, url)
        except Exception as e:  # noqa: BLE001
            logging.warning("Web enrichment failed for %s: %s", website_url, e)
            return {}

        soup = BeautifulSoup(resp.text, "html.parser")
        text = soup.get_text(" ", strip=True)

        out = {}

        title = soup.title.get_text(strip=True) if soup.title else ""
        desc_el = soup.find("meta", attrs={"name": "description"})
        description = desc_el.get("content", "").strip() if desc_el else ""
        profile = " ".join(p for p in (title, description) if p)[:500]
        if profile:
            out["notes"] = profile

        m = _FOUNDED_RE.search(text)
        if m:
            year = int(m.group(1))
            out["founded_year"] = year

        m = _EMPLOYEES_RE.search(text)
        if m:
            count = int(m.group(1).replace(",", ""))
            out["employee_count_low"] = count
            out["employee_count_high"] = count

        return out
