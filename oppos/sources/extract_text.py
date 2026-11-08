"""Read RFP documents with Nutrient's Processor API (DWS `/build`, Markdown output).

One call per document returns Markdown — headings, lists and tables kept — for PDFs and for Office files the
API converts server-side (Word, Excel, PowerPoint, RTF, ODT, HTML, email, images). Scanned PDFs (no text layer)
are read again with the API's OCR action; a long PDF that times out is read in page ranges. Plain text files are
read locally.

Nothing here caps a document's text: the full text is stored per document (`rfp_documents`), and `build_digest`
makes the size-limited version scoring and drafting send to the model, main solicitation first.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

NUTRIENT_API_URL = "https://api.nutrient.io/build"
READABLE_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".docm", ".dotx", ".rtf", ".odt", ".xls", ".xlsx", ".xlsm", ".xlsb", ".ppt", ".pptx",
    ".pps", ".ppsx", ".html", ".htm", ".eml", ".msg", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".txt", ".md", ".csv",
}
_LOCAL_TEXT = {".txt", ".md", ".csv"}
SCANNED_CHARS_PER_PAGE = 200   # below this a PDF has no real text layer: read it again with OCR
PAGE_CHUNK = 25                # page range per call when a long PDF times out
REQUEST_TIMEOUT = 330.0        # the API's own sync limit is 5 minutes (408 after that)


def _get_api_key() -> str:
    return os.environ.get("NUTRIENT_API_KEY", "")


def _result(text: str = "", pages: int | None = None, status: str = "read", note: str = "") -> dict:
    return {"text": text, "pages": pages, "chars": len(text), "status": status, "note": note}


def _pdf_pages(path: Path) -> int | None:
    try:
        from pypdf import PdfReader
        return len(PdfReader(str(path)).pages)
    except Exception:
        return None


def _build(path: Path, key: str, ocr: bool = False, pages: tuple[int, int] | None = None) -> str:
    part: dict = {"file": "file"}
    if pages:
        part["pages"] = {"start": pages[0], "end": pages[1]}
    instructions: dict = {"parts": [part], "output": {"type": "markdown"}}
    if ocr:
        instructions["actions"] = [{"type": "ocr", "language": "english"}]
    resp = httpx.post(NUTRIENT_API_URL, headers={"Authorization": f"Bearer {key}"},
                      data={"instructions": json.dumps(instructions)},
                      files={"file": (path.name, path.read_bytes())}, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.text


def _build_in_ranges(path: Path, key: str, total: int, ocr: bool) -> str:
    chunks = []
    for start in range(0, total, PAGE_CHUNK):
        chunks.append(_build(path, key, ocr=ocr, pages=(start, min(start + PAGE_CHUNK, total) - 1)))
    return "\n\n".join(chunks)


def read_file(path: Path) -> dict:
    """Read one document. Returns {text, pages, chars, status (read / unreadable / failed), note}."""
    ext = path.suffix.lower()
    if ext not in READABLE_EXTENSIONS:
        return _result(status="unreadable", note=f"{ext.lstrip('.').upper() or 'this'} files can't be read")
    if ext in _LOCAL_TEXT:
        return _result(path.read_text(errors="replace"))
    key = _get_api_key()
    if not key:
        return _result(status="failed", note="NUTRIENT_API_KEY is not set")

    pages = _pdf_pages(path) if ext == ".pdf" else None
    note = ""
    try:
        try:
            text = _build(path, key)
        except (httpx.TimeoutException, httpx.HTTPStatusError) as e:
            timed_out = isinstance(e, httpx.TimeoutException) or e.response.status_code in (408, 504)
            if not (timed_out and pages and pages > PAGE_CHUNK):
                raise
            text = _build_in_ranges(path, key, pages, ocr=False)
            note = f"read in {PAGE_CHUNK}-page parts"
        if ext == ".pdf" and pages and len(text.strip()) < SCANNED_CHARS_PER_PAGE * pages:
            # A scan: no text layer, so the plain read came back (nearly) empty. Read it again with OCR.
            try:
                ocr_text = _build(path, key, ocr=True) if pages <= PAGE_CHUNK else _build_in_ranges(path, key, pages, ocr=True)
            except (httpx.TimeoutException, httpx.HTTPStatusError) as e:
                logger.warning("OCR failed for %s: %s", path.name, e)
                ocr_text = ""
            if len(ocr_text.strip()) > len(text.strip()):
                text, note = ocr_text, "scanned: read with OCR"
        return _result(text, pages, note=note)
    except httpx.HTTPStatusError as e:
        detail = ""
        try:
            detail = (e.response.json().get("details") or "")[:160]
        except Exception:
            pass
        logger.warning("Nutrient API %s for %s: %s", e.response.status_code, path.name, detail)
        return _result(pages=pages, status="failed", note=f"Nutrient API error {e.response.status_code}" + (f": {detail}" if detail else ""))
    except httpx.TimeoutException:
        return _result(pages=pages, status="failed", note="Nutrient API timed out")
    except Exception as e:
        logger.warning("Reading %s failed: %s", path.name, e)
        return _result(pages=pages, status="failed", note=f"{type(e).__name__}: {e}"[:200])


# ---------------------------------------------------------------------------
# Digest: what scoring and drafting send to the model
# ---------------------------------------------------------------------------

_MAIN = re.compile(r"solicitation|\brf[piqs]\b|\bitb\b|\bifb\b|scope|statement of work|\bsow\b|requirement|specification|"
                   r"technical|main document|questions", re.I)
_BOILERPLATE = re.compile(r"form|packet|w-?9|insurance|affidavit|certif|terms|conditions|sstc|price|pricing|cost|bond|"
                          r"registration|disclosure|reference check|signature page", re.I)


def compact(markdown: str) -> str:
    """Markdown from the API carries HTML tables; flatten them to pipe rows and drop blank runs (about a third smaller)."""
    t = re.sub(r"<br\s*/?>", "; ", markdown)
    t = re.sub(r"</t[dh]>\s*<t[dh][^>]*>", " | ", t)
    t = re.sub(r"</?(table|tr|td|th|thead|tbody)[^>]*>", "\n", t)
    t = re.sub(r"<[^>]+>", "", t)
    t = re.sub(r"[ \t]+\n", "\n", t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def _weight(name: str) -> int:
    if _MAIN.search(name):
        return 3
    if _BOILERPLATE.search(name):
        return 1
    return 2


def build_digest(docs: list[tuple[str, str]], budget: int) -> str:
    """One text from many documents within `budget` characters. Each document gets a share weighted by what it
    is (the solicitation and requirements most, forms and terms least); a short document's unused share goes to
    the long ones. Documents are written main-first, each under a '--- name ---' header."""
    items = [(name, compact(text)) for name, text in docs if text and text.strip()]
    if not items:
        return ""
    overhead = sum(len(n) + 10 for n, _ in items)
    remaining = max(budget - overhead, 0)
    order = sorted(range(len(items)), key=lambda i: len(items[i][1]) / _weight(items[i][0]))
    weights_left = sum(_weight(n) for n, _ in items)
    take: dict[int, int] = {}
    for i in order:
        name, text = items[i]
        share = remaining * _weight(name) // max(weights_left, 1)
        take[i] = min(len(text), share)
        remaining -= take[i]
        weights_left -= _weight(name)
    out = []
    for i in sorted(range(len(items)), key=lambda i: (-_weight(items[i][0]), items[i][0])):
        name, text = items[i]
        body = text[:take[i]]
        if take[i] < len(text):
            body += f"\n[... {len(text) - take[i]:,} more characters of this document not included ...]"
        out.append(f"--- {name} ---\n{body}")
    return "\n\n".join(out)
