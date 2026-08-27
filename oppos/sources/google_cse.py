"""Google Custom Search source for private-sector RFP discovery.

Uses Google's Custom Search JSON API to find RFPs posted directly on
organization websites (hospitals, universities, enterprises).  A domain
blocklist filters out aggregator/paywall sites so only direct-source
postings enter the pipeline.

Quota: 100 free queries/day, each returning up to 10 results.
The module rotates through search terms across runs, tracking progress
in the ``meta`` table.

Setup:
  1. Create a Programmable Search Engine at programmablesearchengine.google.com
     - Search the entire web
     - In the exclusion list, add the domains from _AGGREGATOR_DOMAINS
  2. Get your API key from console.cloud.google.com (Custom Search API)
  3. Set GOOGLE_CSE_API_KEY and GOOGLE_CSE_CX in .env
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, date
from typing import Any
from urllib.parse import urlparse

import httpx

from oppos.config import GOOGLE_CSE_API_KEY, GOOGLE_CSE_CX, GOOGLE_CSE_DAILY_LIMIT
from oppos.storage.db import get_meta, set_meta, is_seen

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Search terms — rotated across runs to stay within free-tier quota
# ---------------------------------------------------------------------------

_SEARCH_TERMS: list[str] = [
    # Core workflow automation
    '"request for proposal" workflow automation',
    '"request for proposal" case management software',
    '"request for proposal" document management system',
    '"request for proposal" business process automation',
    '"request for proposal" forms management',
    # Finance / CapEx
    '"request for proposal" capital expenditure approval',
    '"request for proposal" invoice processing automation',
    '"request for proposal" purchase requisition system',
    '"request for proposal" accounts payable automation',
    # HR / Operations
    '"request for proposal" employee onboarding system',
    '"request for proposal" contract management software',
    '"request for proposal" incident reporting system',
    '"request for proposal" field service management',
    '"request for proposal" compliance workflow',
    # Broader terms (alternate phrasing)
    '"RFP" workflow automation software',
    '"request for proposal" records management system',
    '"request for proposal" permit management software',
    '"request for proposal" leave management system',
    '"request for proposal" electronic signature workflow',
]

_BATCH_SIZE = 10  # queries per run (10 × 10 results = 100 URLs max)

# ---------------------------------------------------------------------------
# Aggregator / paywall domain blocklist
# ---------------------------------------------------------------------------

_AGGREGATOR_DOMAINS: frozenset[str] = frozenset({
    # Major bid aggregators
    "bidnet.com",
    "govwin.com",
    "bidsync.com",
    "bonfirehub.com",
    "bidexpress.com",
    "publicpurchase.com",
    "merx.com",
    "bidocean.com",
    "rfpdb.com",
    "findmyrfp.com",
    "governmentbids.com",
    "bidspotter.com",
    "negometrix.com",
    "tendersinfo.com",
    "globaltenders.com",
    "ustenders.com",
    "rfpmart.com",
    "epiqsource.com",
    "procureport.com",
    "onvia.com",
    "deltek.com",
    "govspend.com",
    "smartprocure.us",
    "opengov.com",
    "procurenow.com",
    "ion-wave.net",
    "planetbids.com",
    "centurion-e.com",
    "demandstar.com",
    "vendorregistry.com",
    "purchasing.org",
    "ebidexchange.com",
    "bidcontract.com",
    "bidhubusa.com",
    # Periscope-family
    "periscope-holdings.com",
    "periscopeholdings.com",
    # General aggregator / news noise
    "fpds.gov",
    "sam.gov",
    "grants.gov",
    "gsa.gov",
})


def _is_aggregator(url: str) -> bool:
    """Check if a URL belongs to a blocked aggregator domain."""
    netloc = urlparse(url).netloc.lower()
    # Strip www. prefix
    if netloc.startswith("www."):
        netloc = netloc[4:]
    # Check exact match and parent domain
    return netloc in _AGGREGATOR_DOMAINS or any(
        netloc.endswith("." + d) for d in _AGGREGATOR_DOMAINS
    )


# ---------------------------------------------------------------------------
# Google Custom Search API
# ---------------------------------------------------------------------------

_API_URL = "https://www.googleapis.com/customsearch/v1"


def _daily_counter_key() -> str:
    return f"google_cse_calls_{date.today().isoformat()}"


def _get_daily_calls() -> int:
    val = get_meta(_daily_counter_key())
    return int(val) if val else 0


def _increment_daily_calls() -> int:
    count = _get_daily_calls() + 1
    set_meta(_daily_counter_key(), str(count))
    return count


def _search(query: str) -> list[dict]:
    """Execute a single Google CSE query. Returns raw result items."""
    if _get_daily_calls() >= GOOGLE_CSE_DAILY_LIMIT:
        logger.warning("Google CSE daily limit (%d) reached — skipping", GOOGLE_CSE_DAILY_LIMIT)
        return []

    params = {
        "key": GOOGLE_CSE_API_KEY,
        "cx": GOOGLE_CSE_CX,
        "q": query,
        "num": 10,
        "dateRestrict": "d14",  # last 14 days
    }

    try:
        resp = httpx.get(_API_URL, params=params, timeout=15.0)
        resp.raise_for_status()
        _increment_daily_calls()
        data = resp.json()
        items = data.get("items", [])
        logger.info("Google CSE: '%s' → %d results", query[:50], len(items))
        return items
    except httpx.HTTPError as e:
        logger.error("Google CSE API error: %s", e)
        return []


# ---------------------------------------------------------------------------
# Result processing
# ---------------------------------------------------------------------------

def _make_source_id(url: str) -> str:
    return f"gcse-{hashlib.sha256(url.encode()).hexdigest()[:12]}"


def _process_result(item: dict) -> dict[str, Any] | None:
    """Convert a Google CSE result item into a preliminary opportunity dict.

    Does NOT fetch the full page here — that's done in fetch_opportunities()
    after dedup.  This just builds a lightweight record from the snippet.
    """
    url = item.get("link", "")
    if not url:
        return None

    if _is_aggregator(url):
        logger.debug("Google CSE: skipping aggregator URL %s", url[:80])
        return None

    source_id = _make_source_id(url)

    # Skip if already in the database
    if is_seen(source_id):
        return None

    title = item.get("title", "").strip()
    snippet = item.get("snippet", "").strip()

    # Basic sanity: skip if title/snippet are too thin
    if len(title) < 10 and len(snippet) < 20:
        return None

    return {
        "source_id": source_id,
        "source": "google_cse",
        "url": url,
        "title": title,
        "description": snippet,
        # Placeholders — will be enriched by extract_metadata after full page fetch
        "agency": "",
        "solicitation_number": "",
        "notice_type": "",
        "posted_date": "",
        "response_deadline": "",
        "office": "",
        "naics_code": "",
        "set_aside": "",
        "classification_code": "",
        "resource_links": [],
        "point_of_contact": {},
        "place_of_performance": "",
        "raw": {"google_title": title, "google_snippet": snippet},
    }


# ---------------------------------------------------------------------------
# Page enrichment — fetch full page + extract metadata with Claude
# ---------------------------------------------------------------------------

def _enrich_opportunity(opp: dict[str, Any]) -> dict[str, Any]:
    """Fetch the full page and extract structured metadata with Claude."""
    from oppos.sources.manual import fetch_page, extract_metadata

    url = opp["url"]
    logger.info("Google CSE: enriching %s", url[:80])

    page = fetch_page(url)
    if page.get("error"):
        logger.warning("Google CSE: could not fetch %s: %s", url[:60], page["error"])
        # Keep the snippet-based record — still scorable
        return opp

    text = page.get("text", "")
    if not text or len(text.strip()) < 50:
        return opp

    # Extract structured fields with Claude
    meta = extract_metadata(text, url)

    # Merge extracted fields (prefer extracted over placeholder)
    if meta.get("title"):
        opp["title"] = meta["title"]
    if meta.get("agency"):
        opp["agency"] = meta["agency"]
    if meta.get("description"):
        opp["description"] = meta["description"]
    if meta.get("solicitation_number"):
        opp["solicitation_number"] = meta["solicitation_number"]
    if meta.get("notice_type"):
        opp["notice_type"] = meta["notice_type"]
    if meta.get("posted_date"):
        opp["posted_date"] = meta["posted_date"]
    if meta.get("response_deadline"):
        opp["response_deadline"] = meta["response_deadline"]
    if meta.get("place_of_performance"):
        opp["place_of_performance"] = meta["place_of_performance"]
    if meta.get("office"):
        opp["office"] = meta["office"]
    if meta.get("naics_code"):
        opp["naics_code"] = meta["naics_code"]
    if meta.get("set_aside"):
        opp["set_aside"] = meta["set_aside"]
    if meta.get("contact_name") or meta.get("contact_email"):
        opp["point_of_contact"] = {
            "name": meta.get("contact_name", ""),
            "email": meta.get("contact_email", ""),
            "phone": meta.get("contact_phone", ""),
        }

    return opp


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_opportunities(limit: int = 50) -> list[dict[str, Any]]:
    """Search Google for private-sector RFPs matching Nutrient's use cases.

    Rotates through search terms across runs, staying within the daily
    API quota.  Each result is checked against the aggregator blocklist
    and the database dedup table before enrichment.
    """
    if not GOOGLE_CSE_API_KEY or not GOOGLE_CSE_CX:
        logger.warning("GOOGLE_CSE_API_KEY / GOOGLE_CSE_CX not set — skipping")
        return []

    # Determine which batch of queries to run
    idx_raw = get_meta("google_cse_query_index")
    start_idx = int(idx_raw) if idx_raw else 0
    total = len(_SEARCH_TERMS)

    # Pick the next batch of queries
    batch_indices = [(start_idx + i) % total for i in range(_BATCH_SIZE)]
    queries = [_SEARCH_TERMS[i] for i in batch_indices]
    next_idx = (start_idx + _BATCH_SIZE) % total
    set_meta("google_cse_query_index", str(next_idx))

    # Execute searches and collect unique candidates
    candidates: dict[str, dict] = {}  # url → opp
    for query in queries:
        if _get_daily_calls() >= GOOGLE_CSE_DAILY_LIMIT:
            break
        for item in _search(query):
            opp = _process_result(item)
            if opp and opp["url"] not in candidates:
                candidates[opp["url"]] = opp
                if len(candidates) >= limit:
                    break
        if len(candidates) >= limit:
            break

    logger.info(
        "Google CSE: %d new candidates from %d queries (%d daily calls used)",
        len(candidates),
        len(queries),
        _get_daily_calls(),
    )

    if not candidates:
        return []

    # Enrich each candidate with full page fetch + Claude metadata extraction
    results: list[dict[str, Any]] = []
    for opp in candidates.values():
        enriched = _enrich_opportunity(opp)
        results.append(enriched)

    logger.info("Google CSE: %d opportunities ready for scoring", len(results))
    return results
