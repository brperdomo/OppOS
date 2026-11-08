"""Wisconsin VendorNet (vendornet.wi.gov) — the state's public bid board, open to anyone without registering.

VendorNet is a Blazor Server app: the bid grid is rendered over a live connection, so it is read with a plain headless
browser (no anti-detection settings; the daily scan installs one, Streamlit Cloud has none). The grid is filtered to
bids due today or later; each bid's page (``/Bid/View/<id>``) is opened from its row for the synopsis, questions
deadline and contact. The grid's rows carry no links and going back resets the search, so every detail visit starts
from a fresh, filtered grid.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Any

logger = logging.getLogger(__name__)

BASE = "https://vendornet.wi.gov"
PAGE_SIZE = "50"
MAX_DETAILS = 120


def _date(raw: str) -> str | None:
    for fmt in ("%m/%d/%Y %I:%M %p", "%m/%d/%Y"):
        try:
            return datetime.strptime(raw.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _between(text: str, start: str, ends: tuple[str, ...]) -> str:
    i = text.find(start)
    if i < 0:
        return ""
    i += len(start)
    j = min([k for k in (text.find(e, i) for e in ends) if k >= 0] or [len(text)])
    return text[i:j].strip()


def fetch_opportunities(limit: int = 300) -> list[dict[str, Any]]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.warning("VendorNet needs a headless browser (pip install playwright && playwright install chromium)")
        return []

    out: list[dict[str, Any]] = []
    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(channel="chrome", headless=True)
        except Exception:
            browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1400, "height": 1000})

        def open_grid(page_no: int) -> list:
            page.goto(f"{BASE}/Bids", wait_until="networkidle", timeout=60000)
            page.wait_for_selector("#DueDateStart", timeout=30000)
            page.fill("#DueDateStart", date.today().isoformat())
            page.get_by_role("button", name="Search").click()
            page.wait_for_timeout(2500)
            sizes = page.query_selector(".k-pager-sizes .k-dropdownlist")
            if sizes:
                sizes.click()
                page.get_by_role("option", name=PAGE_SIZE).click()
                page.wait_for_timeout(2500)
            if page_no > 1:
                page.get_by_role("button", name=str(page_no), exact=True).click()
                page.wait_for_timeout(2500)
            return page.query_selector_all("table tbody tr")

        try:
            pager = ""
            rows = open_grid(1)
            if page.query_selector(".k-pager"):
                pager = " ".join(page.inner_text(".k-pager").split())
            total = int((re.search(r"of ([\d,]+) items", pager) or [None, "0"])[1].replace(",", "") or 0)
            pages = max(1, -(-min(total, limit) // int(PAGE_SIZE)))
            listed: list[tuple[int, int, list[str]]] = []
            for page_no in range(1, pages + 1):
                rows = rows if page_no == 1 else open_grid(page_no)
                for i, r in enumerate(rows):
                    cells = [c.inner_text().strip() for c in r.query_selector_all("td")]
                    if len(cells) >= 6 and cells[0]:
                        listed.append((page_no, i, cells))
            logger.info("VendorNet: %d open bids listed", len(listed))

            for n, (page_no, i, cells) in enumerate(listed[:limit]):
                ref, title, org, available, due, kind = cells[:6]
                bid: dict[str, Any] = {
                    "source": "wisconsin_vendornet",
                    "source_id": f"wi-vn-{re.sub(r'[^A-Za-z0-9-]+', '-', ref)[:80]}",
                    "title": title[:300] or ref,
                    "solicitation_number": ref,
                    "notice_type": kind,
                    "agency": org,
                    "posted_date": _date(available),
                    "response_deadline": _date(due),
                    "url": f"{BASE}/Bids",
                    "description": title,
                    "point_of_contact": {"name": "", "email": "", "phone": ""},
                    "place_of_performance": "Wisconsin",
                    "resource_links": [],
                    "raw": {"ref": ref, "due": due},
                }
                if n < MAX_DETAILS:
                    try:
                        grid = open_grid(page_no)
                        grid[i].click()
                        page.wait_for_url("**/Bid/View/**", timeout=15000)
                        page.wait_for_timeout(1200)
                        text = " ".join(page.inner_text("body").split())
                        bid["url"] = page.url
                        bid["raw"]["view_id"] = page.url.rsplit("/", 1)[-1]
                        synopsis = _between(text, "Synopsis", ("Contact Information", "Documents"))
                        if synopsis:
                            bid["description"] = synopsis[:4000]
                        qa = _between(text, "Questions Due", ("Due Date",))
                        if qa:
                            bid["raw"]["questions_due"] = qa
                        contact = _between(text, "Contact Information", ("Documents",))
                        mail = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", contact)
                        phone = re.search(r"\(?\d{3}\)?[-. ]?\d{3}[-. ]\d{4}", contact)
                        bid["point_of_contact"] = {"name": _between(contact, "Name", ("Email",)).strip(),
                                                   "email": mail.group(0) if mail else "", "phone": phone.group(0) if phone else ""}
                    except Exception as e:  # keep the grid facts; the listing page is still linked
                        logger.warning("VendorNet detail for %s failed: %s", ref, e)
                out.append(bid)
        finally:
            browser.close()
    logger.info("VendorNet: %d open bids", len(out))
    return out
