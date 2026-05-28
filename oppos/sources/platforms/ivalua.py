"""Generic scraper for Ivalua-based eProcurement portals.

Covers: Alabama (AlabamaBuys), Maryland (eMMA), North Dakota (NDBuys), Ohio (OhioBuys), Vermont (VTBuys), Virginia (eVA).
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
class IvaluaSite:
    key: str
    state: str
    name: str
    base_url: str
    bids_path: str = ""
    place_default: str = ""


SITES: dict[str, IvaluaSite] = {
    "maryland_emma": IvaluaSite(
        key="maryland_emma", state="MD", name="eMMA Maryland",
        base_url="https://emma.maryland.gov",
        bids_path="/page.aspx/en/bpm/process_manage_498/solicitations",
        place_default="Maryland",
    ),
    "virginia_eva": IvaluaSite(
        key="virginia_eva", state="VA", name="eVA Virginia",
        base_url="https://eva.virginia.gov",
        bids_path="/pages/eva-public-solicitations.htm",
        place_default="Virginia",
    ),
    "north_dakota_ndbuys": IvaluaSite(
        key="north_dakota_ndbuys", state="ND", name="NDBuys",
        base_url="https://ndbuys.nd.gov",
        bids_path="/",
        place_default="North Dakota",
    ),
    "vermont_vtbuys": IvaluaSite(
        key="vermont_vtbuys", state="VT", name="VTBuys",
        base_url="https://vtbuysprocurement.vermont.gov",
        bids_path="/",
        place_default="Vermont",
    ),
    "alabama_alabamabuys": IvaluaSite(
        key="alabama_alabamabuys", state="AL", name="AlabamaBuys",
        base_url="https://alabamabuys.gov",
        bids_path="/",
        place_default="Alabama",
    ),
    "ohio_ohiobuys": IvaluaSite(
        key="ohio_ohiobuys", state="OH", name="OhioBuys",
        base_url="https://ohiobuys.ohio.gov",
        bids_path="/",
        place_default="Ohio",
    ),
}


class _SolicitationParser(HTMLParser):
    """Parse solicitation listings from Ivalua portals."""

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
        if tag == "table" and ("solicitation" in cls.lower() or "grid" in cls.lower()
                               or "list" in cls.lower() or "result" in cls.lower()
                               or "data" in cls.lower()):
            self._in_table = True
        if tag == "table" and not self._in_table:
            role = attr_dict.get("role", "")
            if role == "grid":
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


def _parse_date(date_str: str | None) -> str | None:
    if not date_str:
        return None
    for fmt in ("%m/%d/%Y %I:%M %p", "%m/%d/%Y %H:%M:%S", "%m/%d/%Y", "%Y-%m-%d",
                "%b %d, %Y", "%d-%b-%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(date_str.strip(), fmt).isoformat()
        except ValueError:
            continue
    return None


def fetch_opportunities(site: IvaluaSite, limit: int = 200) -> list[dict[str, Any]]:
    """Scrape open solicitations from an Ivalua portal."""
    list_url = f"{site.base_url}{site.bids_path}"
    results: list[dict[str, Any]] = []

    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        logger.info("Fetching %s (%s) solicitations…", site.name, site.state)
        try:
            resp = client.get(list_url)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.error("%s listing failed: %s", site.name, e)
            return []

        parser = _SolicitationParser()
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
            sol_num = cells[0]
            agency = cells[2] if len(cells) > 2 else ""
            deadline_str = cells[-1] if len(cells) > 2 else ""

            opp = {
                "source": site.key,
                "source_id": f"{site.state.lower()}-iv-{sol_num or i}",
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
