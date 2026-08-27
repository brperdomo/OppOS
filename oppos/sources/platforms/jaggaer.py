"""Generic scraper for JAGGAER/SciQuest eProcurement portals.

Covers: Iowa, Montana, New Mexico, Pennsylvania, Utah, Ohio.
Most use bids.sciquest.com with a CustomerOrg parameter.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from typing import Any

import httpx

logger = logging.getLogger(__name__)


@dataclass
class JaggaerSite:
    key: str
    state: str
    name: str
    base_url: str
    customer_org: str
    place_default: str = ""


SITES: dict[str, JaggaerSite] = {
    "iowa_impacs": JaggaerSite(
        key="iowa_impacs", state="IA", name="IMPACS Iowa",
        base_url="https://bids.sciquest.com",
        customer_org="DASIowa",  # Changed from StateOfIowa (400 error)
        place_default="Iowa",
    ),
    "montana_emacs": JaggaerSite(
        key="montana_emacs", state="MT", name="eMACS Montana",
        base_url="https://bids.sciquest.com",
        customer_org="StateOfMontana",
        place_default="Montana",
    ),
    "new_mexico_epronm": JaggaerSite(
        key="new_mexico_epronm", state="NM", name="eProNM",
        base_url="https://bids.sciquest.com",
        customer_org="StateOfNewMexico",
        place_default="New Mexico",
    ),
    # NOTE: Pennsylvania removed — uses custom ASP.NET site, not JAGGAER.
    # See pa_emarketplace.py for the PA scraper.
    # NOTE: Utah removed — migrated from JAGGAER to Bonfire (April 2025).
    # New URL: https://utah.bonfirehub.com/portal/?tab=openOpportunities
}


def _parse_date(date_str: str | None) -> str | None:
    if not date_str:
        return None
    date_str = date_str.strip()
    for fmt in ("%m/%d/%Y %I:%M %p", "%m/%d/%Y %H:%M:%S", "%m/%d/%Y", "%Y-%m-%d",
                "%m/%d/%Y %I:%M %p %Z"):
        try:
            return datetime.strptime(date_str, fmt).isoformat()
        except ValueError:
            continue
    # Try stripping timezone abbreviation (e.g. "6/1/2026 12:00 AM CDT")
    stripped = re.sub(r"\s+[A-Z]{2,4}$", "", date_str)
    for fmt in ("%m/%d/%Y %I:%M %p", "%m/%d/%Y %H:%M:%S"):
        try:
            return datetime.strptime(stripped, fmt).isoformat()
        except ValueError:
            continue
    return None


def _parse_list_page(html: str, site: JaggaerSite) -> list[dict[str, Any]]:
    """Parse the new JAGGAER PHX list page format.

    The 2025+ JAGGAER UI embeds all event data (title, description, dates,
    type, number, contact) directly in each ``<tr>`` row instead of requiring
    separate detail-page fetches.  Detail links now use AuthToken instead of
    eventId.
    """
    results: list[dict[str, Any]] = []

    # Split HTML into rows from the phx table
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.DOTALL)

    for row in rows:
        # Must have a detail link to be a real event row
        link_match = re.search(
            r'href="(https://app01\.jaggaer\.com/apps/Router/ViewSourcingEvent\?[^"]+)"',
            row,
        )
        if not link_match:
            # Also try old-style links
            link_match = re.search(r'href="([^"]*(?:EventDetail|eventId)[^"]*)"', row)
        if not link_match:
            continue

        detail_url = link_match.group(1).replace("&amp;", "&")

        # Strip HTML to get raw text, then extract structured fields
        text = re.sub(r"<[^>]+>", " ", row)
        text = re.sub(r"\s+", " ", text).strip()

        # Title is the first substantial text chunk (after status like "Open")
        # Find all text between tags for more precise extraction
        chunks = [c.strip() for c in re.sub(r"<[^>]+>", "\n", row).split("\n") if c.strip()]

        title = ""
        description = ""
        for chunk in chunks:
            if chunk in ("Open", "Closed", "Awarded", "Respond Now", "Details", "View as PDF"):
                continue
            if len(chunk) > 10 and not title:
                title = chunk
                continue
            if len(chunk) > 20 and not description and chunk != title:
                description = chunk
                break

        # Extract structured fields using label patterns
        open_match = re.search(r"Open\s*([\d/]+\s+[\d:]+\s+\w+(?:\s+\w+)?)", text)
        close_match = re.search(r"Close\s*([\d/]+\s+[\d:]+\s+\w+(?:\s+\w+)?)", text)
        type_match = re.search(r"Type\s*(\w+)", text)
        num_match = re.search(r"Number\s*([\w\-]+)", text)
        contact_match = re.search(r"Contact\s+([\w\s.]+?)\s+([\w.+-]+@[\w.-]+)", text)

        sol_number = num_match.group(1) if num_match else ""
        source_id = f"{site.state.lower()}-jag-{sol_number}" if sol_number else f"{site.state.lower()}-jag-{hash(detail_url) & 0xFFFFFF:06x}"

        opp: dict[str, Any] = {
            "source": site.key,
            "source_id": source_id,
            "title": (title or "Untitled")[:500],
            "solicitation_number": sol_number,
            "notice_type": type_match.group(1) if type_match else "",
            "posted_date": _parse_date(open_match.group(1) if open_match else None),
            "response_deadline": _parse_date(close_match.group(1) if close_match else None),
            "agency": "",
            "office": "",
            "naics_code": "",
            "set_aside": "",
            "classification_code": "",
            "url": detail_url,
            "description": description or title,
            "resource_links": [],
            "point_of_contact": {
                "name": contact_match.group(1).strip() if contact_match else "",
                "email": contact_match.group(2) if contact_match else "",
                "phone": "",
            },
            "place_of_performance": site.place_default,
            "raw": {"row_text": text[:500]},
        }
        results.append(opp)

    return results


def fetch_opportunities(site: JaggaerSite, limit: int = 200) -> list[dict[str, Any]]:
    """Scrape open events from a JAGGAER/SciQuest portal.

    Supports both the legacy (pre-2025) and new PHX table formats.
    """
    if site.customer_org:
        list_url = f"{site.base_url}/apps/Router/PublicEvent?CustomerOrg={site.customer_org}"
    else:
        list_url = f"{site.base_url}/apps/Router/PublicEvent"

    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        logger.info("Fetching %s (%s) public events…", site.name, site.state)
        try:
            resp = client.get(list_url)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.error("%s listing failed: %s", site.name, e)
            return []

        results = _parse_list_page(resp.text, site)

    logger.info("%s: %d opportunities scraped", site.name, len(results))
    return results[:limit]
