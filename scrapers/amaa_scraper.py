"""
AM&AA Deal Corner Scraper — public M&A listings from the Alliance of
Merger & Acquisition Advisors.

  TERMS OF SERVICE NOTE: Confirm permission, honor robots.txt, and respect
  rate limits before enabling this scraper. Much of AM&AA's Deal Corner sits
  behind member login; only publicly visible listings are reachable here, and
  there may be few or none on any given run. See the BizBuySell module header.

Pulls seller-stated name, asking price, revenue, cash flow, state, and listing
URL where public. Best-effort, defensive parsing.
"""

import logging

from bs4 import BeautifulSoup

from config import AMAA_BASE_URL, MAX_RESULTS_PER_SOURCE, REVENUE_MIN, REVENUE_MAX
from scrapers.http_client import make_session, get, polite_sleep
from scrapers.listing_utils import extract_currency, parse_state


class AMAAScraper:
    source = "amaa"

    # Public Deal Corner / deal listing path (adjust if the site reorganizes).
    LISTING_PATHS = ["/deal-corner", "/deals"]

    def __init__(self):
        self.session = make_session(
            {"User-Agent": "Mozilla/5.0 (compatible; TRS-Research-Bot/1.0)"}
        )

    def run(self):
        results = []
        for path in self.LISTING_PATHS:
            if len(results) >= MAX_RESULTS_PER_SOURCE:
                break
            try:
                cards = self._scrape_path(path)
            except Exception as e:  # noqa: BLE001
                logging.error("AM&AA path %s error: %s", path, e)
                continue
            for card in cards:
                parsed = self._parse_listing(card)
                if parsed:
                    results.append(parsed)
                if len(results) >= MAX_RESULTS_PER_SOURCE:
                    break
            polite_sleep(2)
        return results

    def _scrape_path(self, path):
        url = f"{AMAA_BASE_URL}{path}"
        try:
            resp = get(self.session, url)
        except Exception as e:  # noqa: BLE001
            logging.warning("AM&AA fetch %s error: %s", url, e)
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        return soup.select("div.deal, article.deal, div.listing, div.deal-card")

    def _parse_listing(self, card):
        try:
            name_el = card.find(["h3", "h2", "h4", "a"])
            name_text = name_el.get_text(strip=True) if name_el else "Unknown"

            text_blob = card.get_text(" ", strip=True)
            revenue = extract_currency(text_blob, ["revenue", "sales"])
            cash_flow = extract_currency(text_blob, ["cash flow", "ebitda", "sde"])
            asking_price = extract_currency(text_blob, ["asking price", "price"])
            state = parse_state(text_blob)

            url_el = card.find("a", href=True)
            listing_url = ""
            if url_el:
                href = url_el["href"]
                listing_url = (
                    href if href.startswith("http") else f"{AMAA_BASE_URL}{href}"
                )

            if revenue and (revenue < REVENUE_MIN * 0.5 or revenue > REVENUE_MAX * 2):
                return None

            return {
                "company_name": name_text,
                "source": self.source,
                "state": state,
                "asking_price": asking_price,
                "listed_revenue": revenue,
                "listed_cash_flow": cash_flow,
                "listing_url": listing_url,
                "raw_data": {"text_preview": text_blob[:500]},
            }
        except Exception as e:  # noqa: BLE001
            logging.warning("AM&AA parse error: %s", e)
            return None
