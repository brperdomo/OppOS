"""Generic scraper for SAP/Ariba-based eProcurement portals.

Covers: Florida (MFMP), Louisiana (LaPAC), Mississippi (MAGIC), North Carolina (eVP), South Carolina (SCPro).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from typing import Any

import httpx

logger = logging.getLogger(__name__)


@dataclass
class SAPSite:
    key: str
    state: str
    name: str
    base_url: str
    bids_path: str = ""
    place_default: str = ""


SITES: dict[str, SAPSite] = {
    "florida_mfmp": SAPSite(
        key="florida_mfmp", state="FL", name="MyFloridaMarketPlace",
        base_url="https://vendor.myfloridamarketplace.com",
        bids_path="/search/bids",
        place_default="Florida",
    ),
    "north_carolina_evp": SAPSite(
        key="north_carolina_evp", state="NC", name="NC eProcurement",
        base_url="https://evp.nc.gov",
        bids_path="/solicitations/",
        place_default="North Carolina",
    ),
    "mississippi_magic": SAPSite(
        key="mississippi_magic", state="MS", name="MAGIC Mississippi",
        base_url="https://www.ms.gov",
        bids_path="/dfa/contract_bid_search/Bid",
        place_default="Mississippi",
    ),
    "south_carolina_scpro": SAPSite(
        key="south_carolina_scpro", state="SC", name="SC Procurement",
        base_url="https://procurement.sc.gov",
        bids_path="/doing-biz/bid-ops",
        place_default="South Carolina",
    ),
    "louisiana_lapac": SAPSite(
        key="louisiana_lapac", state="LA", name="LaPAC Louisiana",
        base_url="https://wwwcfprd.doa.louisiana.gov",
        bids_path="/osp/lapac/pubmain.cfm",
        place_default="Louisiana",
    ),
}


class _BidListParser(HTMLParser):
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
        if tag == "table" and ("bid" in cls.lower() or "result" in cls.lower()
                               or "list" in cls.lower() or "data" in cls.lower()
                               or "grid" in cls.lower()):
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
                "%b %d, %Y", "%d-%b-%Y"):
        try:
            return datetime.strptime(date_str.strip(), fmt).isoformat()
        except ValueError:
            continue
    return None


def fetch_opportunities(site: SAPSite, limit: int = 200) -> list[dict[str, Any]]:
    """Scrape open bids from an SAP/Ariba procurement portal."""
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
            sol_num = cells[0]
            agency = cells[2] if len(cells) > 2 else ""
            deadline_str = cells[-1] if len(cells) > 2 else ""

            opp = {
                "source": site.key,
                "source_id": f"{site.state.lower()}-sap-{sol_num or i}",
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
