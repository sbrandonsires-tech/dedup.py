"""Polite HTTP client used by every source module.

Guarantees, per the project's data-handling rules:
  * identifies with a real, contactable User-Agent;
  * respects robots.txt (per host, cached for the process);
  * rate-limits to one request per 2 seconds per host;
  * caches every raw response on disk so re-runs never re-fetch.

The on-disk cache is keyed by a hash of the full URL. Cached bodies are served
without touching the network, which makes `rescore` and repeat `run`s free and
keeps us well under any host's fair-access ceiling.
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.parse
import urllib.robotparser
from pathlib import Path

import requests

from . import settings

_LAST_REQUEST_AT: dict[str, float] = {}      # host -> monotonic timestamp
_ROBOTS: dict[str, urllib.robotparser.RobotFileParser] = {}


def _host(url: str) -> str:
    return urllib.parse.urlparse(url).netloc


def _cache_path(url: str, suffix: str) -> Path:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
    return settings.CACHE_DIR / f"{digest}{suffix}"


def _respect_rate_limit(host: str) -> None:
    last = _LAST_REQUEST_AT.get(host)
    if last is not None:
        wait = settings.RATE_LIMIT_SECONDS - (time.monotonic() - last)
        if wait > 0:
            time.sleep(wait)
    _LAST_REQUEST_AT[host] = time.monotonic()


def _robots_ok(url: str) -> bool:
    host = _host(url)
    rp = _ROBOTS.get(host)
    if rp is None:
        rp = urllib.robotparser.RobotFileParser()
        robots_url = f"{urllib.parse.urlparse(url).scheme}://{host}/robots.txt"
        try:
            _respect_rate_limit(host)
            resp = requests.get(
                robots_url,
                headers={"User-Agent": settings.user_agent()},
                timeout=settings.REQUEST_TIMEOUT,
            )
            if resp.status_code == 200:
                rp.parse(resp.text.splitlines())
            else:
                rp.parse([])  # no robots.txt -> allow
        except requests.RequestException:
            rp.parse([])      # unreachable robots.txt -> default allow
        _ROBOTS[host] = rp
    return rp.can_fetch(settings.user_agent(), url)


def get(url: str, *, params: dict | None = None, binary: bool = False,
        check_robots: bool = True, force: bool = False) -> bytes | str | None:
    """Fetch a URL through the cache. Returns text (default) or bytes.

    Returns None if robots.txt disallows the path or the request fails.
    """
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"

    suffix = ".bin" if binary else ".txt"
    cache_file = _cache_path(url, suffix)
    meta_file = _cache_path(url, ".meta.json")

    if cache_file.exists() and not force:
        return cache_file.read_bytes() if binary else cache_file.read_text("utf-8")

    if check_robots and not _robots_ok(url):
        print(f"  [robots] disallowed, skipping: {url}")
        return None

    _respect_rate_limit(_host(url))
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": settings.user_agent(),
                     "Accept-Encoding": "gzip, deflate"},
            timeout=settings.REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        print(f"  [http] request failed: {url} ({exc})")
        return None

    if resp.status_code != 200:
        print(f"  [http] HTTP {resp.status_code}: {url}")
        return None

    if binary:
        cache_file.write_bytes(resp.content)
    else:
        cache_file.write_text(resp.text, "utf-8")
    meta_file.write_text(json.dumps({
        "url": url,
        "status": resp.status_code,
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "content_type": resp.headers.get("Content-Type", ""),
    }), "utf-8")

    return resp.content if binary else resp.text


def get_json(url: str, *, params: dict | None = None, force: bool = False):
    raw = get(url, params=params, binary=False, force=force)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        print(f"  [http] non-JSON response: {url}")
        return None


def fetched_at(url: str, *, params: dict | None = None) -> str | None:
    """Return the ISO fetch timestamp recorded for a cached URL, if any."""
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    meta_file = _cache_path(url, ".meta.json")
    if meta_file.exists():
        try:
            return json.loads(meta_file.read_text("utf-8")).get("fetched_at")
        except (json.JSONDecodeError, OSError):
            return None
    return None
