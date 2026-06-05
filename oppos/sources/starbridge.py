"""Starbridge.ai RFP aggregator scraper.

Starbridge provides a free, categorized catalog of government RFPs with
clean structured data (JSON-LD + HTML cards).  This scraper monitors
categories that align with Nutrient Workflow use cases and feeds new
listings into the scoring pipeline.

No API key required.  Each category page returns 20 results with title,
agency, description, release date, and close date embedded in the HTML.
Detail pages add state/region via JSON-LD ``addressRegion``.

This is a separate source category from state procurement portals --
Starbridge aggregates across federal, state, and local sources.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime
from typing import Any
from urllib.parse import urljoin

import httpx

from oppos.storage.db import get_meta, set_meta, is_seen

logger = logging.getLogger(__name__)

_BASE_URL = "https://starbridge.ai"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}

# ---------------------------------------------------------------------------
# Categories mapped to Nutrient Workflow use cases
# ---------------------------------------------------------------------------

_CATEGORIES: list[dict[str, str]] = [
    {"slug": "case-management", "label": "Case Management"},
    {"slug": "document-management", "label": "Document Management"},
    {"slug": "erp", "label": "ERP"},
    {"slug": "permitting-software", "label": "Permitting Software"},
    {"slug": "records-management-system", "label": "Records Management"},
    {"slug": "hris", "label": "HRIS"},
    {"slug": "grants-management", "label": "Grants Management"},
    {"slug": "eprocurement", "label": "eProcurement"},
    {"slug": "financial-reporting-software", "label": "Financial Reporting"},
    {"slug": "lms", "label": "LMS"},
]

# How many pages to scan per category (20 results per page)
_MAX_PAGES_PER_CATEGORY = 3


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _parse_date(date_str: str | None) -> str | None:
    """Parse dates like 'Jun 12, 2026' or 'May 28, 2026'."""
    if not date_str:
        return None
    date_str = date_str.strip()
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _make_source_id(url: str) -> str:
    return f"sb-{hashlib.sha256(url.encode()).hexdigest()[:12]}"


def _parse_listing_page(html: str) -> list[dict[str, Any]]:
    """Parse a Starbridge category listing page.

    Uses JSON-LD ItemList for title/url/description, then extracts
    agency, release date, and close date from HTML card structure.
    """
    # Extract JSON-LD items
    jsonld_blocks = re.findall(
        r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
        html, re.DOTALL,
    )
    jld_items: list[dict] = []
    for block in jsonld_blocks:
        try:
            data = json.loads(block)
            if isinstance(data, dict) and data.get("@type") == "ItemList":
                jld_items = data.get("itemListElement", [])
                break
        except json.JSONDecodeError:
            continue

    # Extract card text blocks (split on <h3> which starts each card)
    card_segments = re.split(r"<h3[^>]*>", html)
    cards_text: list[list[str]] = []
    for seg in card_segments[1:]:  # skip content before first card
        clean = re.sub(r"<[^>]+>", "|", seg)
        parts = [p.strip() for p in clean.split("|") if p.strip()]
        cards_text.append(parts)

    results: list[dict[str, Any]] = []

    for i, jld_item in enumerate(jld_items):
        url = jld_item.get("url", "")
        title = jld_item.get("name", "")
        description = jld_item.get("description", "")

        if not url or not title:
            continue

        # Match with HTML card for agency and dates
        agency = ""
        release_date = None
        close_date = None
        status = ""

        if i < len(cards_text):
            parts = cards_text[i]
            # Card structure: [title, status, agency, description, "Posted Date",
            #                  "Release:", date, "Due Date", "Close:", date, ...]
            if len(parts) >= 3:
                status = parts[1] if parts[1] in ("Available", "Closed", "Upcoming") else ""
                agency = parts[2] if len(parts) > 2 else ""
                # Sometimes agency is at index 1 if status is missing
                if not status and len(parts) > 1:
                    agency = parts[1]

            # Find dates by looking for "Release:" and "Close:" markers
            for j, part in enumerate(parts):
                if part == "Release:" and j + 1 < len(parts):
                    release_date = _parse_date(parts[j + 1])
                elif part == "Close:" and j + 1 < len(parts):
                    close_date = _parse_date(parts[j + 1])

        source_id = _make_source_id(url)

        results.append({
            "source_id": source_id,
            "url": url,
            "title": title,
            "description": description,
            "agency": agency,
            "posted_date": release_date,
            "response_deadline": close_date,
            "status": status,
        })

    return results


def _fetch_state_from_detail(url: str) -> str:
    """Fetch a detail page and extract state from JSON-LD addressRegion."""
    try:
        resp = httpx.get(url, timeout=10.0, headers=_HEADERS, follow_redirects=True)
        if resp.status_code != 200:
            return ""

        jsonld_blocks = re.findall(
            r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
            resp.text, re.DOTALL,
        )
        for block in jsonld_blocks:
            try:
                data = json.loads(block)
                if isinstance(data, dict) and data.get("@type") == "GovernmentService":
                    provider = data.get("provider", {})
                    addr = provider.get("address", {})
                    return addr.get("addressRegion", "")
            except json.JSONDecodeError:
                continue
    except Exception:
        pass
    return ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_opportunities(limit: int = 100) -> list[dict[str, Any]]:
    """Scan Starbridge RFP categories for new listings.

    Iterates through categories relevant to Nutrient Workflow, extracts
    listing data from each page, and returns new (unseen) opportunities
    in the standard schema.
    """
    all_opps: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    with httpx.Client(timeout=15.0, headers=_HEADERS, follow_redirects=True) as client:
        for cat in _CATEGORIES:
            slug = cat["slug"]
            label = cat["label"]

            for page_num in range(1, _MAX_PAGES_PER_CATEGORY + 1):
                url = f"{_BASE_URL}/catalog/rfp/{slug}?page={page_num}"
                logger.info("Starbridge: fetching %s page %d", label, page_num)

                try:
                    resp = client.get(url)
                    resp.raise_for_status()
                except httpx.HTTPError as e:
                    logger.warning("Starbridge: %s page %d failed: %s", label, page_num, e)
                    break

                listings = _parse_listing_page(resp.text)
                if not listings:
                    break  # no more results in this category

                new_count = 0
                for listing in listings:
                    rfp_url = listing["url"]
                    if rfp_url in seen_urls:
                        continue
                    seen_urls.add(rfp_url)

                    source_id = listing["source_id"]
                    if is_seen(source_id):
                        continue

                    # Skip closed listings
                    if listing.get("status", "").lower() == "closed":
                        continue

                    opp: dict[str, Any] = {
                        "source": "starbridge",
                        "source_id": source_id,
                        "title": listing["title"][:500],
                        "solicitation_number": "",
                        "notice_type": "Solicitation",
                        "posted_date": listing["posted_date"],
                        "response_deadline": listing["response_deadline"],
                        "agency": listing["agency"],
                        "office": "",
                        "naics_code": "",
                        "set_aside": "",
                        "classification_code": "",
                        "url": rfp_url,
                        "description": listing["description"],
                        "resource_links": [],
                        "point_of_contact": {"name": "", "email": "", "phone": ""},
                        "place_of_performance": "",
                        "raw": {"category": slug, "starbridge_status": listing.get("status", "")},
                    }
                    all_opps.append(opp)
                    new_count += 1

                    if len(all_opps) >= limit:
                        break

                logger.info(
                    "Starbridge: %s page %d -- %d listings, %d new",
                    label, page_num, len(listings), new_count,
                )

                if len(all_opps) >= limit:
                    break

            if len(all_opps) >= limit:
                break

    logger.info("Starbridge: %d new opportunities across %d categories", len(all_opps), len(_CATEGORIES))
    return all_opps
