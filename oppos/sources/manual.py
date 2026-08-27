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

# Optional Playwright for Cloudflare bypass
_PLAYWRIGHT_AVAILABLE = False
try:
    import playwright.sync_api  # noqa: F401
    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    pass

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


_STEALTH_JS = """
// Hide navigator.webdriver
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

// Realistic plugins array
Object.defineProperty(navigator, 'plugins', {
    get: () => {
        const arr = [
            { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
            { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
            { name: 'Native Client', filename: 'internal-nacl-plugin' },
        ];
        arr.item = i => arr[i];
        arr.namedItem = n => arr.find(p => p.name === n);
        arr.refresh = () => {};
        return arr;
    },
});

// Realistic languages
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });

// chrome.runtime stub
window.chrome = window.chrome || {};
window.chrome.runtime = window.chrome.runtime || {};

// Permissions query override
const _origPermQuery = navigator.permissions?.query?.bind(navigator.permissions);
if (_origPermQuery) {
    navigator.permissions.query = params =>
        params.name === 'notifications'
            ? Promise.resolve({ state: Notification.permission })
            : _origPermQuery(params);
}
"""

_CF_CHALLENGE_MARKERS = frozenset([
    "just a moment",
    "checking your browser",
    "performing security verification",
    "verifying you are human",
    "security check",
])


def _is_cf_challenge(text: str) -> bool:
    """Return True if *text* (title or body snippet) looks like a Cloudflare challenge."""
    low = text.lower()
    return any(marker in low for marker in _CF_CHALLENGE_MARKERS)


def _try_playwright_fetch(url: str) -> dict | None:
    """Fetch a Cloudflare-protected page with a real browser.

    Uses **headed mode** (visible Chrome window) because Cloudflare's
    Turnstile challenge detects headless browsers.  The window opens
    briefly (~5 s) and closes automatically once the page is loaded.

    For React SPAs like OpenGov, also tries to expand collapsed content
    sections so the full text is captured.

    Returns a ``fetch_page()``-compatible dict with an extra ``_pw_cookies``
    key that downstream code can use to download attachments through the
    same Cloudflare-cleared session.  Returns *None* on failure.
    """
    if not _PLAYWRIGHT_AVAILABLE:
        logger.warning(
            "playwright not installed — run: "
            "pip install playwright && playwright install chromium"
        )
        return None

    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as pw:
            # Headed mode + system Chrome is the only combo that clears
            # Cloudflare Turnstile.  Headless (even with stealth patches)
            # is detected.
            launch_kwargs: dict[str, Any] = {
                "headless": False,
                "args": ["--disable-blink-features=AutomationControlled"],
            }
            try:
                browser = pw.chromium.launch(channel="chrome", **launch_kwargs)
            except Exception:
                # System Chrome not available — fall back to bundled Chromium
                browser = pw.chromium.launch(**launch_kwargs)

            ctx = browser.new_context(
                viewport={"width": 1280, "height": 720},
                locale="en-US",
                timezone_id="America/New_York",
                color_scheme="light",
                accept_downloads=True,
            )
            ctx.add_init_script(_STEALTH_JS)

            page = ctx.new_page()

            logger.info("Playwright: opening browser for %s", url)
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)

            # Wait for Cloudflare challenge to clear (up to 30 s)
            cleared = False
            for i in range(30):
                title = page.title() or ""
                body_snippet = page.inner_text("body")[:500] if i % 3 == 0 else ""
                if not _is_cf_challenge(title) and not _is_cf_challenge(body_snippet):
                    cleared = True
                    break
                if i % 10 == 0:
                    logger.info("Playwright: waiting for Cloudflare… (%ds)", i)
                page.wait_for_timeout(1_000)

            if not cleared:
                logger.warning("Playwright: Cloudflare challenge did not clear after 30 s")
                browser.close()
                return None

            # Give SPA frameworks time to render
            try:
                page.wait_for_load_state("networkidle", timeout=15_000)
            except Exception:
                pass  # some pages never fully idle

            # Expand collapsed sections (OpenGov, etc.)
            for label in ("View All Sections", "Show All", "Expand All"):
                try:
                    btn = page.get_by_text(label, exact=False)
                    if btn.count() > 0:
                        btn.first.click()
                        page.wait_for_timeout(2_000)
                        logger.info("Playwright: expanded sections via '%s'", label)
                        break
                except Exception:
                    continue

            html = page.content()
            text = page.inner_text("body")
            cookies = ctx.cookies()

            browser.close()

            if not text or len(text.strip()) < 50:
                logger.warning(
                    "Playwright: page rendered but content too thin (%d chars)",
                    len((text or "").strip()),
                )
                return None

            logger.info("Playwright: fetched %d chars from %s", len(text), url)
            return {
                "html": html,
                "raw_bytes": None,
                "text": text,
                "content_type": "text/html",
                "status_code": 200,
                "error": None,
                "_pw_cookies": cookies,
            }
    except Exception as e:
        logger.error("Playwright fetch failed for %s: %s", url, e)
        return None


