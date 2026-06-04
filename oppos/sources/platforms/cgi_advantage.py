"""Generic scraper for CGI Advantage Vendor Self-Service (VSS) portals.

Covers: Alaska, Colorado, Kentucky, Maine, Michigan, West Virginia, Alabama.
These share CGI's VSS module with similar page structures.
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
class CGISite:
    key: str
    state: str
    name: str
    base_url: str
    bids_path: str = ""
    place_default: str = ""


SITES: dict[str, CGISite] = {
    "west_virginia_wvoasis": CGISite(
        key="west_virginia_wvoasis", state="WV", name="wvOASIS",
        base_url="https://www.wvoasis.gov",
        bids_path="/VSS/Default",
        place_default="West Virginia",
    ),
    "kentucky_emars": CGISite(
        key="kentucky_emars", state="KY", name="eMARS Kentucky",
        base_url="https://vss.ky.gov",
        bids_path="/vssprod-ext/Advantage4",  # Migrated to CGI Advantage 4
        place_default="Kentucky",
    ),
    "colorado_vss": CGISite(
        key="colorado_vss", state="CO", name="Colorado VSS",
        base_url="https://prd.co.cgiadvantage.com",  # Migrated to CGI Federal cloud
        bids_path="/PRDVSS1X1/Advantage4",
        place_default="Colorado",
    ),
    "michigan_sigma": CGISite(
        key="michigan_sigma", state="MI", name="SIGMA Michigan",
        base_url="https://sigma.michigan.gov",
        bids_path="/PRDVSS1X1/Advantage4",  # Migrated to Advantage 4
        place_default="Michigan",
    ),
    "alaska_iris": CGISite(
        key="alaska_iris", state="AK", name="IRIS Alaska",
        base_url="https://iris-vss.alaska.gov",
        bids_path="/PRDVSS1X1/Advantage4",  # Migrated to Advantage 4
        place_default="Alaska",
    ),
    "maine_vss": CGISite(
        key="maine_vss", state="ME", name="Maine VSS",
        base_url="https://mevss.hostams.com",  # Migrated from gob2g to CGI Federal cloud
        bids_path="/PRDVSS1X1/AltSelfService",
        place_default="Maine",
    ),
}


class _BidListParser(HTMLParser):
    """Parse CGI Advantage VSS bid listing tables."""

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
        cls = attr_dict.get("class", "") or ""
        tag_id = attr_dict.get("id", "") or ""
        if tag == "table" and ("bid" in cls.lower() or "bid" in tag_id.lower()
                               or "grid" in cls.lower() or "list" in cls.lower()
                               or "result" in cls.lower()):
            self._in_table = True
        if self._in_table and tag == "tr":
            self._in_row = True
            self._current_row = []
            self._row_links = []
        if self._in_row and tag == "td":
            self._in_cell = True
        if self._in_row and tag == "a":
            href = attr_dict.get("href", "")
            if href and href != "#":
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


class _DetailParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self._fields: dict[str, str] = {}
        self._capture_key: str | None = None
        self._in_label = False
        self._in_value = False
        self._current_label = ""
        self._current_value_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_dict = dict(attrs)
        cls = attr_dict.get("class", "") or ""
        if tag in ("td", "th", "span", "label", "div") and ("label" in cls or "header" in cls or "caption" in cls):
            self._in_label = True
            self._current_label = ""
        if tag in ("td", "span", "div") and ("value" in cls or "data" in cls or "field" in cls):
            self._in_value = True
            self._current_value_parts = []

    def handle_endtag(self, tag: str) -> None:
        if self._in_label:
            self._in_label = False
            self._capture_key = self._current_label.strip().rstrip(":")
        if self._in_value:
            self._in_value = False
            if self._capture_key:
                self._fields[self._capture_key] = " ".join(self._current_value_parts).strip()
                self._capture_key = None

    def handle_data(self, data: str) -> None:
        if self._in_label:
            self._current_label += data
        if self._in_value:
            self._current_value_parts.append(data.strip())


def _parse_date(date_str: str | None) -> str | None:
    if not date_str:
        return None
    for fmt in ("%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y %H:%M:%S", "%m/%d/%Y %I:%M %p", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str.strip(), fmt).isoformat()
        except ValueError:
            continue
    return None


def fetch_opportunities(site: CGISite, limit: int = 200) -> list[dict[str, Any]]:
    """Scrape open bids from a CGI Advantage VSS portal."""
    list_url = f"{site.base_url}{site.bids_path}"
    results: list[dict[str, Any]] = []

    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        logger.info("Fetching %s (%s) open bids…", site.name, site.state)
        try:
            resp = client.get(list_url)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.error("%s listing failed: %s", site.name, e)
            return []

        parser = _BidListParser()
        parser.feed(resp.text)

        detail_urls: list[str] = []
        seen: set[str] = set()
        for row_links in parser._all_links:
            for href in row_links:
                full_url = href if href.startswith("http") else f"{site.base_url}{href}"
                if full_url not in seen:
                    seen.add(full_url)
                    detail_urls.append(full_url)

        logger.info("%s: found %d bid listings", site.name, len(detail_urls))

        for detail_url in detail_urls[:limit]:
            try:
                resp = client.get(detail_url)
                resp.raise_for_status()
            except httpx.HTTPError as e:
                logger.warning("%s: failed detail fetch: %s", site.name, e)
                continue

            dp = _DetailParser()
            dp.feed(resp.text)
            fields = dp._fields

            bid_id = fields.get("Bid Number", fields.get("Solicitation Number", fields.get("Document Number", "")))
            title = fields.get("Description", fields.get("Title", fields.get("Subject", "Untitled")))
            deadline = _parse_date(fields.get("Closing Date", fields.get("Due Date", fields.get("Bid Opening Date"))))
            posted = _parse_date(fields.get("Issue Date", fields.get("Open Date", fields.get("Published Date"))))

            desc_parts = []
            for key in ("Description", "Scope of Work", "Comments", "Special Instructions"):
                val = fields.get(key, "").strip()
                if val:
                    desc_parts.append(val)

            sid = bid_id or re.sub(r"[^a-zA-Z0-9]", "_", detail_url.split("?")[-1][:50])

            opp = {
                "source": site.key,
                "source_id": f"{site.state.lower()}-cgi-{sid}",
                "title": title[:500],
                "solicitation_number": bid_id,
                "notice_type": fields.get("Type", fields.get("Bid Type", "")),
                "posted_date": posted,
                "response_deadline": deadline,
                "agency": fields.get("Organization", fields.get("Agency", fields.get("Department", ""))),
                "office": fields.get("Division", ""),
                "naics_code": "",
                "set_aside": "",
                "classification_code": fields.get("Commodity Code", ""),
                "url": detail_url,
                "description": "\n".join(desc_parts),
                "resource_links": [],
                "point_of_contact": {
                    "name": fields.get("Contact", fields.get("Buyer", "")),
                    "email": fields.get("Email", ""),
                    "phone": fields.get("Phone", ""),
                },
                "place_of_performance": fields.get("Location", fields.get("Ship To", site.place_default)),
                "raw": fields,
            }
            results.append(opp)

    logger.info("%s: %d opportunities scraped", site.name, len(results))
    return results
