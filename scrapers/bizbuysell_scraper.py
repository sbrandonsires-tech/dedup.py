"""
BizBuySell Scraper — public business-for-sale listings.

  TERMS OF SERVICE NOTE: BizBuySell's Terms of Use generally prohibit
  automated access / scraping. This module is provided for completeness of the
  pipeline, but you (TRS) are responsible for confirming you have permission to
  scrape, honoring robots.txt, and respecting rate limits. Prefer their
  official data offerings or a licensed feed where one exists. The scraper uses
  conservative delays and a clearly identified User-Agent.

What it pulls (all seller-stated, unverified):
  * Business name (often anonymized, e.g. "Midwest Manufacturing Company")
  * Asking price, revenue, cash flow
  * State, broker, listing URL

Selectors will need maintenance whenever the site's HTML changes; parsing is
defensive and logs (rather than crashes) when the structure shifts.
"""

import logging

from bs4 import BeautifulSoup

from config import (
    BIZBUYSELL_BASE_URL,
    MAX_RESULTS_PER_SOURCE,
    REVENUE_MIN,
    REVENUE_MAX,
)
from scrapers.http_client import make_session, get, polite_sleep
from scrapers.listing_utils import extract_currency, parse_state


class BizBuySellScraper:
    source = "bizbuysell"

    TARGET_CATEGORIES = [
        "manufacturing-businesses-for-sale",
        "industrial-businesses-for-sale",
        "distribution-businesses-for-sale",
        "wholesale-businesses-for-sale",
    ]

    def __init__(self):
        self.session = make_session(
            {"User-Agent": "Mozilla/5.0 (compatible; TRS-Research-Bot/1.0)"}
        )

    def run(self):
        results = []
        for category in self.TARGET_CATEGORIES:
            if len(results) >= MAX_RESULTS_PER_SOURCE:
                break
            try:
                cards = self._scrape_category(category)
            except Exception as e:  # noqa: BLE001
                logging.error("BizBuySell category %s error: %s", category, e)
                continue
            for card in cards:
                parsed = self._parse_listing(card)
                if parsed:
                    results.append(parsed)
                if len(results) >= MAX_RESULTS_PER_SOURCE:
                    break
            polite_sleep(2)  # extra polite for HTML scraping
        return results

    def _scrape_category(self, category_slug, pages=5):
        cards = []
        for page in range(1, pages + 1):
            url = f"{BIZBUYSELL_BASE_URL}/{category_slug}/"
            try:
                resp = get(self.session, url, params={"pg": page})
            except Exception as e:  # noqa: BLE001
                logging.warning("BizBuySell page %s error: %s", page, e)
                break
            soup = BeautifulSoup(resp.text, "html.parser")
            page_cards = soup.select("div.result, article.listing, div.listing")
            if not page_cards:
                break
            cards.extend(page_cards)
            polite_sleep(2)
        return cards

    def _parse_listing(self, card):
        try:
            name_el = card.find(["h3", "h2", "h4"])
            name_text = name_el.get_text(strip=True) if name_el else "Unknown"

            text_blob = card.get_text(" ", strip=True)
            revenue = extract_currency(text_blob, ["revenue", "sales", "gross revenue"])
            cash_flow = extract_currency(
                text_blob, ["cash flow", "cashflow", "sde", "ebitda"]
            )
            asking_price = extract_currency(text_blob, ["asking price", "price"])

            loc_el = card.select_one(".location, .state, .listing-location")
            state = parse_state(loc_el.get_text(strip=True) if loc_el else text_blob)

            url_el = card.find("a", href=True)
            listing_url = ""
            if url_el:
                href = url_el["href"]
                listing_url = (
                    href if href.startswith("http") else f"{BIZBUYSELL_BASE_URL}{href}"
                )

            # Skip if revenue is clearly far outside the TRS window.
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
            logging.warning("BizBuySell parse error: %s", e)
            return None
