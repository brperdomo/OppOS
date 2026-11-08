"""Manual RFP submission — paste a URL or upload a file from any source."""

from __future__ import annotations

import hashlib
from datetime import datetime
import json
import logging
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import anthropic
import httpx

from oppos.config import ANTHROPIC_API_KEY, SCORING_MODEL_STAGE1
from oppos.sources.attachments import ATTACHMENTS_DIR, _sanitize_filename

logger = logging.getLogger(__name__)

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client


# ---------------------------------------------------------------------------
# HTML text extraction (strip tags, keep visible text)
# ---------------------------------------------------------------------------

class _TextExtractor(HTMLParser):
    """Simple HTML→plain-text converter."""

    _SKIP_TAGS = {"script", "style", "noscript", "svg", "head"}

    def __init__(self):
        super().__init__()
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() in self._SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag.lower() in self._SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data):
        if self._skip_depth == 0:
            text = data.strip()
            if text:
                self._parts.append(text)

    def get_text(self) -> str:
        return "\n".join(self._parts)


def _html_to_text(html: str) -> str:
    parser = _TextExtractor()
    try:
        parser.feed(html)
    except Exception:
        pass
    return parser.get_text()


# ---------------------------------------------------------------------------
# Page fetching
# ---------------------------------------------------------------------------

