"""Name / state / domain normalization and the dedup key.

Dedup rule (from the spec): a company is identified by
    normalized_name + state + domain.
Two records collapse to one when all three agree. A blank domain still allows a
name+state match, which is the common case for registry / Census-derived rows.
"""

from __future__ import annotations

import re
import urllib.parse

# Common corporate suffixes and noise stripped before comparing names.
_SUFFIXES = [
    "incorporated", "inc", "corporation", "corp", "company", "co",
    "limited", "ltd", "llc", "llp", "lp", "plc", "pllc",
    "lc", "pc", "gmbh", "sa", "nv", "the",
]
_SUFFIX_RE = re.compile(
    r"\b(" + "|".join(re.escape(s) for s in _SUFFIXES) + r")\b", re.IGNORECASE
)
_NONALNUM_RE = re.compile(r"[^a-z0-9]+")


def normalize_name(name: str | None) -> str:
    if not name:
        return ""
    text = name.lower()
    text = text.replace("&", " and ")
    text = _SUFFIX_RE.sub(" ", text)
    text = _NONALNUM_RE.sub(" ", text)
    return " ".join(text.split())


def normalize_domain(value: str | None) -> str:
    """Reduce a URL or email host to a bare registrable domain, lowercased."""
    if not value:
        return ""
    value = value.strip().lower()
    if "@" in value:                      # an email address
        value = value.split("@", 1)[1]
    if "://" not in value:
        value = "http://" + value
    host = urllib.parse.urlparse(value).netloc or ""
    if host.startswith("www."):
        host = host[4:]
    return host


def normalize_state(state: str | None) -> str:
    return (state or "").strip().upper()[:2]


def dedup_key(name: str | None, state: str | None, domain: str | None) -> str:
    return "|".join((
        normalize_name(name),
        normalize_state(state),
        normalize_domain(domain),
    ))
