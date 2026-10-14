"""Generic scraper for Periscope/SOVRA BuySpeed eProcurement portals.

Covers: Arizona, Arkansas, California, Illinois, Massachusetts, Nevada, New Jersey, Oregon.
All share the same /bso/ application with identical URL patterns.
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
class PeriscopeSite:
    key: str
    state: str
    name: str
    base_url: str
    place_default: str = ""


SITES: dict[str, PeriscopeSite] = {
    "nevada_epro": PeriscopeSite(
        key="nevada_epro", state="NV", name="NevadaEPro",
        base_url="https://nevadaepro.com",
        place_default="Nevada",
    ),
    "massachusetts_commbuys": PeriscopeSite(
        key="massachusetts_commbuys", state="MA", name="COMMBUYS",
        base_url="https://www.commbuys.com",
        place_default="Massachusetts",
    ),
    "new_jersey_njstart": PeriscopeSite(
        key="new_jersey_njstart", state="NJ", name="NJSTART",
        base_url="https://www.njstart.gov",
        place_default="New Jersey",
    ),
    "illinois_bidbuy": PeriscopeSite(
        key="illinois_bidbuy", state="IL", name="BidBuy Illinois",
        base_url="https://www.bidbuy.illinois.gov",
        place_default="Illinois",
    ),
    "oregon_oregonbuys": PeriscopeSite(
        key="oregon_oregonbuys", state="OR", name="OregonBuys",
        base_url="https://oregonbuys.gov",
        place_default="Oregon",
    ),
    "arkansas_arbuy": PeriscopeSite(
        key="arkansas_arbuy", state="AR", name="ARBuy",
        base_url="https://arbuy.arkansas.gov",
        place_default="Arkansas",
    ),
    "arizona_app": PeriscopeSite(
        key="arizona_app", state="AZ", name="Arizona Procurement Portal",
        base_url="https://app.az.gov",
        place_default="Arizona",
    ),
    "california_caleprocure": PeriscopeSite(
        key="california_caleprocure", state="CA", name="Cal eProcure",
        base_url="https://caleprocure.ca.gov",
        place_default="California",
    ),
}


class _TableParser(HTMLParser):
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
        if tag == "table" and ("results" in cls or "list" in cls or "data" in cls):
            self._in_table = True
        if self._in_table and tag == "tr":
            self._in_row = True
            self._current_row = []
            self._row_links = []
        if self._in_row and tag == "td":
            self._in_cell = True
        if self._in_row and tag == "a":
            href = attr_dict.get("href", "")
            if href and ("bidDetail" in href or "docId" in href):
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
            self._current_row.append(data.strip())


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
        if tag == "td" and ("t-head" in cls or "label" in cls):
            self._in_label = True
            self._current_label = ""
        if tag == "td" and ("tableText" in cls or "value" in cls):
            self._in_value = True
            self._current_value_parts = []

    def handle_endtag(self, tag: str) -> None:
        if self._in_label and tag == "td":
            self._in_label = False
            self._capture_key = " ".join(self._current_label.split()).strip().rstrip(":")
        if self._in_value and tag == "td":
            self._in_value = False
            if self._capture_key:
                self._fields[self._capture_key] = " ".join(self._current_value_parts).strip()
                self._capture_key = None

    def handle_data(self, data: str) -> None:
        if self._in_label:
            self._current_label += data
        if self._in_value:
            self._current_value_parts.append(data.strip())


def _parse_contact(raw: str) -> dict[str, str]:
    email = ""
    name = raw
    email_match = re.search(r"[\w.+-]+@[\w.-]+\.\w+", raw)
    if email_match:
        email = email_match.group(0)
        name = raw[:email_match.start()].strip().rstrip("-").strip()
    return {"name": name, "email": email, "phone": ""}


def _parse_date(date_str: str | None) -> str | None:
    if not date_str:
        return None
    date_str = " ".join(date_str.split()).strip()
    for fmt in ("%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y %H:%M:%S", "%m/%d/%Y %I:%M %p", "%m/%d/%Y"):
        try:
            return datetime.strptime(date_str, fmt).isoformat()
        except ValueError:
            continue
    return None


def _extract_doc_id(href: str) -> str | None:
    match = re.search(r"docId=([^&]+)", href)
    if match:
        return match.group(1)
    match = re.search(r"bidId=([^&]+)", href)
    return match.group(1) if match else None


SEARCH_KEYWORDS = [
    "workflow automation",
    "case management",
    "document management",
    "business process",
    "forms management",
    "approval workflow",
    "contract management",
    "permit management",
    "records management",
    "invoice automation",
    "onboarding system",
    "electronic signature",
    "redaction",
    "document processing",
    "capital expenditure",
    "compliance workflow",
    "IT service management",
    "help desk",
]


def _list_rows(html: str) -> list[dict[str, str]]:
    """Rows of the open-bids results table (a full page or a PrimeFaces partial update): doc id, bid number,
    organisation, buyer, title (Description column) and opening date."""
    import html as _html
    out: list[dict[str, str]] = []
    for row in re.findall(r'<tr data-ri="\d+".*?</tr>', html, re.S):
        href = re.search(r'href="([^"]*bidDetail[^"]*)"', row)
        doc_id = _extract_doc_id(href.group(1).replace("&amp;", "&")) if href else None
        if not doc_id:
            continue
        cells = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", _html.unescape(c))).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        if len(cells) < 8:
            continue
        out.append({"doc_id": doc_id, "number": cells[0] or doc_id, "agency": cells[2], "buyer": cells[5],
                    "title": cells[6] or cells[0], "deadline": _parse_date(cells[7]) or ""})
    return out


def _search_by_keyword(
    client: httpx.Client,
    base_url: str,
    keyword: str,
) -> list[str]:
    """Run a keyword search on the Periscope advanced search and return doc IDs."""
    url = f"{base_url}/bso/view/search/external/advancedSearchBid.xhtml?openBids=true"
    try:
        resp = client.get(url)
        resp.raise_for_status()
    except httpx.HTTPError:
        return []

    xsrf = client.cookies.get("XSRF-TOKEN", "")
    vs_match = re.search(r'name="javax\.faces\.ViewState".*?value="([^"]+)"', resp.text)
    if not vs_match:
        return []

    data = {
        "javax.faces.partial.ajax": "true",
        "javax.faces.source": "bidSearchForm:btnBidSearch",
        "javax.faces.partial.execute": "@all",
        "javax.faces.partial.render": "bidSearchResultsForm",
        "bidSearchForm": "bidSearchForm",
        "bidSearchForm:desc": keyword,
        "bidSearchForm:btnBidSearch": "bidSearchForm:btnBidSearch",
        "javax.faces.ViewState": vs_match.group(1),
    }
    headers = {
        "Faces-Request": "partial/ajax",
        "X-Requested-With": "XMLHttpRequest",
        "X-XSRF-TOKEN": xsrf,
    }

    try:
        resp2 = client.post(url, data=data, headers=headers)
        if resp2.status_code != 200:
            return []
    except httpx.HTTPError:
        return []

    doc_ids: list[str] = []
    for match in re.findall(r"docId=([^&\"<\\\s]+)", resp2.text):
        if match not in doc_ids:
            doc_ids.append(match)
    return doc_ids


def fetch_opportunities(site: PeriscopeSite, limit: int = 500, workers: int = 6) -> list[dict[str, Any]]:
    """Scrape open bids from a Periscope/SOVRA BuySpeed portal."""
    open_bids_url = f"{site.base_url}/bso/view/search/external/advancedSearchBid.xhtml?openBids=true"
    detail_base = f"{site.base_url}/bso/external/bidDetail.sda"
    results: list[dict[str, Any]] = []

    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        logger.info("Fetching %s (%s) open bids…", site.name, site.state)
        try:
            resp = client.get(open_bids_url)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.error("%s listing page failed: %s", site.name, e)
            return []

        # The open-bids table shows 25 rows per page; the rest sit behind a PrimeFaces AJAX paginator. Walk it
        # (first=25, 50, …) until a page comes back empty. Each row carries number, organisation, title and
        # opening date, so a bid we already hold needs no detail fetch — only new ones cost a round trip.
        rows = _list_rows(resp.text)
        vs = re.search(r'name="javax\.faces\.ViewState"[^>]*value="([^"]+)"', resp.text)
        dt = "bidSearchResultsForm:bidResultId"
        first = 25
        while vs and first < 2000:
            data = {"javax.faces.partial.ajax": "true", "javax.faces.source": dt, "javax.faces.partial.execute": dt,
                    "javax.faces.partial.render": dt, f"{dt}_pagination": "true", f"{dt}_first": str(first), f"{dt}_rows": "25",
                    f"{dt}_encodeFeature": "true", "bidSearchResultsForm": "bidSearchResultsForm", "javax.faces.ViewState": vs.group(1)}
            try:
                r2 = client.post(open_bids_url, data=data, headers={"Faces-Request": "partial/ajax", "X-Requested-With": "XMLHttpRequest",
                                                                   "X-XSRF-TOKEN": client.cookies.get("XSRF-TOKEN") or ""})
                r2.raise_for_status()
            except httpx.HTTPError as e:
                logger.warning("%s: paginator page at %d failed: %s", site.name, first, e)
                break
            more = [r for r in _list_rows(r2.text) if r["doc_id"] not in {x["doc_id"] for x in rows}]
            if not more:
                break
            rows.extend(more)
            first += 25
        logger.info("%s: %d open bids listed across pages", site.name, len(rows))

        try:  # bids we already hold: list data is enough to refresh / expire them (one query for the whole list)
            from oppos.storage.db import get_opps_by_ids
            held = set(get_opps_by_ids([f"{site.state.lower()}-{r['doc_id']}" for r in rows]))
        except Exception:  # standalone use without a database
            held = set()
        detail_ids: list[str] = []
        for row in rows:
            sid = f"{site.state.lower()}-{row['doc_id']}"
            if sid in held:
                results.append({
                    "source": site.key, "source_id": sid, "title": row["title"][:500], "solicitation_number": row["number"],
                    "agency": row["agency"], "response_deadline": row["deadline"], "posted_date": None,
                    "url": f"{detail_base}?docId={row['doc_id']}&external=true&parentUrl=close",
                    "place_of_performance": site.place_default, "active": True,
                })
            else:
                detail_ids.append(row["doc_id"])
        logger.info("%s: %d already held, %d new to fetch in detail", site.name, len(rows) - len(detail_ids), len(detail_ids))

        def _detail(doc_id: str) -> dict[str, Any] | None:
            try:
                resp = client.get(
                    detail_base,
                    params={"docId": doc_id, "external": "true", "parentUrl": "close"},
                )
                resp.raise_for_status()
            except httpx.HTTPError as e:
                logger.warning("%s: failed to fetch detail %s: %s", site.name, doc_id, e)
                return None

            dp = _DetailParser()
            dp.feed(resp.text)
            fields = dp._fields

            deadline = _parse_date(fields.get("Bid Opening Date"))
            posted = _parse_date(fields.get("Available Date"))

            desc_parts = []
            for key in ("Bulletin Desc", "Description", "Bid Type", "Purchase Method", "Pre Bid Conference"):
                val = fields.get(key, "").strip()
                if val:
                    desc_parts.append(f"{key}: {val}")

            opp = {
                "source": site.key,
                "source_id": f"{site.state.lower()}-{doc_id}",
                "title": fields.get("Description", fields.get("Bulletin Desc", "Untitled"))[:500],
                "solicitation_number": fields.get("Bid Number", doc_id),
                "notice_type": fields.get("Procurement type", fields.get("Bid Type", "")),
                "posted_date": posted,
                "response_deadline": deadline,
                "agency": fields.get("Organization", ""),
                "office": fields.get("Department", ""),
                "naics_code": "",
                "set_aside": "",
                "classification_code": "",
                "url": f"{detail_base}?docId={doc_id}&external=true&parentUrl=close",
                "description": "\n".join(desc_parts),
                "resource_links": [],
                "point_of_contact": _parse_contact(
                    fields.get("Info Contact", fields.get("Purchaser", ""))
                ),
                "place_of_performance": fields.get("Location", site.place_default),
                "raw": fields,
            }
            return opp

        # New bids: fetch their detail pages concurrently (each is one round trip of ~0.5-1 s).
        from concurrent.futures import ThreadPoolExecutor
        todo = detail_ids[:limit]
        if len(detail_ids) > limit:
            logger.info("%s: %d new bids, fetching the first %d this scan (the rest next scan)", site.name, len(detail_ids), limit)
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            for opp in pool.map(_detail, todo):
                if opp:
                    results.append(opp)

    logger.info("%s: %d opportunities scraped", site.name, len(results))
    return results
