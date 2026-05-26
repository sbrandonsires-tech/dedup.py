# TRS Investments — Deal Sourcing Pipeline

Proprietary deal-sourcing pipeline for TRS Investments LLC, a lower-middle-market
industrial PE firm. Targets founder/family-owned North American businesses with
$4M–$30M revenue and $800K–$5M adjusted EBITDA in manufacturing, value-add
distribution, and B2B industrial services.

The pipeline pulls candidate companies from public sources, scores each one for
fit and exit-readiness, deduplicates them into a SQLite database, and writes a
formatted Excel workbook (Tier 1 / Tier 2 / All Records / Run Log) plus a weekly
HTML digest.

## Architecture

```
main.py            Orchestrator: run scrapers -> score -> dedup -> SQLite -> Excel
scheduler.py       Register recurring runs (Windows Task Scheduler / cron)
config.py          All tunable parameters; secrets read from the environment
scrapers/          One module per source (returns dicts matching the schema)
enrichment/        Per-company lookups (OSHA, UCC, EDGAR financials, website)
scoring/           Sector map, exit-readiness signals, master scorer
database/          SQLite schema + data-access layer
outputs/           Excel export + weekly HTML digest
logs/              run_log.txt and error_log.txt
```

## Data sources

| Source | Key needed | Role |
|---|---|---|
| SEC EDGAR | none | Company discovery by SIC; XBRL financials |
| SAM.gov | `SAM_API_KEY` | Federal contractor registry (size band, location) |
| OSHA | none | Inspection/violation history (stress signal) |
| Census CBP | `CENSUS_API_KEY` (optional) | Market sizing only — **not** a lead source |
| USPTO / PatentsView | `USPTO_API_KEY` (optional) | IP-activity enrichment signal only |
| BizBuySell / DealStream / AM&AA | none | Public broker listings — **see ToS note** |

### Terms-of-service note on broker scrapers
BizBuySell, DealStream, and AM&AA generally prohibit automated scraping in their
Terms of Use. These scrapers are included for completeness, but you are
responsible for confirming you have permission, honoring `robots.txt`, and
respecting rate limits before enabling them. Prefer a licensed feed where one
exists. The public-API sources (EDGAR / SAM / OSHA / Census / USPTO) have no
such restriction.

## Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure secrets (never commit real keys)
cp .env.example .env
#    then edit .env and fill in SAM_API_KEY / CENSUS_API_KEY (optional keys)

# 3. Initialize the database
python main.py --init

# 4. Test a single source
python main.py --source edgar

# 5. Full run
python main.py
```

### Secrets
API keys are read from environment variables (via `.env`, which is gitignored).
Nothing sensitive is committed to the repository. On Windows you can also set
them with `setx SAM_API_KEY ...` instead of using a `.env` file.

### Output location
The Excel workbook defaults to `outputs/TRS_Deal_Pipeline.xlsx`. To write it
elsewhere (e.g. your Windows deal folder), set `TRS_EXCEL_OUTPUT_PATH` in `.env`:

```
TRS_EXCEL_OUTPUT_PATH=C:\Users\Owner\trs-deal-sourcing\outputs\TRS_Deal_Pipeline.xlsx
```

## Common commands

```bash
python main.py                    # full run, all sources
python main.py --source sam       # one source
python main.py --tier 1           # only persist Tier 1 hits
python main.py --no-excel         # skip the Excel rewrite
python main.py --enrich "Acme Co" # OSHA enrichment for one company
python main.py --digest           # (re)generate / email the weekly digest
python scheduler.py               # print scheduling instructions
```

## Scoring

Each company is scored 0–100 across five weighted dimensions (weights in
`config.py`):

| Dimension | Weight | Notes |
|---|---|---|
| Sector fit | 30 | Exact SIC/NAICS match scores highest |
| Geography | 15 | Priority states > target states > other |
| Size fit | 25 | Revenue / employee band proximity to Fund III window |
| Ownership signal | 20 | Business age, lapsed registration, small-business flag |
| Stress signal | 10 | OSHA severity, UCC filings, days on market |

Tiers: **Tier 1** ≥ 70 (surfaced immediately), **Tier 2** 45–69 (watch list /
digest), **Tier 3** otherwise (logged only).

## Working the pipeline in Excel
- `Stage` defaults to `Identified`; update it to `Screened` / `Diligence` /
  `LOI` / `Closed` / `Passed` as deals progress.
- `Notes`, `Next Action`, `Next Action Date`, `Assigned To`, and `Stage` are
  user-managed: reruns **never** overwrite them once set.
- Listing URLs are clickable; Tier 1 rows are gold, Tier 2 slate.

## Known limitations
1. Revenue/EBITDA figures are proxies (SAM bands are self-reported; broker
   figures are seller-stated). Never present them as verified financials.
2. EDGAR names are legal entity names; one parent can appear several times.
3. OSHA data is address/establishment-matched, not entity-matched.
4. Broker listings are often anonymized and skew smaller than the TRS window.
5. This pipeline finds companies that *match criteria*; it does not confirm
   they are for sale. Most outreach is cold.
6. Dedup is by company name + state; subsidiaries/DBAs can still slip through —
   review Tier 1 hits manually before outreach.
```
