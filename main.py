"""
TRS Deal Sourcing Pipeline — master orchestrator.

Usage:
    python main.py                      # full run, all sources
    python main.py --source edgar       # single source only
    python main.py --tier 1             # only persist a specific tier
    python main.py --enrich "Acme Co"   # OSHA-enrich a named company
    python main.py --digest             # (re)generate / send the weekly digest
    python main.py --init               # create the database and exit
    python main.py --no-excel           # skip the Excel rewrite

Each source is scored, deduplicated on (company_name, state), and written to
SQLite. Tier 1 / Tier 2 are surfaced in the Excel workbook after the run.
"""

import argparse
import logging
import time
from datetime import datetime

from config import LOG_LEVEL, RUN_LOG_PATH, ERROR_LOG_PATH
from database.db import Database
from scoring.scorer import Scorer
from outputs.excel_export import ExcelExport
from outputs.digest import DigestGenerator

from scrapers.edgar_scraper import EDGARScraper
from scrapers.sam_scraper import SAMScraper
from scrapers.osha_scraper import OSHAScraper
from scrapers.census_scraper import CensusScraper
from scrapers.uspto_scraper import USPTOScraper
from scrapers.bizbuysell_scraper import BizBuySellScraper
from scrapers.dealstream_scraper import DealStreamScraper
from scrapers.amaa_scraper import AMAAScraper


def _configure_logging():
    root = logging.getLogger()
    root.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    run_handler = logging.FileHandler(RUN_LOG_PATH, encoding="utf-8")
    run_handler.setLevel(logging.INFO)
    run_handler.setFormatter(fmt)

    err_handler = logging.FileHandler(ERROR_LOG_PATH, encoding="utf-8")
    err_handler.setLevel(logging.ERROR)
    err_handler.setFormatter(fmt)

    root.handlers.clear()
    root.addHandler(run_handler)
    root.addHandler(err_handler)


SCRAPER_REGISTRY = {
    "edgar": EDGARScraper,
    "sam": SAMScraper,
    "osha": OSHAScraper,
    "census": CensusScraper,
    "uspto": USPTOScraper,
    "bizbuysell": BizBuySellScraper,
    "dealstream": DealStreamScraper,
    "amaa": AMAAScraper,
}


def run_pipeline(source_filter=None, tier_filter=None, write_excel=True):
    db = Database()
    db.initialize()
    scorer = Scorer()

    print(f"\n{'=' * 60}")
    print(f"TRS DEAL SOURCING PIPELINE — {datetime.now():%Y-%m-%d %H:%M}")
    print(f"{'=' * 60}\n")

    registry = SCRAPER_REGISTRY
    if source_filter:
        if source_filter not in registry:
            print(f"Unknown source '{source_filter}'. "
                  f"Choices: {', '.join(registry)}")
            return
        registry = {source_filter: registry[source_filter]}

    total_new = total_updated = total_tier1 = 0

    for name, scraper_cls in registry.items():
        print(f"Running {name.upper()} scraper...")
        source_start = time.time()
        new_count = updated_count = tier1_count = tier2_count = 0
        error_text = ""
        pulled = 0
        try:
            records = scraper_cls().run()
            pulled = len(records)
            print(f"  Pulled {pulled} records")

            for record in records:
                scored = scorer.score(record)
                if tier_filter and scored["tier"] != tier_filter:
                    continue

                if db.exists(scored.get("company_name"), scored.get("state")):
                    if db.update(scored):
                        updated_count += 1
                    continue

                db.insert(scored)
                new_count += 1
                if scored["tier"] == 1:
                    tier1_count += 1
                    print(f"  *** TIER 1: {scored['company_name']} "
                          f"({scored.get('state')}) — Score {scored['score_total']}")
                elif scored["tier"] == 2:
                    tier2_count += 1
        except Exception as e:  # noqa: BLE001 - isolate per-source failures
            error_text = str(e)
            logging.error("Pipeline error on %s: %s", name, e)
            print(f"  ERROR: {e}")

        duration = time.time() - source_start
        db.log_run(
            source=name,
            records_pulled=pulled,
            records_new=new_count,
            records_updated=updated_count,
            tier1_count=tier1_count,
            tier2_count=tier2_count,
            errors=error_text,
            duration_seconds=duration,
        )
        print(f"  New: {new_count} | Updated: {updated_count} | "
              f"Tier 1: {tier1_count} | Tier 2: {tier2_count}")
        total_new += new_count
        total_updated += updated_count
        total_tier1 += tier1_count

    if write_excel:
        print("\nWriting Excel pipeline file...")
        ExcelExport(db).write()

    print(f"\n{'=' * 60}")
    print("PIPELINE COMPLETE")
    print(f"Total new: {total_new} | updated: {total_updated} | "
          f"Tier 1: {total_tier1}")
    print(f"{'=' * 60}\n")


def enrich_company(name):
    """Quick standalone OSHA enrichment for a named company."""
    from enrichment.osha_enricher import OSHAEnricher

    print(f"OSHA enrichment for: {name}")
    result = OSHAEnricher().enrich(name)
    for k, v in result.items():
        print(f"  {k}: {v}")
    return result


if __name__ == "__main__":
    _configure_logging()
    parser = argparse.ArgumentParser(description="TRS Deal Sourcing Pipeline")
    parser.add_argument("--source", help="Run a single source only")
    parser.add_argument("--tier", type=int, help="Only persist this tier (1/2/3)")
    parser.add_argument("--enrich", help="OSHA-enrich a named company and exit")
    parser.add_argument("--digest", action="store_true", help="Generate/send digest")
    parser.add_argument("--init", action="store_true", help="Init database and exit")
    parser.add_argument("--no-excel", action="store_true", help="Skip Excel rewrite")
    args = parser.parse_args()

    if args.init:
        Database().initialize()
        print("Database initialized.")
    elif args.enrich:
        enrich_company(args.enrich)
    elif args.digest:
        DigestGenerator().send()
    else:
        run_pipeline(
            source_filter=args.source,
            tier_filter=args.tier,
            write_excel=not args.no_excel,
        )
