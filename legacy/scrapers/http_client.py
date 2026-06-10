"""
Shared HTTP helper for all scrapers.

Provides a requests.Session with automatic retry/backoff on transient errors,
a default User-Agent identifying TRS (SEC etiquette), and convenience wrappers
that apply the configured timeout. Centralizing this keeps every scraper from
re-implementing the same retry and header boilerplate.
"""

import logging
import time

import requests
from requests.adapters import HTTPAdapter

try:
    from urllib3.util.retry import Retry
except ImportError:  # pragma: no cover
    from requests.packages.urllib3.util.retry import Retry  # type: ignore

from config import USER_AGENT, REQUEST_TIMEOUT_SECONDS, REQUEST_DELAY_SECONDS


def make_session(extra_headers=None, retry_statuses=(429, 500, 502, 503, 504)) -> requests.Session:
    session = requests.Session()
    headers = {"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"}
    if extra_headers:
        headers.update(extra_headers)
    session.headers.update(headers)
    retry = Retry(
        total=3,
        backoff_factor=1.0,
        status_forcelist=tuple(retry_statuses),
        allowed_methods=frozenset({"GET"}),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def polite_sleep(multiplier: float = 1.0):
    """Pause between requests to respect rate limits."""
    time.sleep(REQUEST_DELAY_SECONDS * multiplier)


def get(session: requests.Session, url: str, **kwargs):
    """GET with the configured timeout applied. Raises for HTTP errors."""
    kwargs.setdefault("timeout", REQUEST_TIMEOUT_SECONDS)
    resp = session.get(url, **kwargs)
    resp.raise_for_status()
    return resp


def get_json(session: requests.Session, url: str, **kwargs):
    resp = get(session, url, **kwargs)
    return resp.json()