# OppOS identifies itself. Pages that turn automated visitors away (Cloudflare checks, 403s) are not worked around:
# the person opens the page in their browser, downloads the RFP files and uploads them instead.
_HEADERS = {
    "User-Agent": "OppOS/1.0 (Nutrient RFP monitor)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

_BLOCKED_MARKERS = ("just a moment", "checking your browser", "verifying you are human", "security check",
                    "performing security verification", "attention required")
_UPLOAD_INSTEAD = ("Open it in your browser, download the RFP files, and upload them instead (Add an RFP → "
                   "I have the document, or the pursuit's RFP and documents tab).")


def fetch_page(url: str, on_progress=None) -> dict:
    """Fetch a URL once, as OppOS. Returns html, text, content_type, error."""
    if on_progress:
        on_progress("fetch", "Fetching the page…")
    try:
        with httpx.Client(timeout=30.0, follow_redirects=True, headers=_HEADERS) as client:
            resp = client.get(url)
    except Exception as e:
        logger.info("Fetch failed for %s: %s", url, e)
        return {"html": "", "raw_bytes": None, "text": "", "content_type": "", "status_code": 0,
                "error": "Could not connect to the site. Check the address and try again."}
    ct = resp.headers.get("content-type", "")
    if resp.status_code >= 400:
        blocked = resp.status_code in (403, 429) or any(m in resp.text[:2000].lower() for m in _BLOCKED_MARKERS)
        if resp.status_code == 401:
            msg = "This page needs a login. " + _UPLOAD_INSTEAD
        elif blocked:
            msg = "This site doesn't allow automated access. " + _UPLOAD_INSTEAD
        else:
            msg = f"The site answered HTTP {resp.status_code}. Check the address, or " + _UPLOAD_INSTEAD[0].lower() + _UPLOAD_INSTEAD[1:]
        return {"html": "", "raw_bytes": None, "text": "", "content_type": ct, "status_code": resp.status_code, "error": msg}
    if "html" in ct and any(m in resp.text[:2000].lower() for m in _BLOCKED_MARKERS):
        return {"html": "", "raw_bytes": None, "text": "", "content_type": ct, "status_code": resp.status_code,
                "error": "This site shows a human check to automated visitors. " + _UPLOAD_INSTEAD}
    if "html" in ct and len(_html_to_text(resp.text).strip()) < 500:
        return {"html": "", "raw_bytes": None, "text": "", "content_type": ct, "status_code": resp.status_code,
                "error": "The page came back nearly empty — it may need a browser or a login to show the RFP. " + _UPLOAD_INSTEAD}
    return {
        "html": resp.text if "html" in ct else "",
        "raw_bytes": resp.content if "html" not in ct else None,
        "text": _html_to_text(resp.text) if "html" in ct else "",
        "content_type": ct,
        "status_code": resp.status_code,
        "error": None,
    }


def is_direct_file_url(url: str, content_type: str = "") -> bool:
    """Check if the URL points directly to a downloadable file."""
    path = urlparse(url).path.lower()
    if any(path.endswith(ext) for ext in (".pdf", ".docx", ".doc")):
        return True
    if any(t in content_type for t in ("application/pdf", "application/msword", "officedocument")):
        return True
    return False


# ---------------------------------------------------------------------------
# Link extraction (find downloadable attachments on page)
# ---------------------------------------------------------------------------

class _LinkExtractor(HTMLParser):
    """Extract <a href> links from HTML."""

    def __init__(self):
        super().__init__()
        self.links: list[tuple[str, str]] = []  # (href, text)
        self._current_href: str | None = None
        self._current_text: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            href = dict(attrs).get("href", "")
            if href:
                self._current_href = href
                self._current_text = []

    def handle_data(self, data):
        if self._current_href is not None:
            self._current_text.append(data.strip())

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._current_href:
            self.links.append((self._current_href, " ".join(self._current_text)))
            self._current_href = None
            self._current_text = []


from oppos.sources.extract_text import READABLE_EXTENSIONS as _SCANNABLE_EXTENSIONS  # attachment links worth fetching
_DOWNLOAD_PATTERNS = re.compile(r"/download|/attachment|/file|/document|/getfile", re.IGNORECASE)


_PERISCOPE_DOMAINS = {
    "commbuys.com", "nevadaepro.com", "njstart.gov",
    "bidbuy.illinois.gov", "oregonbuys.gov", "arbuy.arkansas.gov",
    "app.az.gov", "caleprocure.ca.gov",
}


def _detect_periscope(url: str) -> tuple[str, str] | None:
    """If *url* is a Periscope/SOVRA bid detail page, return (base_url, docId).

    Returns None for non-Periscope URLs.
    """
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if not any(host == d or host.endswith("." + d) for d in _PERISCOPE_DOMAINS):
        return None

    # Extract docId from query string
    from urllib.parse import parse_qs
    qs = parse_qs(parsed.query)
    doc_id = (qs.get("docId") or qs.get("docid") or [""])[0]
    if not doc_id:
        return None

    base = f"{parsed.scheme}://{parsed.netloc}"
    return base, doc_id


def find_attachment_links(html: str, base_url: str) -> list[dict]:
    """Find PDF/DOCX links on a page. Returns list of {url, filename, ext}."""
    parser = _LinkExtractor()
    try:
        parser.feed(html)
    except Exception:
        pass

    results = []
    seen_urls = set()

    for href, text in parser.links:
        full_url = urljoin(base_url, href)
        if full_url in seen_urls:
            continue

        path = urlparse(full_url).path.lower()
        ext = Path(path).suffix

        # Match by extension
        if ext in _SCANNABLE_EXTENSIONS:
            fname = Path(urlparse(full_url).path).name or text or f"attachment{ext}"
            results.append({"url": full_url, "filename": _sanitize_filename(fname), "ext": ext})
            seen_urls.add(full_url)
            continue

        # Match by URL pattern + link text hinting at a document
        if _DOWNLOAD_PATTERNS.search(href):
            fname = text.strip() if text.strip() else "attachment.pdf"
            if not Path(fname).suffix:
                fname += ".pdf"
            results.append({"url": full_url, "filename": _sanitize_filename(fname), "ext": Path(fname).suffix})
            seen_urls.add(full_url)

    return results


# ---------------------------------------------------------------------------
# Attachment downloading
# ---------------------------------------------------------------------------

def download_manual_attachments(source_id: str, links: list[dict]) -> list[Path]:
    """Download attachment links to the attachments directory."""
    opp_dir = ATTACHMENTS_DIR / _sanitize_filename(source_id)
    opp_dir.mkdir(parents=True, exist_ok=True)
    downloaded: list[Path] = []

    with httpx.Client(timeout=60.0, follow_redirects=True, headers=_HEADERS) as client:
        for link in links:
            try:
                resp = client.get(link["url"])
                resp.raise_for_status()

                # Try to get real filename from content-disposition
                disposition = resp.headers.get("content-disposition", "")
                fname_match = re.search(r'filename="?([^";\n]+)"?', disposition)
                if fname_match:
                    fname = _sanitize_filename(fname_match.group(1))
                else:
                    fname = link["filename"]

                filepath = opp_dir / fname
                filepath.write_bytes(resp.content)
                downloaded.append(filepath)
                logger.info("Downloaded: %s (%d bytes)", fname, len(resp.content))
            except Exception as e:
                logger.warning("Failed to download %s: %s", link["url"], e)

    return downloaded


# ---------------------------------------------------------------------------
# Claude metadata extraction
# ---------------------------------------------------------------------------

_EXTRACT_SYSTEM = """You are a structured data extractor for RFP/procurement listings.

Given the text content of a web page or document about an RFP or procurement opportunity, extract the following fields. Return ONLY valid JSON — no markdown, no explanation.

If a field is not found, use an empty string "". For dates, use ISO 8601 format (YYYY-MM-DD).

{
    "title": "the RFP/solicitation title",
    "agency": "the issuing agency or organization name",
    "solicitation_number": "RFP/solicitation/bid number",
    "notice_type": "solicitation, presolicitation, RFI, amendment, etc.",
    "description": "summary of what is being requested (max 500 words)",
    "posted_date": "when posted (YYYY-MM-DD)",
    "response_deadline": "submission deadline (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)",
    "contact_name": "point of contact full name",
    "contact_email": "point of contact email",
    "contact_phone": "point of contact phone",
    "place_of_performance": "where the work will be performed (city, state)",
    "office": "specific office or department within the agency",
    "naics_code": "NAICS code if mentioned",
    "set_aside": "small business set-aside type if mentioned"
}"""


def extract_metadata(text: str, url: str = "") -> dict[str, Any]:
    """Use Claude to extract structured RFP metadata from page/document text."""
    truncated = text[:8000]

    user_msg = f"Extract RFP metadata from this content"
    if url:
        user_msg += f" (source: {url})"
    user_msg += f":\n\n{truncated}"

    try:
        resp = _get_client().messages.create(
            model=SCORING_MODEL_STAGE1,
            max_tokens=1024,
            system=_EXTRACT_SYSTEM,
            messages=[{"role": "user", "content": user_msg}],
        )
        raw = resp.content[0].text.strip()
        # Handle markdown code blocks
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
        return json.loads(raw)
    except (json.JSONDecodeError, Exception) as e:
        logger.warning("Metadata extraction failed: %s", e)
        return {}


# ---------------------------------------------------------------------------
# Source ID generation
# ---------------------------------------------------------------------------

def _make_source_id(content: str | bytes) -> str:
    if isinstance(content, str):
        content = content.encode()
    return f"manual-{hashlib.sha256(content).hexdigest()[:12]}"


# ---------------------------------------------------------------------------
# Orchestrators
# ---------------------------------------------------------------------------

def _read_folder(source_id: str, _progress) -> tuple[str, str]:
    """Read every file in the submission's folder with the shared reader (stored per document, so the desk lists
    them and nothing is read twice). Returns (text for drafting, text for scoring)."""
    from oppos.sources.rfp_documents import DRAFT_BUDGET, SCORING_BUDGET, digest_for, read_rfp_documents
    res = read_rfp_documents({"source_id": source_id, "source": "manual"},
                             on_progress=lambda name, i, n: _progress("extract_text", f"Reading {name} ({i + 1}/{n})"))
    if res["read"]:
        _progress("extract_text", f"  ✅ {res['read']} of {res['files']} document(s) read")
    for name, note in res["failed"]:
        _progress("extract_text", f"  ❌ {name} — {note}")
    return digest_for(source_id, DRAFT_BUDGET), digest_for(source_id, SCORING_BUDGET)


def submit_url(url: str, on_progress=None) -> dict[str, Any]:
    """Submit a URL for analysis. Returns the scored opportunity dict.

    on_progress(step: str, detail: str) is called at each stage.
    """
    from oppos.scoring.qualifier import qualify
    from oppos.storage.db import is_seen, set_pipeline_status, upsert_opportunity

    def _progress(step, detail=""):
        if on_progress:
            on_progress(step, detail)

    source_id = _make_source_id(url)

    # Check dedup
    if is_seen(source_id):
        _progress("duplicate", "This URL has already been submitted. Re-scoring...")

    # Fetch page
    _progress("fetch", f"Fetching {url}")
    page = fetch_page(url, on_progress=on_progress)
    if page["error"]:
        return {"error": page["error"]}

    # Direct file URL (e.g. user pasted a link to a PDF)
    if is_direct_file_url(url, page["content_type"]):
        _progress("direct_file", "URL points to a file — downloading...")
        opp_dir = ATTACHMENTS_DIR / _sanitize_filename(source_id)
        opp_dir.mkdir(parents=True, exist_ok=True)
        parsed_path = urlparse(url).path
        fname = Path(parsed_path).name or "document.pdf"
        filepath = opp_dir / _sanitize_filename(fname)

        if page["raw_bytes"]:
            filepath.write_bytes(page["raw_bytes"])
        else:
            # Re-fetch as bytes
            try:
                resp = httpx.get(url, timeout=60.0, follow_redirects=True, headers=_HEADERS)
                filepath.write_bytes(resp.content)
            except Exception as e:
                return {"error": f"Failed to download file: {e}"}

        doc_text, score_text = _read_folder(source_id, _progress)

        _progress("metadata", "Extracting metadata with AI...")
        meta = extract_metadata(score_text, url)

        opp = _build_opportunity(source_id, url, meta)
        opp["attachment_text"] = doc_text

        _progress("scoring", "Scoring with Claude...")
        scored = qualify(opp, attachment_text=score_text)
        scored["attachment_text"] = doc_text or None
        upsert_opportunity(scored)
        set_pipeline_status(source_id, "qualified", notes="Manual submission — file analyzed")
        return scored

    # HTML page flow
    _progress("metadata", "Extracting metadata with AI...")
    meta = extract_metadata(page["text"], url)

    # Find and download attachments
    att_text = ""
    att_files: list[Path] = []

    # Periscope/SOVRA sites use JavaScript downloadFile() calls, not <a> links.
    # Route through the dedicated Periscope downloader which handles CSRF + POST.
    periscope_info = _detect_periscope(url)
    if periscope_info:
        p_base, p_doc_id = periscope_info
        _progress("attachments", "Periscope site detected — downloading via CSRF handler...")
        from oppos.sources.attachments import download_periscope
        fake_opp = {"source_id": source_id, "solicitation_number": p_doc_id}
        att_files = download_periscope(fake_opp, p_base)
        if att_files:
            _progress("attachments", f"Downloaded {len(att_files)} file(s) from Periscope")
        else:
            _progress("attachments", "No downloadable files found on this bid")
        # Also use the doc_id as solicitation_number if Claude didn't extract one
        if not meta.get("solicitation_number"):
            meta["solicitation_number"] = p_doc_id
    else:
        links = find_attachment_links(page["html"], url)
        if links:
            _progress("attachments", f"Found {len(links)} attachment(s) — downloading...")
            att_files = download_manual_attachments(source_id, links)

    # Read the downloaded files
    score_text = ""
    if att_files:
        att_text, score_text = _read_folder(source_id, _progress)

    opp = _build_opportunity(source_id, url, meta)
    if att_text:
        opp["attachment_text"] = att_text

    _progress("scoring", "Scoring with Claude...")
    scored = qualify(opp, attachment_text=score_text)
    scored["attachment_text"] = att_text or None
    upsert_opportunity(scored)
    # If we extracted document text, go straight to Qualified; otherwise New
    if att_text:
        set_pipeline_status(source_id, "qualified", notes="Manual submission — documents analyzed")
    scored["_att_files"] = [str(f) for f in att_files]
    return scored


def submit_file(file_bytes: bytes, filename: str, on_progress=None) -> dict[str, Any]:
    """Submit an uploaded file for analysis. Returns the scored opportunity dict."""
    from oppos.scoring.qualifier import qualify
    from oppos.storage.db import set_pipeline_status, upsert_opportunity

    def _progress(step, detail=""):
        if on_progress:
            on_progress(step, detail)

    source_id = _make_source_id(file_bytes)

    # Save file
    opp_dir = ATTACHMENTS_DIR / _sanitize_filename(source_id)
    opp_dir.mkdir(parents=True, exist_ok=True)
    filepath = opp_dir / _sanitize_filename(filename)
    filepath.write_bytes(file_bytes)

    # Extract text
    doc_text, score_text = _read_folder(source_id, _progress)
    if not doc_text:
        from oppos.storage.db import get_documents
        note = next((d.get("note") for d in get_documents(source_id) if d["name"] == filepath.name), "") or "unknown"
        return {"error": f"Could not read {filename}: {note}"}

    # Extract metadata
    _progress("metadata", "Extracting metadata with AI...")
    meta = extract_metadata(score_text)

    opp = _build_opportunity(source_id, "", meta)
    opp["url"] = ""
    opp["attachment_text"] = doc_text

    _progress("scoring", "Scoring with Claude...")
    scored = qualify(opp, attachment_text=score_text)
    scored["attachment_text"] = doc_text
    upsert_opportunity(scored)
    set_pipeline_status(source_id, "qualified", notes="Manual submission — file analyzed")
    scored["_att_files"] = [str(filepath)]
    return scored


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def submit_details(fields: dict[str, Any], score: bool = True, on_progress=None) -> dict[str, Any]:
    """Add an RFP typed in by hand (no link or document needed). `fields`: title (required), agency, response_deadline
    (YYYY-MM-DD), url, solicitation_number, description, contact_name/email/phone. Scored from the description when
    `score` is set and there is one; otherwise stored unscored (fit 0) so the owner can score it later."""
    import uuid
    from oppos.scoring.qualifier import qualify
    from oppos.storage.db import set_pipeline_status, upsert_opportunity

    title = (fields.get("title") or "").strip()
    if not title:
        return {"error": "A title is required"}
    source_id = _make_source_id(f"{title}|{fields.get('agency', '')}|{fields.get('url', '')}|{uuid.uuid4()}")
    meta = {k: (fields.get(k) or "") for k in ("title", "agency", "response_deadline", "solicitation_number", "description",
                                              "contact_name", "contact_email", "contact_phone", "place_of_performance")}
    meta["title"] = title
    meta["notice_type"] = fields.get("notice_type") or "Solicitation"
    opp = _build_opportunity(source_id, (fields.get("url") or "").strip(), meta)
    opp["posted_date"] = datetime.utcnow().strftime("%Y-%m-%d")
    if score and meta["description"].strip():
        if on_progress:
            on_progress("scoring", "Scoring the fit from what you entered")
        try:
            opp = qualify(opp)
            status, note = "qualified", "Added by hand — scored from the description"
        except Exception as e:
            opp.setdefault("fit_score", 0)
            status, note = "new", f"Added by hand — scoring failed ({type(e).__name__}); score it from Find RFPs later"
    else:
        opp.setdefault("fit_score", 0)
        status, note = "new", "Added by hand — not scored yet"
    upsert_opportunity(opp)
    set_pipeline_status(source_id, status, notes=note)
    opp["pipeline_status"] = status
    return opp


def _build_opportunity(source_id: str, url: str, meta: dict) -> dict[str, Any]:
    """Build an opportunity dict from extracted metadata."""
    return {
        "source_id": source_id,
        "source": "manual",
        "title": meta.get("title", "Manual Submission"),
        "solicitation_number": meta.get("solicitation_number", ""),
        "notice_type": meta.get("notice_type", ""),
        "agency": meta.get("agency", ""),
        "posted_date": meta.get("posted_date", ""),
        "response_deadline": meta.get("response_deadline", ""),
        "url": url,
        "description": meta.get("description", ""),
        "point_of_contact": {
            "name": meta.get("contact_name", ""),
            "email": meta.get("contact_email", ""),
            "phone": meta.get("contact_phone", ""),
        },
        "place_of_performance": meta.get("place_of_performance", ""),
        "office": meta.get("office", ""),
        "naics_code": meta.get("naics_code", ""),
        "set_aside": meta.get("set_aside", ""),
    }
