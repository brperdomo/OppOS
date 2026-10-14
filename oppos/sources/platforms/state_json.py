"""State portals whose listings come from a JSON endpoint behind a JavaScript page.

Each fetcher here calls the same request the portal's own page makes, so it needs no browser:

* Mississippi MAGIC — the DFA bid search is a legacy DataTables 1.9 grid; ``POST /dfa/contract_bid_search/Bid/BidData``
  returns every open bid with description, buyer contact, category and PDF link.
* Louisiana LaPAC — plain ColdFusion HTML, but one page per department (``dspBid.cfm?search=department&term=N``);
  the department list comes from ``deptbids.cfm``.
* North Carolina eVP — a Dynamics 365 Power Pages entity grid; ``POST /_services/entity-grid-data.json/<grid>`` with
  the page's secure configuration and an anti-forgery token returns the solicitation records page by page.
"""
from __future__ import annotations

import base64
import html as _html
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"}


def _ms_date(raw: str | None) -> str | None:
    """'/Date(1791954000000)/' → ISO date."""
    m = re.search(r"/Date\((-?\d+)\)/", str(raw or ""))
    if not m:
        return None
    return datetime.fromtimestamp(int(m.group(1)) / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Mississippi MAGIC
# ---------------------------------------------------------------------------

MS_BASE = "https://www.ms.gov"
MS_LIST = f"{MS_BASE}/dfa/contract_bid_search/Bid"
MS_DATA = f"{MS_BASE}/dfa/contract_bid_search/Bid/BidData?AppId=1"
_MS_COLS = ["Agency", "BidNumber", "ObjectID", "VerNumber", "BidStatus", "AdvertiseDate", "SubmissionDate", "OpeningDate", "BidID"]


def fetch_mississippi(limit: int = 500) -> list[dict[str, Any]]:
    """Every bid the MAGIC search lists; closed ones come back flagged inactive so held rows can be retired."""
    data: dict[str, str] = {"sEcho": "1", "iColumns": str(len(_MS_COLS)), "sColumns": "", "iDisplayStart": "0",
                            "iDisplayLength": str(limit), "sSearch": "", "bRegex": "false", "iSortCol_0": "6",
                            "sSortDir_0": "asc", "iSortingCols": "1"}
    for i, col in enumerate(_MS_COLS):
        data.update({f"mDataProp_{i}": col, f"sSearch_{i}": "", f"bRegex_{i}": "false", f"bSearchable_{i}": "true", f"bSortable_{i}": "true"})
    with httpx.Client(timeout=40.0, follow_redirects=True, headers=_UA) as client:
        logger.info("Fetching MAGIC Mississippi (MS) bids…")
        resp = client.post(MS_DATA, data=data, headers={"X-Requested-With": "XMLHttpRequest", "Referer": MS_LIST})
        resp.raise_for_status()
        rows = resp.json().get("aaData", [])
    out: list[dict[str, Any]] = []
    for r in rows:
        bid_id = str(r.get("BidID") or "").strip()
        if not bid_id:
            continue
        number = str(r.get("BidNumber") or bid_id).strip()
        desc = _html.unescape(str(r.get("BidDescription") or "")).strip()
        status = str(r.get("BidStatus") or "").strip().lower()
        out.append({
            "source": "mississippi_magic",
            "source_id": f"ms-magic-{bid_id}",
            "title": (desc.split(". ")[0][:160] if desc else number) or number,
            "solicitation_number": number,
            "notice_type": str(r.get("BidType") or ""),
            "agency": str(r.get("Agency") or "").title(),
            "posted_date": _ms_date(r.get("AdvertiseDate")),
            "response_deadline": _ms_date(r.get("SubmissionDate")) or _ms_date(r.get("OpeningDate")),
            "url": f"{MS_LIST}?BidID={bid_id}",
            "description": "\n".join(p for p in (desc, str(r.get("AdditionalInfo") or "").strip(),
                                                 f"Category: {r.get('ProcurementCategoryDescription') or ''}".strip()) if p and not p.endswith(": ")),
            "point_of_contact": {"name": str(r.get("BuyerName") or ""), "email": str(r.get("BuyerEmail") or ""), "phone": str(r.get("BuyerPhone") or "")},
            "place_of_performance": "Mississippi",
            "resource_links": [r["PDFUrl"]] if r.get("PDFUrl") else [],
            "raw": {k: v for k, v in r.items() if k not in ("ExtensionData", "Items")},
            "active": status in ("open", ""),
        })
    logger.info("MAGIC Mississippi: %d bids (%d open)", len(out), sum(1 for o in out if o["active"]))
    return out


# ---------------------------------------------------------------------------
# North Carolina eVP
# ---------------------------------------------------------------------------

NC_BASE = "https://evp.nc.gov"
NC_LIST = f"{NC_BASE}/solicitations/"


def _us_date(raw: Any) -> str | None:
    """'11/12/2026 2:00 PM' or '10/14/2026' → ISO (date, with time when given)."""
    t = " ".join(str(raw or "").split())
    for fmt in ("%m/%d/%Y %I:%M %p", "%m/%d/%Y"):
        try:
            return datetime.strptime(t, fmt).isoformat()
        except ValueError:
            continue
    return None


def _nc_attrs(rec: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for a in rec.get("Attributes", []):
        dv, v = a.get("DisplayValue"), a.get("Value")
        out[a["Name"]] = dv if dv not in (None, "") else v
    return out


def fetch_north_carolina(limit: int = 1500, page_size: int = 100, max_age_days: int = 120) -> list[dict[str, Any]]:
    """Solicitations from the eVP Power Pages grid, newest first (the grid holds ~5,000 incl. closed ones): paged
    until the postings are older than `max_age_days`. Open ones are active; cancelled / closed come back inactive."""
    with httpx.Client(timeout=40.0, follow_redirects=True, headers=_UA) as client:
        logger.info("Fetching NC eProcurement (NC) solicitations…")
        page = client.get(NC_LIST)
        page.raise_for_status()
        m = re.search(r'data-view-layouts="([^"]*)"', page.text)
        g = re.search(r"entity-grid-data\.json/([0-9a-f-]{36})", page.text)
        if not (m and g):
            raise RuntimeError("NC eVP: solicitation grid not found on the page (layout changed?)")
        raw = _html.unescape(m.group(1))
        layouts = json.loads(base64.b64decode(raw + "=" * (-len(raw) % 4)).decode("utf-8"))
        secure = layouts[0].get("Base64SecureConfiguration")
        tok_m = re.search(r'name="__RequestVerificationToken"[^>]*value="([^"]+)"', client.get(f"{NC_BASE}/_layout/tokenhtml").text)
        if not (secure and tok_m):
            raise RuntimeError("NC eVP: grid configuration or anti-forgery token missing")
        headers = {"__RequestVerificationToken": tok_m.group(1), "X-Requested-With": "XMLHttpRequest"}
        out: list[dict[str, Any]] = []
        for page_no in range(1, 50):
            body = {"base64SecureConfiguration": secure, "sortExpression": "evp_posteddate DESC", "search": None, "page": page_no,
                    "pageSize": page_size, "filter": None, "metaFilter": None, "timezoneOffset": 240, "customParameters": []}
            resp = client.post(f"{NC_BASE}/_services/entity-grid-data.json/{g.group(1)}", json=body, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            recs = data.get("Records", [])
            for rec in recs:
                a = _nc_attrs(rec)
                rid = str(rec.get("Id") or "")
                if not rid:
                    continue
                status = str(a.get("statuscode") or "").strip().lower()
                title = re.sub(r"^\s*title\s*:\s*", "", str(a.get("evp_name") or ""), flags=re.I).strip() or str(a.get("evp_solicitationnbr") or "Untitled")
                out.append({
                    "source": "north_carolina_evp",
                    "source_id": f"nc-evp-{rid}",
                    "title": title[:500],
                    "solicitation_number": str(a.get("evp_solicitationnbr") or ""),
                    "notice_type": str(a.get("evp_solicitationtype") or ""),
                    "agency": str(a.get("owningbusinessunit") or a.get("evp_agency") or "").title(),
                    "posted_date": (_us_date(a.get("evp_posteddate")) or "")[:10] or None,
                    "response_deadline": _us_date(a.get("evp_opendate")),
                    "url": f"{NC_BASE}/solicitations/details/?id={rid}",
                    "description": str(a.get("evp_description") or ""),
                    "point_of_contact": {"name": "", "email": "", "phone": ""},
                    "place_of_performance": "North Carolina",
                    "resource_links": [],
                    "raw": a,
                    "active": status == "open",
                })
            oldest = min((o["posted_date"] for o in out[-len(recs):] if o.get("posted_date")), default=None)
            too_old = bool(oldest) and (datetime.utcnow() - datetime.fromisoformat(oldest)).days > max_age_days
            if not data.get("MoreRecords") or len(out) >= limit or not recs or too_old:
                break
    logger.info("NC eProcurement: %d solicitations (%d open)", len(out), sum(1 for o in out if o["active"]))
    return out[:limit]


# ---------------------------------------------------------------------------
# Louisiana LaPAC
# ---------------------------------------------------------------------------

LA_BASE = "https://wwwcfprd.doa.louisiana.gov/osp/lapac"


def _cells(row_html: str) -> list[str]:
    return [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", _html.unescape(c))).strip()
            for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row_html, re.S)]


def _la_date(raw: str) -> str | None:
    t = " ".join(raw.replace(" CT", "").split())
    for fmt in ("%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y %I:%M %p", "%m/%d/%Y"):
        try:
            return datetime.strptime(t, fmt).isoformat()
        except ValueError:
            continue
    return None


def fetch_louisiana(limit: int = 2000) -> list[dict[str, Any]]:
    """Open bids from every LaPAC department page (the keyword search only returns a handful)."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    with httpx.Client(timeout=60.0, follow_redirects=True, headers=_UA) as client:
        logger.info("Fetching LaPAC Louisiana (LA) bids…")
        terms = sorted({int(t) for t in re.findall(r"term=(\d+)", client.get(f"{LA_BASE}/deptbids.cfm").text)})
        if not terms:
            raise RuntimeError("LaPAC: department list not found (page changed?)")
        for term in terms:
            try:
                page = client.get(f"{LA_BASE}/dspBid.cfm", params={"search": "department", "term": str(term)})
                page.raise_for_status()
            except httpx.HTTPError as e:
                logger.warning("LaPAC department %s failed: %s", term, e)
                continue
            for row in re.findall(r"<tr[^>]*>(.*?)</tr>", page.text, re.S):
                cells = _cells(row)
                if len(cells) < 4 or cells[0].lower().startswith("bid number"):
                    continue
                number = cells[0]
                if not number or number in seen:
                    continue
                seen.add(number)
                desc = cells[1]
                title = re.split(r"\s+(?:Original|Attachments?):", desc, maxsplit=1)[0].strip()[:300]
                pdf = re.search(r'href="([^"]*\.pdf)"', row)
                out.append({
                    "source": "louisiana_lapac",
                    "source_id": f"la-lapac-{number}",
                    "title": title or number,
                    "solicitation_number": number,
                    "notice_type": "RFP" if title.upper().startswith("RFP") else "",
                    "agency": f"Louisiana department {term}",
                    "posted_date": (_la_date(cells[2]) or "")[:10] or None,
                    "response_deadline": _la_date(cells[3]),
                    "url": (LA_BASE.rsplit("/osp", 1)[0] + pdf.group(1)) if pdf and pdf.group(1).startswith("/") else (pdf.group(1) if pdf else f"{LA_BASE}/dspBid.cfm?search=department&term={term}"),
                    "description": desc,
                    "point_of_contact": {"name": "", "email": "", "phone": ""},
                    "place_of_performance": "Louisiana",
                    "resource_links": [],
                    "raw": {"department_term": term, "cells": cells},
                })
            if len(out) >= limit:
                break
    logger.info("LaPAC Louisiana: %d bids across %d departments", len(out), len(terms))
    return out[:limit]
