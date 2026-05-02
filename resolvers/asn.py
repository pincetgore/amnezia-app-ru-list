"""
ASN-to-prefix resolver.

Fetches all announced IPv4 prefixes for a given Autonomous System Number (ASN).
Primary source: RIPE NCC RISstat API.
Fallback: HTML scraping from bgp.he.net.

Rate limiting is enforced globally (min 1 second between requests) to avoid
being throttled by upstream APIs.
"""

import logging
import re
import time
from ipaddress import IPv4Network

import requests

logger = logging.getLogger(__name__)

# RIPE NCC RISstat API endpoint for announced prefixes
RIPE_API_URL = "https://stat.ripe.net/data/announced-prefixes/data.json"

# Hurricane Electric BGP Toolkit — used as a fallback when RIPE returns no data
HE_BGP_URL = "https://bgp.he.net/AS{asn}#_prefixes4"

# Timestamp of the last API request (used for rate limiting)
_last_request_time = 0.0

# Reuse connection for performance
_session = requests.Session()
_session.headers.update({"User-Agent": "Mozilla/5.0 (ru-bypass-list generator)"})


def _rate_limit():
    """Enforce a minimum 1-second gap between consecutive API requests."""
    global _last_request_time
    elapsed = time.time() - _last_request_time
    if elapsed < 1.0:
        time.sleep(1.0 - elapsed)
    _last_request_time = time.time()


def get_prefixes_ripe(asn: int, timeout: int = 30) -> list[IPv4Network] | None:
    """Fetch all announced IPv4 prefixes for an ASN from RIPE NCC API.

    Returns an empty list on failure (network error, invalid response, etc.)
    so the caller can fall through to the bgp.he.net fallback.
    """
    _rate_limit()
    try:
        resp = _session.get(
            RIPE_API_URL,
            params={"resource": f"AS{asn}"},
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()

        prefixes = []
        for entry in data.get("data", {}).get("prefixes", []):
            prefix = entry.get("prefix", "")
            # Skip IPv6 prefixes (contain colons)
            if ":" in prefix:
                continue
            try:
                prefixes.append(IPv4Network(prefix, strict=False))
            except ValueError:
                logger.warning("Invalid prefix from RIPE for AS%d: %s", asn, prefix)
        logger.info("AS%d: got %d prefixes from RIPE", asn, len(prefixes))
        return prefixes

    except requests.RequestException as e:
        logger.warning("RIPE API failed for AS%d: %s", asn, e)
        return None


def get_prefixes_he(asn: int, timeout: int = 30) -> list[IPv4Network]:
    """Scrape announced IPv4 prefixes from bgp.he.net (fallback).

    Parses CIDR notation strings from the HTML response using a regex.
    Less reliable than RIPE but useful when RIPE returns empty results.
    """
    _rate_limit()
    try:
        resp = _session.get(
            HE_BGP_URL.format(asn=asn),
            timeout=timeout,
        )
        resp.raise_for_status()

        # Extract all IPv4 CIDR strings from the page HTML
        pattern = r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}/\d{1,2})'
        raw = re.findall(pattern, resp.text)
        prefixes = []
        for p in raw:
            try:
                prefixes.append(IPv4Network(p, strict=False))
            except ValueError:
                pass
        logger.info("AS%d: got %d prefixes from bgp.he.net (fallback)", asn, len(prefixes))
        return prefixes

    except requests.RequestException as e:
        logger.warning("bgp.he.net failed for AS%d: %s", asn, e)
        return []


def resolve_asn(asn: int) -> list[IPv4Network]:
    """Resolve all IPv4 prefixes for an ASN.

    Tries RIPE NCC first; falls back to bgp.he.net if RIPE returns no results.
    """
    prefixes = get_prefixes_ripe(asn)
    if prefixes is None:
        prefixes = get_prefixes_he(asn)
    return prefixes or []
