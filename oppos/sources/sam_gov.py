"""SAM.gov Opportunities API connector.

Docs: https://open.gsa.gov/api/get-opportunities-public-api/
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import httpx

from oppos.config import SAM_GOV_API_KEY, SAM_GOV_BASE_URL

logger = logging.getLogger(__name__)

RELEVANT_NAICS = [
    "541511",  # Custom Computer Programming Services
    "541512",  # Computer Systems Design Services
    "541513",  # Computer Facilities Management Services
    "541519",  # Other Computer Related Services
    "518210",  # Data Processing, Hosting, and Related Services
    "511210",  # Software Publishers
    "541611",  # Administrative Management Consulting
    "541614",  # Process/Physical Distribution/Logistics Consulting
    "541690",  # Other Scientific and Technical Consulting
]

KEYWORD_QUERIES = [
    # Core platform
    "workflow automation",
    "case management system",
    "case management software",
    "business process automation",
    "business process management",
    "document management workflow",
    "process automation platform",
    "low-code workflow",
    "approval workflow",
    "forms management system",
    "electronic forms",
    "document routing",
    # Finance / CapEx
    "capital expenditure approval",
    "invoice approval automation",
    "purchase requisition system",
    "accounts payable automation",
    "vendor management system",
    "financial approval workflow",
    # HR / Compliance
    "FMLA case management",
    "leave management system",
    "employee onboarding system",
    "performance review system",
    "time and attendance system",
    "HR compliance automation",
    # IT Service
    "IT service management",
    "help desk system",
    "change management system",
    "IT request management",
    # Legal / Contract
    "contract management system",
    "contract lifecycle management",
    "contract review approval",
    # Operations
    "corrective action preventive action",
    "field service management",
    "maintenance request system",
    "incident reporting system",
    # Civic / Permitting
    "permit management system",
    "licensing management system",
    "citizen request management",
    # Records / Compliance
    "records management automation",
    "compliance workflow",
    "audit trail management",
    # Document-heavy
    "document generation system",
    "electronic signature workflow",
    "document processing automation",
    "redaction software",
]


def _parse_date(date_str: str | None) -> datetime | None:
    if not date_str:
        return None
    for fmt in ("%m/%d/%Y %H:%M", "%Y-%m-%dT%H:%M:%S%z", "%m/%d/%Y"):
        try:
            return datetime.strptime(date_str.split("+")[0].split("Z")[0], fmt)
        except ValueError:
            continue
    return None


def _normalize_opportunity(raw: dict[str, Any]) -> dict[str, Any]:
    """Flatten SAM.gov API response into a consistent structure."""
    response_deadline = _parse_date(raw.get("responseDeadLine"))
    posted_date = _parse_date(raw.get("postedDate"))

    return {
        "source": "sam_gov",
        "source_id": raw.get("noticeId", ""),
        "title": raw.get("title", "").strip(),
        "solicitation_number": raw.get("solicitationNumber", ""),
        "notice_type": raw.get("type", ""),
        "posted_date": posted_date.isoformat() if posted_date else None,
        "response_deadline": response_deadline.isoformat() if response_deadline else None,
        "agency": raw.get("fullParentPathName", ""),
        "office": raw.get("officeAddress", {}).get("city", "") if isinstance(raw.get("officeAddress"), dict) else "",
        "naics_code": raw.get("naicsCode", ""),
        "set_aside": raw.get("typeOfSetAside", ""),
        "classification_code": raw.get("classificationCode", ""),
        "url": raw.get("uiLink", f"https://sam.gov/opp/{raw.get('noticeId', '')}"),
        "description": raw.get("description", ""),
        "resource_links": raw.get("resourceLinks", []),
        "point_of_contact": _extract_poc(raw.get("pointOfContact", [])),
        "place_of_performance": _extract_pop(raw.get("placeOfPerformance", {})),
        "raw": raw,
    }


def _extract_poc(contacts: list[dict] | None) -> dict[str, str]:
    if not contacts:
        return {}
    primary = contacts[0] if contacts else {}
    return {
        "name": primary.get("fullName", ""),
        "email": primary.get("email", ""),
        "phone": primary.get("phone", ""),
    }


def _extract_pop(pop: dict | None) -> str:
    if not pop:
        return ""
    city = pop.get("city", {})
    state = pop.get("state", {})
    if isinstance(city, dict):
        city = city.get("name", "")
    if isinstance(state, dict):
        state = state.get("name", "")
    return f"{city}, {state}".strip(", ")


def fetch_opportunities(
    keywords: list[str] | None = None,
    posted_from: datetime | None = None,
    posted_to: datetime | None = None,
    limit: int = 100,
    notice_types: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Fetch opportunities from SAM.gov matching keyword queries.

    Args:
        keywords: Override default keyword list. Searches are OR'd.
        posted_from: Only return opportunities posted after this date.
        posted_to: Only return opportunities posted before this date.
        limit: Max results per keyword query (API max is 1000).
        notice_types: Filter by notice type (e.g., "o" for solicitation,
                      "p" for presolicitation, "k" for combined synopsis).

    Returns:
        Deduplicated list of normalized opportunity dicts.
    """
    if not SAM_GOV_API_KEY:
        raise RuntimeError("SAM_GOV_API_KEY not set")

    if posted_from is None:
        posted_from = datetime.now() - timedelta(days=30)
    if posted_to is None:
        posted_to = datetime.now()
    if keywords is None:
        keywords = KEYWORD_QUERIES
    if notice_types is None:
        notice_types = ["o", "p", "k", "r"]  # solicitations, presolicitations, combined, sources sought

    seen_ids: set[str] = set()
    results: list[dict[str, Any]] = []

    with httpx.Client(timeout=30.0) as client:
        for keyword in keywords:
            params: dict[str, Any] = {
                "api_key": SAM_GOV_API_KEY,
                "q": keyword,
                "postedFrom": posted_from.strftime("%m/%d/%Y"),
                "postedTo": posted_to.strftime("%m/%d/%Y"),
                "limit": min(limit, 1000),
                "offset": 0,
            }
            if notice_types:
                params["ptype"] = ",".join(notice_types)

            try:
                resp = client.get(SAM_GOV_BASE_URL, params=params)
                resp.raise_for_status()
                data = resp.json()
            except (httpx.HTTPError, ValueError) as e:
                logger.warning("SAM.gov query failed for '%s': %s", keyword, e)
                continue

            opps = data.get("opportunitiesData", [])
            logger.info("SAM.gov: '%s' returned %d results", keyword, len(opps))

            for raw_opp in opps:
                notice_id = raw_opp.get("noticeId", "")
                if notice_id in seen_ids:
                    continue
                seen_ids.add(notice_id)
                results.append(_normalize_opportunity(raw_opp))

    logger.info("SAM.gov: %d unique opportunities across %d keyword queries", len(results), len(keywords))
    return results
