"""Target account monitoring for private-sector RFP discovery.

Watches a curated list of high-value organizations (hospitals, universities,
enterprises) for new RFPs on their procurement pages.  Uses content hashing
to skip pages that haven't changed since the last check.

The watchlist lives in ``data/target_accounts.json`` so new accounts can be
added without code changes.  Falls back to an empty list if the file is
missing.

Each monitored page is fetched with the same ``fetch_page()`` pipeline used
for manual URL submissions (handles Cloudflare, retries, Playwright).  New
links found on procurement pages are extracted with Claude and fed into the
standard scoring pipeline.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from oppos.storage.db import get_meta, set_meta, is_seen

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_ACCOUNTS_FILE = _DATA_DIR / "target_accounts.json"

# How often to re-check each account (hours)
_DEFAULT_CHECK_INTERVAL_HOURS = 24


# ---------------------------------------------------------------------------
# Watchlist loading
# ---------------------------------------------------------------------------

def _load_accounts() -> list[dict]:
    """Load target accounts from the JSON watchlist."""
    if not _ACCOUNTS_FILE.exists():
        logger.warning("Target accounts file not found: %s", _ACCOUNTS_FILE)
        return []

    try:
        with open(_ACCOUNTS_FILE) as f:
            data = json.load(f)
        accounts = data.get("accounts", [])
        logger.info("Loaded %d target accounts from %s", len(accounts), _ACCOUNTS_FILE.name)
        return accounts
    except (json.JSONDecodeError, KeyError) as e:
        logger.error("Failed to parse target accounts: %s", e)
        return []


# ---------------------------------------------------------------------------
# Change detection
# ---------------------------------------------------------------------------

def _content_hash(text: str) -> str:
    """SHA-256 hash of page text for change detection."""
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _page_hash_key(account_key: str, url: str) -> str:
    url_hash = hashlib.sha256(url.encode()).hexdigest()[:8]
    return f"ta_hash_{account_key}_{url_hash}"


def _last_check_key(account_key: str) -> str:
    return f"ta_last_check_{account_key}"


def _should_check(account_key: str) -> bool:
    """Return True if this account is due for a check."""
    raw = get_meta(_last_check_key(account_key))
    if not raw:
        return True
    try:
        last = datetime.fromisoformat(raw)
        return datetime.utcnow() - last > timedelta(hours=_DEFAULT_CHECK_INTERVAL_HOURS)
    except ValueError:
        return True


def _mark_checked(account_key: str) -> None:
    set_meta(_last_check_key(account_key), datetime.utcnow().isoformat())


# ---------------------------------------------------------------------------
# Link discovery on procurement pages
# ---------------------------------------------------------------------------

_RFP_LINK_PATTERNS = re.compile(
    r"rfp|rfi|rfq|request\s+for\s+proposal|solicitation|bid\s+opportunit|"
    r"procurement|\.pdf|\.docx?|/download|/attachment",
    re.IGNORECASE,
)


def _find_rfp_links(html: str, base_url: str) -> list[dict]:
    """Find links on a procurement page that look like RFP postings.

    More aggressive than manual.py's find_attachment_links — also catches
    links to RFP listing pages, not just downloadable files.
    """
    from oppos.sources.manual import _LinkExtractor

    parser = _LinkExtractor()
    try:
        parser.feed(html)
    except Exception:
        pass

    results = []
    seen = set()

    for href, text in parser.links:
        full_url = urljoin(base_url, href)
        if full_url in seen:
            continue

        # Skip navigation / social / mailto links
        parsed = urlparse(full_url)
        if parsed.scheme not in ("http", "https"):
            continue
        if any(x in parsed.netloc for x in ("facebook.com", "twitter.com", "linkedin.com", "youtube.com")):
            continue

        combined = f"{href} {text}".lower()
        if _RFP_LINK_PATTERNS.search(combined):
            filename = Path(parsed.path).name or text.strip() or "page"
            ext = Path(parsed.path).suffix.lower()
            results.append({
                "url": full_url,
                "text": text.strip()[:200],
                "filename": filename,
                "ext": ext,
                "is_document": ext in (".pdf", ".docx", ".doc", ".xlsx"),
            })
            seen.add(full_url)

    return results


# ---------------------------------------------------------------------------
# Source ID generation
# ---------------------------------------------------------------------------

def _make_source_id(account_key: str, url: str) -> str:
    return f"ta-{account_key}-{hashlib.sha256(url.encode()).hexdigest()[:10]}"


# ---------------------------------------------------------------------------
# Process a single target account
# ---------------------------------------------------------------------------

def _process_account(account: dict) -> list[dict[str, Any]]:
    """Check one target account for new RFPs."""
    from oppos.sources.manual import fetch_page, extract_metadata

    key = account["key"]
    name = account["name"]
    industry = account.get("industry", "")
    urls = account.get("urls", [])

    if not urls:
        return []

    results: list[dict[str, Any]] = []

    for url in urls:
        logger.info("Target account: checking %s → %s", name, url[:80])

        page = fetch_page(url)
        if page.get("error"):
            logger.warning("Target account %s: fetch failed: %s", key, page["error"])
            continue

        text = page.get("text", "")
        html = page.get("html", "")

        if not text or len(text.strip()) < 50:
            logger.debug("Target account %s: page too thin, skipping", key)
            continue

        # Change detection — skip if page hasn't changed
        current_hash = _content_hash(text)
        hash_key = _page_hash_key(key, url)
        stored_hash = get_meta(hash_key)

        if stored_hash == current_hash:
            logger.debug("Target account %s: page unchanged, skipping", key)
            continue

        logger.info("Target account %s: page changed (or first check), processing…", key)
        set_meta(hash_key, current_hash)

        # Find RFP-related links on the page
        links = _find_rfp_links(html, url)
        logger.info("Target account %s: found %d RFP-related links", key, len(links))

        for link in links:
            source_id = _make_source_id(key, link["url"])

            if is_seen(source_id):
                continue

            # For document links (PDFs), we'll let the pipeline download and
            # extract them.  For page links, fetch and extract metadata now.
            if link["is_document"]:
                opp = {
                    "source_id": source_id,
                    "source": "target_accounts",
                    "url": link["url"],
                    "title": link["text"] or f"RFP from {name}",
                    "description": f"Document found on {name} procurement page: {link['text']}",
                    "agency": name,
                    "office": industry,
                    "solicitation_number": "",
                    "notice_type": "",
                    "posted_date": "",
                    "response_deadline": "",
                    "naics_code": "",
                    "set_aside": "",
                    "classification_code": "",
                    "resource_links": [link["url"]],
                    "point_of_contact": {},
                    "place_of_performance": "",
                    "raw": {"account": key, "link_text": link["text"]},
                }
                results.append(opp)
            else:
                # Fetch the linked page and extract metadata
                link_page = fetch_page(link["url"])
                if link_page.get("error") or not link_page.get("text"):
                    continue

                meta = extract_metadata(link_page["text"], link["url"])
                opp = {
                    "source_id": source_id,
                    "source": "target_accounts",
                    "url": link["url"],
                    "title": meta.get("title") or link["text"] or f"RFP from {name}",
                    "description": meta.get("description", ""),
                    "agency": meta.get("agency") or name,
                    "office": meta.get("office") or industry,
                    "solicitation_number": meta.get("solicitation_number", ""),
                    "notice_type": meta.get("notice_type", ""),
                    "posted_date": meta.get("posted_date", ""),
                    "response_deadline": meta.get("response_deadline", ""),
                    "naics_code": meta.get("naics_code", ""),
                    "set_aside": meta.get("set_aside", ""),
                    "classification_code": "",
                    "resource_links": [],
                    "point_of_contact": {
                        "name": meta.get("contact_name", ""),
                        "email": meta.get("contact_email", ""),
                        "phone": meta.get("contact_phone", ""),
                    },
                    "place_of_performance": meta.get("place_of_performance", ""),
                    "raw": {"account": key, "link_text": link["text"]},
                }
                results.append(opp)

    return results


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_opportunities(limit: int = 50) -> list[dict[str, Any]]:
    """Check all due target accounts for new RFPs.

    Only accounts that haven't been checked in the last 24 hours are
    processed.  Pages that haven't changed (by content hash) are skipped
    entirely.
    """
    accounts = _load_accounts()
    if not accounts:
        return []

    results: list[dict[str, Any]] = []

    for account in accounts:
        key = account.get("key", "")
        if not key:
            continue

        if not _should_check(key):
            logger.debug("Target account %s: checked recently, skipping", key)
            continue

        try:
            opps = _process_account(account)
            results.extend(opps)
            _mark_checked(key)
        except Exception as e:
            logger.error("Target account %s failed: %s", key, e)

        if len(results) >= limit:
            break

    logger.info("Target accounts: %d new opportunities found", len(results))
    return results
