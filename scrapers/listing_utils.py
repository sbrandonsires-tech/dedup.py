"""
Shared parsing helpers for broker-listing scrapers (BizBuySell / DealStream /
AM&AA). These sites publish seller-stated figures in free text, so extraction
is best-effort and defensive.
"""

import re

_STATE_ABBRS = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID",
    "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS",
    "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK",
    "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV",
    "WI", "WY", "DC",
}

_STATE_NAMES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN",
    "mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE",
    "nevada": "NV", "new hampshire": "NH", "new jersey": "NJ",
    "new mexico": "NM", "new york": "NY", "north carolina": "NC",
    "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR",
    "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
}


def extract_currency(text: str, keywords):
    """Find a dollar figure near any of the keywords. Returns float or None."""
    text = (text or "").lower()
    for kw in keywords:
        pattern = rf"{re.escape(kw)}[:\s]*\$?\s*([\d,]+(?:\.\d+)?)\s*([kKmM]?)"
        m = re.search(pattern, text)
        if not m:
            continue
        num = float(m.group(1).replace(",", ""))
        suffix = m.group(2).upper()
        if suffix == "K":
            num *= 1_000
        elif suffix == "M":
            num *= 1_000_000
        return num
    return None


def parse_state(location_text: str):
    """Pull a 2-letter state code from a location string."""
    text = (location_text or "").strip()
    if not text:
        return ""
    # Full state names first (e.g. "Dallas, Texas").
    low = text.lower()
    for name, abbr in _STATE_NAMES.items():
        if name in low:
            return abbr
    # Trailing 2-letter abbreviation (e.g. "Dallas, TX").
    for token in reversed(re.findall(r"\b([A-Z]{2})\b", text)):
        if token in _STATE_ABBRS:
            return token
    return ""
