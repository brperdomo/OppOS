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
        customer_org="StateOfIowa",
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
    "pennsylvania_emarketplace": JaggaerSite(
        key="pennsylvania_emarketplace", state="PA", name="PA eMarketplace",
        base_url="https://www.emarketplace.state.pa.us",
        customer_org="",
        place_default="Pennsylvania",
    ),
    "utah_u3p": JaggaerSite(
        key="utah_u3p", state="UT", name="Utah U3P",
        base_url="https://bids.sciquest.com",
        customer_org="StateOfUtah",
        place_default="Utah",
    ),
}


class _EventListParser(HTMLParser):
    """Parse JAGGAER public event listing pages."""

    def __init__(self):
        super().__init__()
        self._in_table = False
        self._in_row = False
        self._in_cell = False
        self._current_row: list[str] = []
        self._rows: list[list[str]] = []
        self._row_links: list[str] = []
        self._all_links: list[list[str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_dict = dict(attrs)
        if tag == "table":
            table_id = attr_dict.get("id", "")
            cls = attr_dict.get("class", "") or ""
            if "event" in table_id.lower() or "event" in cls.lower() or "list" in cls.lower():
                self._in_table = True
        if self._in_table and tag == "tr":
            self._in_row = True
            self._current_row = []
            self._row_links = []
        if self._in_row and tag == "td":
            self._in_cell = True
        if self._in_row and tag == "a":
            href = attr_dict.get("href", "")
            if href and ("EventDetail" in href or "eventId" in href or "PublicEvent" in href):
                self._row_links.append(href)

    def handle_endtag(self, tag: str) -> None:
        if self._in_cell and tag == "td":
            self._in_cell = False
        if self._in_row and tag == "tr":
            self._in_row = False
            if self._current_row:
                self._rows.append(self._current_row)
                self._all_links.append(self._row_links)
        if tag == "table" and self._in_table:
            self._in_table = False

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            text = data.strip()
            if text:
                self._current_row.append(text)


class _EventDetailParser(HTMLParser):
    """Parse JAGGAER event detail page for key fields."""

    def __init__(self):
        super().__init__()
        self._fields: dict[str, str] = {}
        self._capture_key: str | None = None
        self._in_label = False
        self._in_value = False
        self._current_label = ""
        self._current_value_parts: list[str] = []
        self._in_description = False
        self._description_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_dict = dict(attrs)
        cls = attr_dict.get("class", "") or ""
        tag_id = attr_dict.get("id", "") or ""
        if tag in ("th", "label", "span") and ("label" in cls or "header" in cls):
            self._in_label = True
            self._current_label = ""
        if tag in ("td", "span", "div") and ("value" in cls or "data" in cls or "detail" in cls):
            self._in_value = True
            self._current_value_parts = []
        if "description" in tag_id.lower() or "description" in cls.lower():
            self._in_description = True

    def handle_endtag(self, tag: str) -> None:
        if self._in_label and tag in ("th", "label", "span"):
            self._in_label = False
            self._capture_key = self._current_label.strip().rstrip(":")
        if self._in_value and tag in ("td", "span", "div"):
            self._in_value = False
            if self._capture_key:
                self._fields[self._capture_key] = " ".join(self._current_value_parts).strip()
                self._capture_key = None
        if self._in_description and tag in ("div", "td", "p"):
            self._in_description = False
            if self._description_parts:
                self._fields["Description"] = " ".join(self._description_parts).strip()

    def handle_data(self, data: str) -> None:
        if self._in_label:
            self._current_label += data
        if self._in_value:
            self._current_value_parts.append(data.strip())
        if self._in_description:
            self._description_parts.append(data.strip())


def _parse_date(date_str: str | None) -> str | None:
    if not date_str:
        return None
    for fmt in ("%m/%d/%Y %I:%M %p", "%m/%d/%Y %H:%M:%S", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str.strip(), fmt).isoformat()
        except ValueError:
            continue
    return None


def _extract_event_id(href: str) -> str | None:
    match = re.search(r"eventId=(\d+)", href)
    return match.group(1) if match else None


def fetch_opportunities(site: JaggaerSite, limit: int = 200) -> list[dict[str, Any]]:
    """Scrape open events from a JAGGAER/SciQuest portal."""
    if site.customer_org:
        list_url = f"{site.base_url}/apps/Router/PublicEvent?CustomerOrg={site.customer_org}"
    else:
        list_url = f"{site.base_url}/apps/Router/PublicEvent"

    results: list[dict[str, Any]] = []

    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        logger.info("Fetching %s (%s) public events…", site.name, site.state)
        try:
            resp = client.get(list_url)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.error("%s listing failed: %s", site.name, e)
            return []

        parser = _EventListParser()
        parser.feed(resp.text)

        seen_ids: set[str] = set()
        event_links: list[tuple[str, str]] = []
        for row_links in parser._all_links:
            for href in row_links:
                eid = _extract_event_id(href)
                if eid and eid not in seen_ids:
                    seen_ids.add(eid)
                    full_href = href if href.startswith("http") else f"{site.base_url}{href}"
                    event_links.append((eid, full_href))

        logger.info("%s: found %d events", site.name, len(event_links))

        for event_id, detail_url in event_links[:limit]:
            try:
                resp = client.get(detail_url)
                resp.raise_for_status()
            except httpx.HTTPError as e:
                logger.warning("%s: failed to fetch event %s: %s", site.name, event_id, e)
                continue

            dp = _EventDetailParser()
            dp.feed(resp.text)
            fields = dp._fields

            title = fields.get("Event Name", fields.get("Title", fields.get("Description", "Untitled")))
            deadline = _parse_date(
                fields.get("Close Date", fields.get("Response Deadline", fields.get("End Date")))
            )
            posted = _parse_date(
                fields.get("Open Date", fields.get("Start Date", fields.get("Published Date")))
            )

            opp = {
                "source": site.key,
                "source_id": f"{site.state.lower()}-jag-{event_id}",
                "title": title[:500],
                "solicitation_number": fields.get("Event ID", fields.get("Solicitation Number", event_id)),
                "notice_type": fields.get("Event Type", fields.get("Type", "")),
                "posted_date": posted,
                "response_deadline": deadline,
                "agency": fields.get("Organization", fields.get("Agency", fields.get("Department", ""))),
                "office": fields.get("Department", fields.get("Division", "")),
                "naics_code": fields.get("NAICS", ""),
                "set_aside": "",
                "classification_code": fields.get("Commodity Code", fields.get("NIGP Code", "")),
                "url": detail_url,
                "description": fields.get("Description", fields.get("Scope", "")),
                "resource_links": [],
                "point_of_contact": {
                    "name": fields.get("Contact", fields.get("Buyer", "")),
                    "email": fields.get("Contact Email", fields.get("Email", "")),
                    "phone": "",
                },
                "place_of_performance": fields.get("Location", site.place_default),
                "raw": fields,
            }
            results.append(opp)

    logger.info("%s: %d opportunities scraped", site.name, len(results))
    return results
