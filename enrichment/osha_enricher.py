"""
OSHA enricher — pull OSHA history for a known company.

Thin wrapper around OSHAScraper.enrich_company so enrichment code can stay
decoupled from the discovery scraper. Returns the OSHA fields (violation
count, last inspection date, severity) ready to merge into a company record.
"""

from scrapers.osha_scraper import OSHAScraper


class OSHAEnricher:
    def __init__(self):
        self._scraper = OSHAScraper()

    def enrich(self, company_name, state=None):
        return self._scraper.enrich_company(company_name, state=state)
