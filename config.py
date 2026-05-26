"""
TRS Investments — Deal Sourcing Pipeline configuration.

All tunable parameters live here. No hardcoded values elsewhere in the codebase.

Secrets (API keys) are read from environment variables so they never get
committed to source control. Copy `.env.example` to `.env` and fill in your
keys, or export them in your shell. See README.md for details.

Paths are derived from this file's location so the project runs unchanged on
Linux, macOS, or Windows. Override the Excel output location with the
TRS_EXCEL_OUTPUT_PATH environment variable if you want it written elsewhere
(e.g. C:\\Users\\Owner\\trs-deal-sourcing\\outputs\\TRS_Deal_Pipeline.xlsx).
"""

import os
from pathlib import Path

# Load a local .env file if python-dotenv is installed. Optional: the pipeline
# also works if the variables are exported in the environment directly.
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover - dotenv is optional
    pass


# ── PATHS (portable) ──────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
SCRAPERS_DIR = BASE_DIR / "scrapers"
OUTPUTS_DIR = BASE_DIR / "outputs"
LOGS_DIR = BASE_DIR / "logs"
DATABASE_DIR = BASE_DIR / "database"

DB_PATH = Path(os.getenv("TRS_DB_PATH", DATABASE_DIR / "trs_pipeline.db"))
SCHEMA_PATH = DATABASE_DIR / "schema.sql"
EXCEL_OUTPUT_PATH = Path(
    os.getenv("TRS_EXCEL_OUTPUT_PATH", OUTPUTS_DIR / "TRS_Deal_Pipeline.xlsx")
)
DIGEST_OUTPUT_PATH = OUTPUTS_DIR / "weekly_digest.html"
RUN_LOG_PATH = LOGS_DIR / "run_log.txt"
ERROR_LOG_PATH = LOGS_DIR / "error_log.txt"

# Ensure runtime directories exist on import so first run never fails on a
# missing folder.
for _d in (OUTPUTS_DIR, LOGS_DIR, DATABASE_DIR):
    _d.mkdir(parents=True, exist_ok=True)


# ── FIRM IDENTITY ──────────────────────────────────────────────────────────────
FIRM_NAME = "TRS Investments LLC"
CONTACT_EMAIL = "brandon@trsinvestments.com"
# Sent in API User-Agent headers (SEC etiquette requires a contact address).
USER_AGENT = f"{FIRM_NAME} {CONTACT_EMAIL}"


# ── FUND III ACQUISITION CRITERIA ─────────────────────────────────────────────
REVENUE_MIN = 4_000_000  # $4M
REVENUE_MAX = 30_000_000  # $30M
EBITDA_MIN = 800_000  # $800K
EBITDA_MAX = 5_000_000  # $5M
EMPLOYEE_MIN = 10
EMPLOYEE_MAX = 250


# ── CURRENT SOURCING FOCUS ────────────────────────────────────────────────────
# A narrower preference band *within* the Fund III criteria above. The size
# score peaks for companies in this band; companies in the full range still
# score (lower) and nothing is excluded. Widen these back toward EBITDA_MIN/MAX
# when you want the full range again.
EBITDA_TARGET_MIN = 1_000_000  # $1M
EBITDA_TARGET_MAX = 2_000_000  # $2M
# When EBITDA is unknown (most records), approximate the focus band by revenue
# using a typical lower-middle-market industrial EBITDA margin range.
ASSUMED_EBITDA_MARGIN_LOW = 0.10
ASSUMED_EBITDA_MARGIN_HIGH = 0.15
PREFERRED_REVENUE_MIN = round(EBITDA_TARGET_MIN / ASSUMED_EBITDA_MARGIN_HIGH)  # ~$6.7M
PREFERRED_REVENUE_MAX = round(EBITDA_TARGET_MAX / ASSUMED_EBITDA_MARGIN_LOW)   # $20M


# ── TARGET GEOGRAPHIES ────────────────────────────────────────────────────────
TARGET_STATES = [
    "AL", "AR", "AZ", "CO", "FL", "GA", "IA", "ID", "IL", "IN",
    "KS", "KY", "LA", "MI", "MN", "MO", "MS", "MT", "NC", "ND",
    "NE", "NM", "OH", "OK", "OR", "SC", "SD", "TN", "TX", "UT",
    "VA", "WI", "WV", "WY",
]
# Note: Northeast and California de-prioritized but not excluded.
PRIORITY_STATES = ["TX", "FL", "OH", "IL", "IN", "TN", "NC", "GA", "MI"]


# ── TARGET SIC CODES (SEC/EDGAR) ──────────────────────────────────────────────
SIC_TARGET_CODES = [
    # Fabricated Metal
    "3460", "3462", "3463", "3469", "3470", "3480", "3490",
    "3492", "3493", "3494", "3495", "3496", "3497", "3498", "3499",
    # Industrial Machinery
    "3510", "3520", "3530", "3540", "3550", "3560", "3562",
    "3563", "3564", "3565", "3566", "3567", "3568", "3569",
    # Electrical / Electronics
    "3610", "3612", "3613", "3620", "3621", "3625", "3629",
    "3630", "3640", "3643", "3644", "3645", "3646", "3648",
    "3669", "3670", "3672", "3675", "3676", "3677", "3678", "3679",
    # Plastics / Rubber
    "3050", "3060", "3079", "3080", "3085", "3086", "3087", "3089",
    # Primary Metals
    "3310", "3312", "3316", "3317", "3321", "3325", "3330", "3334",
    "3350", "3353", "3354", "3355", "3356", "3357", "3363", "3364",
    # Instruments
    "3812", "3821", "3822", "3823", "3824", "3825", "3826", "3827",
]

