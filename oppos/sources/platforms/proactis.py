"""Generic scraper for PROACTIS/WebProcure eProcurement portals.

Covers: Connecticut (CTsource), Missouri (MissouriBUYS), Rhode Island (Ocean State Procures).
Uses the public Elasticsearch-backed REST API at proactiscloud.com.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

logger = logging.getLogger(__name__)

API_BASE = "https://webprocure.proactiscloud.com/wp-full-text-search"
DETAIL_BASE = "https://webprocure.proactiscloud.com/wp-full-text-search/soldetail"
BID_VIEW_BASE = "https://webprocure.proactiscloud.com/wp-web-public/en/#/bidboard/bid"  # the /en/ segment is required


@dataclass
class ProactisSite:
    key: str
    state: str
    name: str
    customer_id: int          # PROACTIS customer ID for API queries
    oid: int                  # Organization OID
    place_default: str = ""


SITES: dict[str, ProactisSite] = {
    "connecticut_ctsource": ProactisSite(
        key="connecticut_ctsource", state="CT", name="CTsource",
        customer_id=51, oid=149300,
        place_default="Connecticut",
    ),
    "missouri_missouribuys": ProactisSite(
        key="missouri_missouribuys", state="MO", name="MissouriBUYS",
        customer_id=38, oid=86637,
        place_default="Missouri",
    ),
    "rhode_island_osp": ProactisSite(
        key="rhode_island_osp", state="RI", name="Ocean State Procures",
        customer_id=46, oid=120002,
        place_default="Rhode Island",
    ),
}


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
    "onboarding",
    "electronic signature",
    "redaction",
    "document processing",
    "compliance",
    "IT service management",
    "help desk",
]

PAGE_SIZE = 10

# PROACTIS internal status codes (ctBidstatus.status), verified against the live RI/CT boards 2026-10-12:
# 2 = Open (accepting responses), 4 = Opened / "Under Evaluation" (responses were opened — closed to vendors),
# 6 = Awarded, 7 = Canceled / Retracted. Only 2 accepts submissions.
ACTIVE_STATUS_CODES = {2}
OPEN_PUBLIC_STATUSES = {"Open", "Active"}
# Field semantics (there is no closeDate): startDate = posted / available, openDate = bid opening = the
# vendor "End Date" (submission deadline).


def _epoch_to_iso(ms: int | str | None) -> str | None:
    """Convert epoch milliseconds to ISO date string."""
    if ms is None:
        return None
    try:
        ts = int(ms) / 1000
        return datetime.utcfromtimestamp(ts).isoformat()
    except (ValueError, TypeError, OSError):
        return None


def _strip_html(text: str | None) -> str:
    """Remove HTML tags from a string."""
    if not text:
        return ""
    return re.sub(r"<[^>]+>", " ", text).strip()


def _parse_contact(record: dict) -> dict[str, str]:
    """Extract contact info from bid contacts array."""
    contacts = record.get("bidContacts") or []
    if not contacts:
        return {"name": "", "email": "", "phone": ""}

    c = contacts[0]
    name = c.get("contactName") or c.get("name") or ""
    email = c.get("contactEmail") or c.get("email") or ""
    phone = c.get("contactPhone") or c.get("phone") or ""
    return {"name": name, "email": email, "phone": phone}


def _build_bid_url(bid_id: int, site: ProactisSite) -> str:
    """Build a public URL for viewing a bid."""
    return (
        f"{BID_VIEW_BASE}/{bid_id}"
        f"?customerid={site.customer_id}&wl=true&bidoid={site.oid}"
    )


def _search_bids(
    client: httpx.Client,
    site: ProactisSite,
    query: str = "*",
    status_filter: str = "publicStatus:Open",
    max_pages: int = 5,
) -> list[dict]:
    """Search the PROACTIS API for bids matching a query."""
    all_records: list[dict] = []
    offset = 0

    for _ in range(max_pages):
        params: dict[str, Any] = {
            "customerid": site.customer_id,
            "q": query,
            "from": offset,
            "oids": str(site.oid),
        }
        if status_filter:
            params["f"] = status_filter

        try:
            resp = client.get(f"{API_BASE}/search/sols", params=params)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.warning("%s: API search failed (q=%s, offset=%d): %s", site.name, query, offset, e)
            break

        try:
            data = resp.json()
        except Exception:
            logger.warning("%s: invalid JSON response", site.name)
            break

        records = data.get("records") or []
        if not records:
            break

        all_records.extend(records)
        total = int(data.get("hits") or 0)

        offset += PAGE_SIZE
        if offset >= total:
            break

    return all_records


def _record_to_opportunity(record: dict, site: ProactisSite) -> dict[str, Any]:
    """Convert a PROACTIS API record to our standard opportunity dict."""
    bid_id = record.get("bidid") or 0
    bid_number = record.get("bidNumber") or str(bid_id)
    title = _strip_html(record.get("title") or "Untitled")
    description = _strip_html(record.get("description") or "")

    owner_org = record.get("ownerOrg") or {}
    creator_org = record.get("creatorOrg") or {}
    agency = owner_org.get("name") or creator_org.get("name") or ""

    # Category / commodity info
    categories = record.get("bidHeaderCats") or []
    cat_names = []
    for cat in categories:
        item = cat.get("catItem") or {}
        name = item.get("name") or ""
        if name:
            cat_names.append(name)

    bid_type = ""
    ct_bid_type = record.get("ctBidtype") or {}
    if isinstance(ct_bid_type, dict):
        bid_type = ct_bid_type.get("description") or ct_bid_type.get("name") or ""

    return {
        "source": site.key,
        "source_id": f"{site.state.lower()}-proactis-{bid_id}",
        "title": title[:500],
        "solicitation_number": bid_number,
        "notice_type": bid_type,
        "posted_date": _epoch_to_iso(record.get("startDate")),
        "response_deadline": _epoch_to_iso(record.get("openDate")),   # bid opening = submission deadline
        "agency": agency,
        "office": creator_org.get("name") or "",
        "naics_code": "",
        "set_aside": "",
        "classification_code": ", ".join(cat_names[:3]) if cat_names else "",
        "url": _build_bid_url(bid_id, site),
        "description": description[:8000],
        "resource_links": [],
        "point_of_contact": _parse_contact(record),
        "place_of_performance": site.place_default,
        "raw": record,
    }


def _is_active(record: dict) -> bool:
    """Accepting submissions: status 2 / publicStatus Open, and the bid opening (End Date) still ahead."""
    open_ms = record.get("openDate")
    if open_ms is not None:
        try:
            if datetime.utcfromtimestamp(int(open_ms) / 1000) < datetime.utcnow():
                return False
        except (ValueError, TypeError, OSError):
            pass
    bid_status = record.get("ctBidstatus") or {}
    try:
        if int(bid_status.get("status")) in ACTIVE_STATUS_CODES:
            return True
    except (ValueError, TypeError):
        pass
    return (bid_status.get("publicStatus") or "") in OPEN_PUBLIC_STATUSES


def lookup_opportunity(site: ProactisSite, bid_number: str) -> dict[str, Any] | None:
    """Fetch one bid by its solicitation number (for re-syncing rows the wildcard window no longer covers).
    Returns the opportunity dict with `active` set, or None when the portal no longer lists it."""
    if not bid_number:
        return None
    with httpx.Client(timeout=30.0, follow_redirects=True, verify=False) as client:
        recs = [r for r in _search_bids(client, site, query=f'"{bid_number}"', status_filter="", max_pages=1)
                if (r.get("bidNumber") or "").strip().lower() == bid_number.strip().lower()]
    if not recs:
        return None
    opp = _record_to_opportunity(recs[0], site)
    opp["active"] = _is_active(recs[0])
    return opp


def fetch_opportunities(site: ProactisSite, limit: int = 200) -> list[dict[str, Any]]:
    """Scrape open bids from a PROACTIS/WebProcure portal."""
    results: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    all_records: list[dict] = []

    # SSL cert on proactiscloud.com is expired — must skip verification
    with httpx.Client(timeout=30.0, follow_redirects=True, verify=False) as client:
        logger.info("Fetching %s (%s) bids via PROACTIS API…", site.name, site.state)

        # Wildcard search — get all bids, filter client-side for active ones
        raw_bids = _search_bids(
            client, site, query="*", status_filter="",
            max_pages=30,  # up to 300 results
        )
        for rec in raw_bids:
            bid_id = rec.get("bidid")
            if bid_id and bid_id not in seen_ids:
                seen_ids.add(bid_id)
                all_records.append(rec)

        logger.info(
            "%s: %d total from wildcard, filtering for active…",
            site.name, len(all_records),
        )

        # Keyword searches for workflow-relevant bids
        for keyword in SEARCH_KEYWORDS:
            kw_bids = _search_bids(
                client, site, query=keyword, status_filter="",
                max_pages=3,
            )
            new_count = 0
            for rec in kw_bids:
                bid_id = rec.get("bidid")
                if bid_id and bid_id not in seen_ids:
                    seen_ids.add(bid_id)
                    all_records.append(rec)
                    new_count += 1
            if new_count:
                logger.info("%s: '%s' added %d new bids", site.name, keyword, new_count)

        # A re-issued bid carries rebuiltFromBidid: the original is retired in favour of the rebuilt one.
        rebuilt_from = {r.get("rebuiltFromBidid") for r in all_records if r.get("rebuiltFromBidid")}
        active_records, inactive_records = [], []
        for r in all_records:
            (active_records if _is_active(r) and r.get("bidid") not in rebuilt_from else inactive_records).append(r)
        logger.info("%s: %d active out of %d total", site.name, len(active_records), len(all_records))

        # Convert to opportunity dicts; inactive bids are returned too, flagged, so the pipeline can expire
        # rows it already holds (an earlier scan may have stored them while they were open).
        for record in active_records[:limit] + inactive_records:
            try:
                opp = _record_to_opportunity(record, site)
                opp["active"] = record in active_records
                results.append(opp)
            except Exception as e:
                logger.warning(
                    "%s: failed to parse bid %s: %s",
                    site.name, record.get("bidid", "?"), e,
                )

    logger.info("%s: %d opportunities scraped", site.name, len(results))
    return results
