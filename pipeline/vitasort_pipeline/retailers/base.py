"""Retailer adapter interface + polite HTTP.

Every adapter implements fetch_price(listing) -> {"price": float, "in_stock": bool} | None.
Returning None means "couldn't fetch" — the pipeline falls back to the last DB
snapshot, then the catalog seed price. A failed fetch never breaks the build.
"""
import time
import urllib.robotparser
from urllib.parse import urlparse

import requests

USER_AGENT = "VitaSortBot/0.1 (+https://github.com/YOUR_USER/vitasort; personal price tracker)"
MIN_SECONDS_BETWEEN_REQUESTS = 2.0
TIMEOUT = 15

_last_request_at: dict[str, float] = {}
_robots_cache: dict[str, urllib.robotparser.RobotFileParser] = {}


def _allowed_by_robots(url: str) -> bool:
    host = urlparse(url).netloc
    if host not in _robots_cache:
        rp = urllib.robotparser.RobotFileParser()
        try:
            rp.set_url(f"https://{host}/robots.txt")
            rp.read()
        except Exception:
            rp = None
        _robots_cache[host] = rp
    rp = _robots_cache[host]
    return True if rp is None else rp.can_fetch(USER_AGENT, url)


def polite_get(url: str) -> requests.Response | None:
    """GET with per-host rate limiting and robots.txt respect."""
    if not _allowed_by_robots(url):
        print(f"  robots.txt disallows fetching this page -> {url}")
        return None
    host = urlparse(url).netloc
    wait = MIN_SECONDS_BETWEEN_REQUESTS - (time.time() - _last_request_at.get(host, 0))
    if wait > 0:
        time.sleep(wait)
    _last_request_at[host] = time.time()
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
        resp.raise_for_status()
        return resp
    except requests.RequestException as e:
        print(f"  fetch failed for {url}: {e}")
        return None
