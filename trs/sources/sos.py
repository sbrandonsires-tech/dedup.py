"""State Secretary of State business registries.

Goal (from the spec): incorporation year is the company-age signal, and registry
search yields private company names. In practice the public registries for our
test-scope states are NOT keyless-automatable:

  * Illinois SOS business search is behind a WAF and returns HTTP 403 to
    non-browser clients; there is no free bulk download.
  * Indiana INBiz public search (bsd.sos.in.gov) gates every query behind Google
    reCAPTCHA, enforced server-side. Automating around a CAPTCHA would mean
    circumventing an access control, which violates this project's polite-scraping
    mandate, so we do not attempt it. Indiana's only programmatic route is a paid
    Bulk Data Services subscription.

This module therefore probes the keyless route, detects the wall, and records the
gap honestly in run_log rather than pretending to ingest. States that DO offer
open data (Socrata / CKAN portals or free bulk files) can be added to
KEYLESS_SOURCES and will flow through `_ingest_open_data` without code changes
elsewhere.
"""

from __future__ import annotations

from .. import db, http

# Public-search endpoints we probe to confirm/refresh the access status. We send
# a single polite request and read the access posture; we never solve a CAPTCHA.
BLOCKED_SOURCES = {
    "IL": {
        "url": "https://apps.ilsos.gov/corporatellc/",
        "barrier": "WAF / HTTP 403 to non-browser clients; no free bulk file",
    },
    "IN": {
        "url": "https://bsd.sos.in.gov/publicbusinesssearch",
        "barrier": "Google reCAPTCHA gate (server-enforced); paid Bulk Data only",
    },
}

# Map of states that expose keyless open data. Empty until a usable one is found
# that is reachable from the run environment. Shape:
#   "OH": {"url": "https://data.ohio.gov/resource/<id>.json", "parser": fn}
KEYLESS_SOURCES: dict[str, dict] = {}


def _probe(state: str, cfg: dict) -> str:
    """Single polite request to confirm the access barrier still stands."""
    raw = http.get(cfg["url"], check_robots=True)
    status = "reachable but gated" if raw else "blocked / unreachable"
    return f"{state}: {cfg['barrier']} ({status})"


def _ingest_open_data(conn, state: str, cfg: dict) -> int:  # pragma: no cover
    """Placeholder for states with keyless open-data feeds (none wired yet)."""
    return 0


def run(conn, *, states: list[str]) -> dict:
    print(f"[sos] checking state registries: {states}")
    gap_notes = []
    ingested = 0

    for state in states:
        if state in KEYLESS_SOURCES:
            ingested += _ingest_open_data(conn, state, KEYLESS_SOURCES[state])
        elif state in BLOCKED_SOURCES:
            note = _probe(state, BLOCKED_SOURCES[state])
            gap_notes.append(note)
            print(f"  data gap -> {note}")
        else:
            gap_notes.append(f"{state}: no keyless source configured")
            print(f"  no keyless source configured for {state}")

    notes = ("State registries are CAPTCHA/WAF gated for this scope; no keyless "
             "ingestion. " + " | ".join(gap_notes)) if gap_notes else \
            f"Ingested {ingested} entities from open-data feeds."
    db.log_run(conn, "sos", pulled=ingested, new=ingested, notes=notes)
    print(f"  {notes}")
    return {"ingested": ingested, "gaps": gap_notes}
