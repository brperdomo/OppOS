"""Manual RFP submission — paste a URL or upload a file from any source."""

from __future__ import annotations

import hashlib
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

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Sec-Ch-Ua": '"Chromium";v="126", "Not A(Brand";v="8", "Google Chrome";v="126"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}


def _try_fetch(url: str, use_http2: bool = False, warm_session: bool = False) -> httpx.Response:
    """Single fetch attempt with configurable options."""
    kwargs: dict = {
        "timeout": 30.0,
        "follow_redirects": True,
        "headers": _HEADERS,
    }
    if use_http2:
        try:
            import h2  # noqa: F401
            kwargs["http2"] = True
        except ImportError:
            pass

    with httpx.Client(**kwargs) as client:
        if warm_session:
            parsed = urlparse(url)
            try:
                client.get(f"{parsed.scheme}://{parsed.netloc}/")
            except Exception:
                pass
        return client.get(url)


def fetch_page(url: str) -> dict:
    """Fetch a URL with multiple strategies. Returns html, text, content_type, error."""
    is_aspx = ".aspx" in url.lower() or ".asp" in url.lower()

    # Strategy list: try progressively simpler approaches
    strategies = [
        {"use_http2": False, "warm_session": is_aspx, "label": "standard"},
        {"use_http2": False, "warm_session": True, "label": "with session warm-up"},
    ]
    if not is_aspx:
        # For non-aspx, also try http2
        strategies.insert(0, {"use_http2": True, "warm_session": False, "label": "http2"})

    last_code = 0
    for strat in strategies:
        try:
            resp = _try_fetch(url, use_http2=strat["use_http2"], warm_session=strat["warm_session"])
            resp.raise_for_status()
            ct = resp.headers.get("content-type", "")
            return {
                "html": resp.text if "html" in ct else "",
                "raw_bytes": resp.content if "html" not in ct else None,
                "text": _html_to_text(resp.text) if "html" in ct else "",
                "content_type": ct,
                "status_code": resp.status_code,
                "error": None,
            }
        except httpx.HTTPStatusError as e:
            last_code = e.response.status_code
            logger.info("Fetch strategy '%s' got HTTP %d for %s", strat["label"], last_code, url)
            if last_code not in (403, 406, 429):
                break  # non-retryable status, stop trying
        except Exception as e:
            logger.info("Fetch strategy '%s' failed for %s: %s", strat["label"], url, e)
            continue

    # All strategies failed
    if last_code == 401:
        msg = f"HTTP {last_code} — this page requires authentication. Try uploading the PDF directly."
    elif last_code == 403:
        msg = (
            f"HTTP {last_code} — this site blocks requests from cloud servers. "
            f"Download the page/PDF on your computer and use the Upload File tab instead."
        )
    elif last_code:
        msg = f"HTTP {last_code}"
    else:
        msg = "Could not connect to the site. Check the URL and try again."
    return {"html": "", "raw_bytes": None, "text": "", "content_type": "", "status_code": last_code, "error": msg}


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


_SCANNABLE_EXTENSIONS = {".pdf", ".docx", ".doc"}
_DOWNLOAD_PATTERNS = re.compile(r"/download|/attachment|/file|/document|/getfile", re.IGNORECASE)


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

def submit_url(url: str, on_progress=None) -> dict[str, Any]:
    """Submit a URL for analysis. Returns the scored opportunity dict.

    on_progress(step: str, detail: str) is called at each stage.
    """
    from oppos.scoring.qualifier import qualify
    from oppos.sources.extract_text import extract_file, SCANNABLE_EXTENSIONS, MAX_TOTAL_TEXT
    from oppos.storage.db import is_seen, upsert_opportunity

    def _progress(step, detail=""):
        if on_progress:
            on_progress(step, detail)

    source_id = _make_source_id(url)

    # Check dedup
    if is_seen(source_id):
        _progress("duplicate", "This URL has already been submitted. Re-scoring...")

    # Fetch page
    _progress("fetch", f"Fetching {url}")
    page = fetch_page(url)
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

        _progress("extract_text", f"Extracting text from {fname}")
        result = extract_file(filepath)
        doc_text = result.get("text", "")

        _progress("metadata", "Extracting metadata with AI...")
        meta = extract_metadata(doc_text, url)

        opp = _build_opportunity(source_id, url, meta)
        opp["attachment_text"] = doc_text

        _progress("scoring", "Scoring with Claude...")
        scored = qualify(opp, attachment_text=doc_text)
        scored["attachment_text"] = doc_text
        upsert_opportunity(scored)
        return scored

    # HTML page flow
    _progress("metadata", "Extracting metadata with AI...")
    meta = extract_metadata(page["text"], url)

    # Find and download attachments
    links = find_attachment_links(page["html"], url)
    att_text = ""
    att_files: list[Path] = []
    if links:
        _progress("attachments", f"Found {len(links)} attachment(s) — downloading...")
        att_files = download_manual_attachments(source_id, links)

        # Extract text from downloaded files
        scannable = [f for f in att_files if f.suffix.lower() in SCANNABLE_EXTENSIONS]
        if scannable:
            _progress("extract_text", f"Extracting text from {len(scannable)} file(s)...")
            text_parts = []
            total_chars = 0
            for fpath in scannable:
                if total_chars >= MAX_TOTAL_TEXT:
                    break
                result = extract_file(fpath)
                if result.get("text"):
                    text_parts.append(f"--- {fpath.name} ---\n{result['text']}")
                    total_chars += result.get("chars", 0)
                    _progress("extract_text", f"  ✅ {fpath.name} — {result.get('chars', 0):,} chars")
            att_text = "\n\n".join(text_parts)[:MAX_TOTAL_TEXT]

    opp = _build_opportunity(source_id, url, meta)
    if att_text:
        opp["attachment_text"] = att_text

    _progress("scoring", "Scoring with Claude...")
    scored = qualify(opp, attachment_text=att_text)
    scored["attachment_text"] = att_text or None
    upsert_opportunity(scored)
    scored["_att_files"] = [str(f) for f in att_files]
    return scored


def submit_file(file_bytes: bytes, filename: str, on_progress=None) -> dict[str, Any]:
    """Submit an uploaded file for analysis. Returns the scored opportunity dict."""
    from oppos.scoring.qualifier import qualify
    from oppos.sources.extract_text import extract_file
    from oppos.storage.db import upsert_opportunity

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
    _progress("extract_text", f"Extracting text from {filename}...")
    result = extract_file(filepath)
    doc_text = result.get("text", "")

    if not doc_text:
        return {"error": f"Could not extract text from {filename}: {result.get('error', 'unknown')}"}

    _progress("extract_text", f"  ✅ {filename} — {result.get('chars', 0):,} chars, {result.get('pages', 0)} pages")

    # Extract metadata
    _progress("metadata", "Extracting metadata with AI...")
    meta = extract_metadata(doc_text)

    opp = _build_opportunity(source_id, "", meta)
    opp["url"] = ""
    opp["attachment_text"] = doc_text

    _progress("scoring", "Scoring with Claude...")
    scored = qualify(opp, attachment_text=doc_text)
    scored["attachment_text"] = doc_text
    upsert_opportunity(scored)
    scored["_att_files"] = [str(filepath)]
    return scored


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