def _pw_download_attachments(
    source_id: str,
    links: list[dict],
    cookies: list[dict],
) -> list[Path]:
    """Download attachments via Playwright (for Cloudflare-protected sites).

    Uses the browser context's request API with Cloudflare clearance
    cookies obtained from ``_try_playwright_fetch``.
    """
    if not _PLAYWRIGHT_AVAILABLE or not links:
        return []

    from playwright.sync_api import sync_playwright

    opp_dir = ATTACHMENTS_DIR / _sanitize_filename(source_id)
    opp_dir.mkdir(parents=True, exist_ok=True)
    downloaded: list[Path] = []

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            ctx = browser.new_context(
                user_agent=_HEADERS["User-Agent"],
                accept_downloads=True,
            )
            if cookies:
                ctx.add_cookies(cookies)

            for link in links:
                try:
                    resp = ctx.request.get(link["url"], timeout=60_000)
                    if not resp.ok:
                        logger.warning(
                            "Playwright DL HTTP %d: %s",
                            resp.status,
                            link["url"],
                        )
                        continue

                    disp = resp.headers.get("content-disposition", "")
                    m = re.search(r'filename="?([^";\n]+)"?', disp)
                    fname = _sanitize_filename(
                        m.group(1) if m else link["filename"]
                    )
                    body = resp.body()
                    filepath = opp_dir / fname
                    filepath.write_bytes(body)
                    downloaded.append(filepath)
                    logger.info(
                        "Downloaded (Playwright): %s (%d bytes)",
                        fname,
                        len(body),
                    )
                except Exception as e:
                    logger.warning(
                        "Playwright DL failed for %s: %s", link["url"], e
                    )

            ctx.dispose()
            browser.close()
    except Exception as e:
        logger.warning("Playwright download session failed: %s", e)

    return downloaded


def fetch_page(url: str, on_progress=None) -> dict:
    """Fetch a URL with multiple strategies. Returns html, text, content_type, error."""
    def _progress(detail: str) -> None:
        if on_progress:
            on_progress("fetch", detail)

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
    last_body = ""
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
            last_body = e.response.text[:500]
            logger.info("Fetch strategy '%s' got HTTP %d for %s", strat["label"], last_code, url)
            # On Cloudflare 403, skip remaining httpx strategies — additional
            # failed requests raise the bot score and make Playwright less
            # likely to succeed.
            if last_code == 403 and "just a moment" in last_body.lower():
                break
            if last_code not in (403, 406, 429):
                break  # non-retryable status, stop trying
        except Exception as e:
            logger.info("Fetch strategy '%s' failed for %s: %s", strat["label"], url, e)
            continue

    is_cloudflare = "just a moment" in last_body.lower()

    # Cloudflare 403 — jump straight to Playwright (headed browser).
    # Doing this before /api/ prefix to avoid extra requests that
    # raise Cloudflare's bot score.  Brief pause lets Cloudflare's
    # rate-limiter settle before the real browser connects.
    if last_code == 403 and is_cloudflare:
        import time
        time.sleep(2)
        _progress("Cloudflare detected — opening browser to bypass…")
        logger.info("Cloudflare detected — launching browser to bypass…")
        pw_result = _try_playwright_fetch(url)
        if pw_result:
            return pw_result

        # Playwright failed or unavailable — try /api/ prefix as last resort
        parsed = urlparse(url)
        api_url = f"{parsed.scheme}://{parsed.netloc}/api{parsed.path}"
        logger.info("Trying /api/ prefix fallback: %s", api_url)
        try:
            resp = _try_fetch(api_url, use_http2=False, warm_session=False)
            if resp.status_code == 200:
                ct = resp.headers.get("content-type", "")
                html = resp.text if "html" in ct else ""
                text = _html_to_text(html) if html else ""
                if text and len(text) > 200:
                    logger.info("Cloudflare bypass succeeded via /api/ prefix")
                    return {
                        "html": html,
                        "raw_bytes": None,
                        "text": text,
                        "content_type": ct,
                        "status_code": 200,
                        "error": None,
                    }
        except Exception:
            pass

    # All strategies failed
    if last_code == 401:
        msg = f"HTTP {last_code} — this page requires authentication. Try uploading the PDF directly."
    elif last_code == 403 and is_cloudflare:
        if not _PLAYWRIGHT_AVAILABLE:
            msg = (
                "This site uses Cloudflare bot protection. Install Playwright for "
                "automatic bypass: pip install playwright && playwright install chromium"
            )
        else:
            msg = (
                "This site uses Cloudflare bot protection and the headless browser "
                "could not bypass it. Open the link in your browser, download the "
                "RFP document (PDF), and use the Upload File tab to submit it."
            )
    elif last_code == 403:
        msg = (
            f"HTTP {last_code} — this site blocks automated requests. "
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

def submit_url(url: str, on_progress=None) -> dict[str, Any]:
    """Submit a URL for analysis. Returns the scored opportunity dict.

    on_progress(step: str, detail: str) is called at each stage.
    """
    from oppos.scoring.qualifier import qualify
    from oppos.sources.extract_text import extract_file, SCANNABLE_EXTENSIONS, MAX_TOTAL_TEXT
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
            pw_cookies = page.get("_pw_cookies")
            if pw_cookies:
                _progress("attachments", "Using browser session for Cloudflare-protected downloads…")
                att_files = _pw_download_attachments(source_id, links, pw_cookies)
            else:
                att_files = download_manual_attachments(source_id, links)

    # Extract text from downloaded files
    if att_files:
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
    # If we extracted document text, go straight to Qualified; otherwise New
    if att_text:
        set_pipeline_status(source_id, "qualified", notes="Manual submission — documents analyzed")
    scored["_att_files"] = [str(f) for f in att_files]
    return scored


def submit_file(file_bytes: bytes, filename: str, on_progress=None) -> dict[str, Any]:
    """Submit an uploaded file for analysis. Returns the scored opportunity dict."""
    from oppos.scoring.qualifier import qualify
    from oppos.sources.extract_text import extract_file
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
    set_pipeline_status(source_id, "qualified", notes="Manual submission — file analyzed")
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
