"""
DealStream Scraper — public business / M&A listings.

  TERMS OF SERVICE NOTE: DealStream's terms generally restrict automated
  access. Confirm permission, honor robots.txt, and respect rate limits before
  enabling this scraper in production. See the BizBuySell module header for the
  same caveat.

Mirrors the BizBuySell scraper: pulls seller-stated name, asking price,
revenue, cash flow, state, and listing URL from public industrial / business
category pages. Selectors are best-effort and defensive.
"""

import logging

from bs4 import BeautifulSoup

from config import DEALSTREAM_BASE_URL, MAX_RESULTS_PER_SOURCE, REVENUE_MIN, REVENUE_MAX
from scrapers.http_client import make_session, get, polite_sleep
from scrapers.listing_utils import extract_currency, parse_state


class DealStreamScraper:
    source = "dealstream"

    TARGET_PATHS = [
        "/businesses-for-sale/manufacturing",
        "/businesses-for-sale/distribution",
        "/businesses-for-sale/industrial",
    ]

    def __init__(self):
        self.session = make_session(
            {"User-Agent": "Mozilla/5.0 (compatible; TRS-Research-Bot/1.0)"}
        )

    def run(self):
        results = []
        for path in self.TARGET_PATHS:
            if len(results) >= MAX_RESULTS_PER_SOURCE:
                break
            try:
                cards = self._scrape_path(path)
            except Exception as e:  # noqa: BLE001
                logging.error("DealStream path %s error: %s", path, e)
                continue
            for card in cards:
                parsed = self._parse_listing(card)
                if parsed:
                    results.append(parsed)
                if len(results) >= MAX_RESULTS_PER_SOURCE:
                    break
            polite_sleep(2)
        return results

    def _scrape_path(self, path, pages=5):
        cards = []
        for page in range(1, pages + 1):
            url = f"{DEALSTREAM_BASE_URL}{path}"
            try:
                resp = get(self.session, url, params={"page": page})
            except Exception as e:  # noqa: BLE001
                logging.warning("DealStream page %s error: %s", page, e)
                break
            soup = BeautifulSoup(resp.text, "html.parser")
            page_cards = soup.select(
                "div.listing, article.listing, li.listing, div.search-result"
            )
            if not page_cards:
                break
            cards.extend(page_cards)
            polite_sleep(2)
        return cards

    def _parse_listing(self, card):
        try:
            name_el = card.find(["h3", "h2", "h4", "a"])
            name_text = name_el.get_text(strip=True) if name_el else "Unknown"

            text_blob = card.get_text(" ", strip=True)
            revenue = extract_currency(text_blob, ["revenue", "sales"])
            cash_flow = extract_currency(
                text_blob, ["cash flow", "ebitda", "sde", "net income"]
            )
            asking_price = extract_currency(text_blob, ["asking price", "price"])
            state = parse_state(text_blob)

            url_el = card.find("a", href=True)
            listing_url = ""
            if url_el:
                href = url_el["href"]
                listing_url = (
                    href if href.startswith("http") else f"{DEALSTREAM_BASE_URL}{href}"
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
            logging.warning("DealStream parse error: %s", e)
            return None
