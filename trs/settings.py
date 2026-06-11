"""Central settings: paths and YAML-backed config loading.

All tunable values live in the two YAML files under config/. This module loads
them and derives portable paths so the project runs unchanged on any OS.
Nothing here requires an API key or a .env file: every data source in this
pipeline is publicly accessible without authentication.
"""

from __future__ import annotations

import functools
from pathlib import Path

import yaml

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
CACHE_DIR = BASE_DIR / "cache"          # raw HTTP responses, keyed by URL
DATA_DIR = BASE_DIR / "data"            # bulk downloads + the SQLite database
OUTPUTS_DIR = BASE_DIR / "outputs"      # generated Excel workbooks
LOGS_DIR = BASE_DIR / "logs"

WEIGHTS_PATH = CONFIG_DIR / "weights.yaml"
TARGETS_PATH = CONFIG_DIR / "targets.yaml"
DB_PATH = DATA_DIR / "trs.db"
SCHEMA_PATH = BASE_DIR / "trs" / "schema.sql"

# Polite scraping policy (applies to every outbound request).
RATE_LIMIT_SECONDS = 2.0                # one request per 2 seconds, per host
REQUEST_TIMEOUT = 30

for _d in (CACHE_DIR, DATA_DIR, OUTPUTS_DIR, LOGS_DIR):
    _d.mkdir(parents=True, exist_ok=True)


@functools.lru_cache(maxsize=1)
def weights() -> dict:
    with open(WEIGHTS_PATH, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@functools.lru_cache(maxsize=1)
def targets() -> dict:
    with open(TARGETS_PATH, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def user_agent() -> str:
    """SEC and most public data hosts require a descriptive, contactable UA."""
    firm = targets().get("firm", {})
    name = firm.get("name", "TRS Investments")
    email = firm.get("contact_email", "research@example.com")
    return f"{name} deal-sourcing research ({email})"


def reload() -> None:
    """Drop cached YAML so a rescore picks up edited config."""
    weights.cache_clear()
    targets.cache_clear()
