"""Scraper for CGI Advantage 4 Vendor Self-Service (VSS) portals.

Covers: Alaska, Colorado, Kentucky, Maine, Michigan, West Virginia.
All migrated to CGI Advantage 4 Angular SPAs in 2024-2025.  Requires
Playwright (headed mode) to render the SPA and navigate to the
Published Solicitations view.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

_PLAYWRIGHT_AVAILABLE = False
try:
    import playwright.sync_api  # noqa: F401
    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    pass


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


def _parse_date(date_str: str | None) -> str | None:
    if not date_str:
        return None
    # Strip timezone abbreviations and "EDT", "EST", etc.
    cleaned = re.sub(r"\s+[A-Z]{2,4}$", "", date_str.strip())
    for fmt in ("%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y %H:%M:%S", "%m/%d/%Y %I:%M %p",
                "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(cleaned, fmt).isoformat()
        except ValueError:
            continue
    return None


def _parse_closing_cell(text: str) -> tuple[str | None, str]:
    """Parse the closing-date cell which contains date, countdown, and status.

    Example: ``06/05/2026 12:00 PM EDT | 0 Days, 18:09 | Open``
    Returns (parsed_date, status).
    """
    parts = [p.strip() for p in re.split(r"[|\n]", text) if p.strip()]
    date_str = parts[0] if parts else ""
    status = parts[-1] if len(parts) > 1 else ""
    return _parse_date(date_str), status


def _render_solicitations(site: CGISite) -> list[list[str]]:
    """Use Playwright to render the CGI Advantage 4 Angular SPA and extract
    the Published Solicitations table rows.

    Returns a list of cell-text lists, one per data row.
    """
    if not _PLAYWRIGHT_AVAILABLE:
        logger.warning(
            "Playwright not installed — cannot render CGI Advantage SPA for %s. "
            "Run: pip install playwright && playwright install chromium",
            site.name,
        )
        return []

    from playwright.sync_api import sync_playwright

    url = f"{site.base_url}{site.bids_path}"
    rows_data: list[list[str]] = []

    try:
        with sync_playwright() as pw:
            try:
                browser = pw.chromium.launch(
                    channel="chrome", headless=False,
                    args=["--disable-blink-features=AutomationControlled"],
                )
            except Exception:
                browser = pw.chromium.launch(
                    headless=False,
                    args=["--disable-blink-features=AutomationControlled"],
                )

            ctx = browser.new_context(
                viewport={"width": 1280, "height": 720}, locale="en-US",
            )
            page = ctx.new_page()

            logger.info("CGI %s: opening browser for %s", site.state, url)
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(3_000)

            try:
                page.wait_for_load_state("networkidle", timeout=10_000)
            except Exception:
                pass

            # Navigate to Published Solicitations
            sol_btn = page.get_by_text("View Published Solicitations", exact=False)
            if sol_btn.count() > 0:
                sol_btn.first.click()
                page.wait_for_timeout(4_000)
                try:
                    page.wait_for_load_state("networkidle", timeout=10_000)
                except Exception:
                    pass
            else:
                logger.warning("CGI %s: 'View Published Solicitations' button not found", site.state)

            # Extract table rows
            rows = page.query_selector_all("tr")
            for row in rows:
                cells = row.query_selector_all("td")
                if len(cells) >= 4:
                    cell_texts = [c.inner_text().strip() for c in cells]
                    rows_data.append(cell_texts)

            logger.info("CGI %s: extracted %d solicitation rows", site.state, len(rows_data))
            browser.close()
    except Exception as e:
        logger.error("CGI %s: Playwright rendering failed: %s", site.state, e)

    return rows_data


def fetch_opportunities(site: CGISite, limit: int = 200) -> list[dict[str, Any]]:
    """Scrape open bids from a CGI Advantage 4 VSS portal.

    Uses Playwright to render the Angular SPA, click through to the
    Published Solicitations view, and extract the table data.

    Table columns (standard CGI Advantage 4 format):
      [0] checkbox  [1] Description  [2] Department / Buyer
      [3] Solicitation Number / Type / Category
      [4] Closing Date and Time / Status  [5] Respond link
    """
    results: list[dict[str, Any]] = []
    rows_data = _render_solicitations(site)

    for cells in rows_data[:limit]:
        # Skip rows that are too short or look like headers
        if len(cells) < 4:
            continue

        title = cells[1].strip() if len(cells) > 1 else ""
        if not title or title.lower() in ("description", "published solicitations"):
            continue

        # Parse Department / Buyer (cell 2)
        dept_buyer = cells[2] if len(cells) > 2 else ""
        dept_parts = [p.strip() for p in re.split(r"[|\n]", dept_buyer) if p.strip()]
        agency = dept_parts[0] if dept_parts else ""
        buyer = dept_parts[1] if len(dept_parts) > 1 else ""

        # Parse Solicitation Number / Type / Category (cell 3)
        sol_info = cells[3] if len(cells) > 3 else ""
        sol_parts = [p.strip() for p in re.split(r"[|\n]", sol_info) if p.strip()]
        sol_number = sol_parts[0] if sol_parts else ""
        sol_type = sol_parts[1] if len(sol_parts) > 1 else ""

        # Parse Closing Date / Status (cell 4)
        closing_text = cells[4] if len(cells) > 4 else ""
        deadline, status = _parse_closing_cell(closing_text)

        # Skip closed/awarded
        if status.lower() in ("closed", "awarded", "cancelled"):
            continue

        sid = sol_number or f"{hash(title) & 0xFFFFFF:06x}"

        opp: dict[str, Any] = {
            "source": site.key,
            "source_id": f"{site.state.lower()}-cgi-{sid}",
            "title": title[:500],
            "solicitation_number": sol_number,
            "notice_type": sol_type,
            "posted_date": None,
            "response_deadline": deadline,
            "agency": agency,
            "office": "",
            "naics_code": "",
            "set_aside": "",
            "classification_code": "",
            "url": f"{site.base_url}{site.bids_path}",
            "description": title,
            "resource_links": [],
            "point_of_contact": {
                "name": buyer,
                "email": "",
                "phone": "",
            },
            "place_of_performance": site.place_default,
            "raw": {"cells": cells, "status": status},
        }
        results.append(opp)

    logger.info("%s: %d opportunities scraped", site.name, len(results))
    return results
