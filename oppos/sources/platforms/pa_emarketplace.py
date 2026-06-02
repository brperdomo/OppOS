"""Scraper for Pennsylvania eMarketplace (emarketplace.state.pa.us).

PA eMarketplace is a custom ASP.NET site — NOT JAGGAER. The search page
returns 10 results via GET (POST is blocked by the server). Detail pages
are publicly accessible via GET with the SID parameter.

The scraper:
  1. Fetches the search page (10 most recent open solicitations)
  2. Fetches each detail page and extracts structured fields
  3. On regular scan cadence, 10-per-run catches new postings as they appear
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any
from urllib.parse import unquote

import httpx

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.emarketplace.state.pa.us"
_SEARCH_URL = f"{_BASE_URL}/Search.aspx"
_DETAIL_URL = f"{_BASE_URL}/Solicitations.aspx"


def _parse_date(date_str: str | None) -> str | None:
    if not date_str:
        return None
    date_str = date_str.strip()
    for fmt in ("%m/%d/%y", "%m/%d/%Y", "%m/%d/%y %I:%M %p", "%m/%d/%Y %I:%M %p"):
        try:
            return datetime.strptime(date_str, fmt).isoformat()
        except ValueError:
            continue
    return None


def _extract_field(html: str, label: str) -> str:
    """Extract the value that follows a label in PA eMarketplace HTML.

    Structure is: <label text>:</label_tag> <value_tag>value text</value_tag>
    We find the label, strip HTML between it and the next field, and take
    the first non-empty text chunk.
    """
    idx = html.find(label)
    if idx < 0:
        return ""
    # Take a chunk after the label
    chunk = html[idx + len(label):idx + len(label) + 2000]
    # Remove HTML tags, replace <br> with spaces
    chunk = re.sub(r"<br\s*/?\s*>", " ", chunk)
    chunk = re.sub(r"<[^>]+>", "|", chunk)
    parts = [p.strip() for p in chunk.split("|") if p.strip()]
    if not parts:
        return ""
    # First part might be the colon or remainder of label — skip if it's just punctuation
    first = parts[0].lstrip(":").strip()
    if first:
        return first
    return parts[1].strip() if len(parts) > 1 else ""


def _parse_detail(html: str, sid: str) -> dict[str, Any]:
    """Parse a PA eMarketplace solicitation detail page."""
    title = _extract_field(html, "Solicitation/Project Title:")
    description = _extract_field(html, "Description:")
    sol_number = _extract_field(html, "Solicitation/Project#:")
    agency = _extract_field(html, "Department/Agency:")
    location = _extract_field(html, "Delivery Location:")
    county = _extract_field(html, "County:")
    duration = _extract_field(html, "Duration:")

    # Contact info
    first_name = _extract_field(html, "First Name:")
    last_name = _extract_field(html, "Last Name:")
    phone_raw = _extract_field(html, "Phone Number:")

    # Email — look specifically in the contact section (after "Email:" label)
    email = ""
    email_section = re.search(r"Email:.*?([\w.+-]+@[\w.-]+\.(?:us|gov|com|org|net|edu))", html, re.DOTALL)
    if email_section:
        email = email_section.group(1)
    else:
        # Fallback: last email on the page (contact emails come after generic ones)
        email_matches = re.findall(r"[\w.+-]+@[\w.-]+\.(?:us|gov|com|org|net|edu)", html)
        if email_matches:
            email = email_matches[-1]

    # Dates — the "Solicitation Due Date" label has disclaimer text mixed in,
    # so look for the specific date format after "Solicitation Start Date:" etc.
    start_date_raw = _extract_field(html, "Solicitation Start Date:")
    due_date_raw = _extract_field(html, "Solicitation Due Date:")
    due_time = _extract_field(html, "Solicitation Due Time:")

    # Ad type
    ad_type = _extract_field(html, "Advertisement Type:")

    contact_name = f"{first_name} {last_name}".strip()

    # Build description with extra context
    desc_parts = [description]
    if duration:
        desc_parts.append(f"Duration: {duration}")
    if ad_type:
        desc_parts.append(f"Type: {ad_type}")
    full_desc = "\n".join(p for p in desc_parts if p)

    # Place of performance
    place = county if county and county.lower() != "statewide" else "Pennsylvania"
    if location:
        place = f"{location}, {place}"

    return {
        "source": "pennsylvania_emarketplace",
        "source_id": f"pa-{sol_number or sid}",
        "title": title[:500] or "Untitled",
        "solicitation_number": sol_number or sid,
        "notice_type": ad_type,
        "posted_date": _parse_date(start_date_raw),
        "response_deadline": _parse_date(due_date_raw),
        "agency": agency,
        "office": "",
        "naics_code": "",
        "set_aside": "",
        "classification_code": "",
        "url": f"{_DETAIL_URL}?SID={sid}",
        "description": full_desc,
        "resource_links": [],
        "point_of_contact": {
            "name": contact_name,
            "email": email,
            "phone": phone_raw,
        },
        "place_of_performance": place,
        "raw": {
            "title": title,
            "description": description,
            "agency": agency,
            "sol_number": sol_number,
            "county": county,
            "duration": duration,
            "due_time": due_time,
        },
    }


def fetch_opportunities(limit: int = 50) -> list[dict[str, Any]]:
    """Scrape open solicitations from PA eMarketplace.

    Fetches the search page (10 most recent via GET) and parses each detail page.
    """
    results: list[dict[str, Any]] = []

    with httpx.Client(
        timeout=30.0,
        follow_redirects=True,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        },
    ) as client:
        logger.info("Fetching PA eMarketplace search page…")
        try:
            resp = client.get(_SEARCH_URL)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.error("PA eMarketplace search page failed: %s", e)
            return []

        # Extract solicitation IDs from the search results
        sid_matches = re.findall(r"Solicitations\.aspx\?SID=([^\"&]+)", resp.text)
        unique_sids = list(dict.fromkeys(sid_matches))
        logger.info("PA eMarketplace: found %d solicitations on search page", len(unique_sids))

        # Fetch each detail page
        for raw_sid in unique_sids[:limit]:
            sid = unquote(raw_sid)
            try:
                detail_resp = client.get(_DETAIL_URL, params={"SID": sid})
                detail_resp.raise_for_status()
            except httpx.HTTPError as e:
                logger.warning("PA eMarketplace: failed to fetch SID %s: %s", sid, e)
                continue

            opp = _parse_detail(detail_resp.text, sid)
            if opp["title"] and opp["title"] != "Untitled":
                results.append(opp)
                logger.debug("PA eMarketplace: parsed '%s'", opp["title"][:60])
            else:
                logger.debug("PA eMarketplace: skipping empty SID %s", sid)

    logger.info("PA eMarketplace: %d opportunities scraped", len(results))
    return results