# Value-Add Distribution
SIC_DISTRIBUTION = [
    "5040", "5041", "5042", "5043", "5044", "5045", "5046", "5047",
    "5063", "5064", "5065",  # Electrical apparatus and equipment
    "5072", "5074", "5075", "5078",
    "5080", "5082", "5084", "5085",  # Industrial machinery and equipment
    "5090", "5091", "5093", "5094", "5099",
]

# B2B Industrial Services
SIC_SERVICES = [
    "7389",  # Services to buildings and industrial
    "7699",  # Repair shops NEC
    "8711", "8712", "8713",  # Engineering
    "8999",
]

ALL_TARGET_SIC = SIC_TARGET_CODES + SIC_DISTRIBUTION + SIC_SERVICES


# ── TARGET NAICS CODES (SAM.GOV / CENSUS) ─────────────────────────────────────
NAICS_TARGET = [
    "332",  # Fabricated Metal Product Manufacturing
    "333",  # Machinery Manufacturing
    "334",  # Computer and Electronic Product Manufacturing
    "335",  # Electrical Equipment Manufacturing
    "336",  # Transportation Equipment Manufacturing
    "339",  # Miscellaneous Manufacturing
    "423",  # Merchant Wholesalers, Durable Goods
    "424",  # Merchant Wholesalers, Nondurable Goods
    "811",  # Repair and Maintenance
    "541330",  # Engineering Services
    "541614",  # Process and Logistics Consulting
]


# ── SCORING WEIGHTS ───────────────────────────────────────────────────────────
WEIGHT_SECTOR_FIT = 30  # Out of 100
WEIGHT_GEOGRAPHY = 15
WEIGHT_SIZE_FIT = 25
WEIGHT_OWNERSHIP_SIGNAL = 20
WEIGHT_STRESS_SIGNAL = 10

TIER_1_THRESHOLD = 70  # Score >= 70: Tier 1 sheet, surfaced immediately
TIER_2_THRESHOLD = 45  # Score 45-69: weekly digest / watch list
TIER_3_THRESHOLD = 0  # Score < 45: logged only, not surfaced


# ── API KEYS AND ENDPOINTS ────────────────────────────────────────────────────
# Keys come from the environment. Empty string means "not configured"; scrapers
# that need a key will skip with a clear log message rather than crash.

# SEC EDGAR — free, no key required.
EDGAR_BROWSE_URL = "https://www.sec.gov/cgi-bin/browse-edgar"
EDGAR_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
EDGAR_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
EDGAR_FULLTEXT_URL = "https://efts.sec.gov/LATEST/search-index"

# SAM.gov — free, register at sam.gov for an API key.
SAM_API_KEY = os.getenv("SAM_API_KEY", "")
SAM_ENTITY_URL = "https://api.sam.gov/entity-information/v3/entities"

# OSHA — free, no key required.
OSHA_BASE_URL = "https://data.osha.gov/api/1.0/inspection"

# Census Bureau — free, register at api.census.gov.
CENSUS_API_KEY = os.getenv("CENSUS_API_KEY", "")
CENSUS_CBP_URL = "https://api.census.gov/data/{year}/cbp"
CENSUS_CBP_YEAR = int(os.getenv("CENSUS_CBP_YEAR", "2022"))

# USPTO / PatentsView — free, no key required.
USPTO_PATENT_URL = "https://search.patentsview.org/api/v1/patent/"
USPTO_TRADEMARK_URL = "https://developer.uspto.gov/ds-api/trademark/v1/records"

# Broker listing sites (HTML scraping). See README for the Terms-of-Service note.
BIZBUYSELL_BASE_URL = "https://www.bizbuysell.com"
DEALSTREAM_BASE_URL = "https://dealstream.com"
AMAA_BASE_URL = "https://www.amaaonline.com"


# ── EMAIL (weekly digest) ─────────────────────────────────────────────────────
# Optional. If SMTP settings are absent, digest.py writes the HTML file only.
WEEKLY_DIGEST_RECIPIENTS = [
    r.strip()
    for r in os.getenv(
        "WEEKLY_DIGEST_RECIPIENTS",
        "brandon@trsinvestments.com,bob@trsinvestments.com",
    ).split(",")
    if r.strip()
]
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", CONTACT_EMAIL)


# ── RUN SETTINGS ──────────────────────────────────────────────────────────────
MAX_RESULTS_PER_SOURCE = int(os.getenv("MAX_RESULTS_PER_SOURCE", "500"))
REQUEST_DELAY_SECONDS = float(os.getenv("REQUEST_DELAY_SECONDS", "1.0"))
REQUEST_TIMEOUT_SECONDS = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "30"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")  # INFO or DEBUG
