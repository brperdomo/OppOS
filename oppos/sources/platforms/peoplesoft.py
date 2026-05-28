"""Generic scraper for PeopleSoft/Oracle Supplier Portal eProcurement.

Covers: Georgia, Indiana, Kansas, Minnesota, New York, Oklahoma, Tennessee, Wisconsin.
PeopleSoft portals share similar Fluid Supplier Portal UI patterns.
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
class PeopleSoftSite:
    key: str
    state: str
    name: str
    base_url: str
    bids_path: str = ""
    place_default: str = ""


SITES: dict[str, PeopleSoftSite] = {
    "tennessee_edison": PeopleSoftSite(
        key="tennessee_edison", state="TN", name="Edison Tennessee",
        base_url="https://hub.edison.tn.gov",
        bids_path="/psp/paprd/SUPPLIER/ERP/h/?tab=TN_SS_SUPPLIER_TAB",
        place_default="Tennessee",
    ),
    "georgia_tgm": PeopleSoftSite(
        key="georgia_tgm", state="GA", name="Team Georgia Marketplace",
        base_url="https://ssl.doas.state.ga.us",
        bids_path="/gpr/",
        place_default="Georgia",
    ),
    "indiana_idoa": PeopleSoftSite(
        key="indiana_idoa", state="IN", name="Indiana IDOA",
        base_url="https://www.in.gov",
        bids_path="/idoa/procurement/current-business-opportunities/",
        place_default="Indiana",
    ),
    "kansas_esupplier": PeopleSoftSite(
        key="kansas_esupplier", state="KS", name="Kansas eSupplier",
        base_url="https://supplier.sok.ks.gov",
        bids_path="/psp/sokfsprdsup/SUPPLIER/ERP/h/?tab=DEFAULT",
        place_default="Kansas",
    ),
    "minnesota_swift": PeopleSoftSite(
        key="minnesota_swift", state="MN", name="Minnesota SWIFT",
        base_url="https://guest.supplier.systems.state.mn.us",
        bids_path="/psp/fmssupap/SUPPLIER/ERP/h/?tab=DEFAULT",
        place_default="Minnesota",
    ),
    "oklahoma_omes": PeopleSoftSite(
        key="oklahoma_omes", state="OK", name="Oklahoma OMES",
        base_url="https://oklahoma.gov",
        bids_path="/omes/divisions/central-purchasing/solicitations/",
        place_default="Oklahoma",
    ),
    "wisconsin_esupplier": PeopleSoftSite(
        key="wisconsin_esupplier", state="WI", name="Wisconsin eSupplier",
        base_url="https://esupplier.wi.gov",
        bids_path="/psp/WISPRDSS/SUPPLIER/ERP/h/?tab=DEFAULT",
        place_default="Wisconsin",
    ),
    "new_york_sfs": PeopleSoftSite(
        key="new_york_sfs", state="NY", name="NY SFS Vendor Portal",
        base_url="https://esupplier.sfs.ny.gov",
        bids_path="/psp/fsprda/SUPPLIER/ERP/h/?tab=DEFAULT",
        place_default="New York",
    ),
}


class _BidListParser(HTMLParser):
    """Parse bid listings from PeopleSoft-style pages."""

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
        if tag == "table" and ("PSLEVEL" in cls or "grid" in cls.lower() or "list" in cls.lower()
                               or "result" in cls.lower() or "data" in cls.lower()):
            self._in_table = True
        if self._in_table and tag == "tr":
            self._in_row = True
            self._current_row = []
            self._row_links = []
        if self._in_row and tag == "td":
            self._in_cell = True
        if self._in_row and tag == "a":
            href = attr_dict.get("href", "")
            if href and href != "#" and "javascript" not in href.lower():
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


def _parse_date(date_str: str | None) -> str | None:
    if not date_str:
        return None
    for fmt in ("%m/%d/%Y %I:%M %p", "%m/%d/%Y %H:%M:%S", "%m/%d/%Y", "%Y-%m-%d", "%b %d, %Y"):
        try:
            return datetime.strptime(date_str.strip(), fmt).isoformat()
        except ValueError:
            continue
    return None


def fetch_opportunities(site: PeopleSoftSite, limit: int = 200) -> list[dict[str, Any]]:
    """Scrape open bids from a PeopleSoft Supplier Portal."""
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

        for i, (row, links) in enumerate(zip(parser._rows, parser._all_links)):
            if i >= limit:
                break

            cells = [c for c in row if c]
            if len(cells) < 2:
                continue

            detail_url = ""
            if links:
                href = links[0]
                detail_url = href if href.startswith("http") else f"{site.base_url}{href}"

            title = cells[1] if len(cells) > 1 else cells[0]
            sol_num = cells[0] if len(cells) > 1 else ""
            agency = cells[2] if len(cells) > 2 else ""
            deadline_str = cells[3] if len(cells) > 3 else ""

            opp = {
                "source": site.key,
                "source_id": f"{site.state.lower()}-ps-{sol_num or i}",
                "title": title[:500],
                "solicitation_number": sol_num,
                "notice_type": "",
                "posted_date": None,
                "response_deadline": _parse_date(deadline_str),
                "agency": agency,
                "office": "",
                "naics_code": "",
                "set_aside": "",
                "classification_code": "",
                "url": detail_url or list_url,
                "description": title,
                "resource_links": [],
                "point_of_contact": {"name": "", "email": "", "phone": ""},
                "place_of_performance": site.place_default,
                "raw": {"cells": cells, "links": links},
            }
            results.append(opp)

    logger.info("%s: %d opportunities scraped", site.name, len(results))
    return results
