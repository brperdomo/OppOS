"""Extract text from RFP attachments using Nutrient DWS API."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

NUTRIENT_API_URL = "https://api.nutrient.io/build"
MAX_TEXT_PER_FILE = 15_000
MAX_TOTAL_TEXT = 30_000


def _get_api_key() -> str:
    return os.environ.get("NUTRIENT_API_KEY", "")


def extract_text_from_pdf(file_path: Path) -> str:
    """Upload a PDF to Nutrient DWS and return extracted plain text."""
    api_key = _get_api_key()
    if not api_key:
        logger.warning("NUTRIENT_API_KEY not set — skipping text extraction")
        return ""

    instructions = json.dumps({
        "parts": [{"file": "file"}],
        "output": {
            "type": "json-content",
            "plainText": True,
            "language": "english",
        },
    })

    try:
        with open(file_path, "rb") as f:
            resp = httpx.post(
                NUTRIENT_API_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                data={"instructions": instructions},
                files={"file": (file_path.name, f, "application/pdf")},
                timeout=120.0,
            )
        resp.raise_for_status()
        data = resp.json()

        pages = data.get("pages", [])
        text_parts = []
        for page in pages:
            text = page.get("plainText", "")
            if text:
                text_parts.append(text)

        full_text = "\n\n".join(text_parts)

        remaining = resp.headers.get("x-pspdfkit-remaining-credits", "?")
        logger.info(
            "Extracted %d chars from %s (%d pages) — %s credits remaining",
            len(full_text), file_path.name, len(pages), remaining,
        )
        return full_text[:MAX_TEXT_PER_FILE]

    except httpx.HTTPStatusError as e:
        logger.warning("Nutrient API error for %s: %s %s", file_path.name, e.response.status_code, e.response.text[:200])
        return ""
    except Exception as e:
        logger.warning("Text extraction failed for %s: %s", file_path.name, e)
        return ""


def extract_text_from_attachments(file_paths: list[Path]) -> str:
    """Extract and concatenate text from multiple attachment files."""
    if not file_paths:
        return ""

    all_text = []
    total_len = 0

    pdf_paths = [p for p in file_paths if p.suffix.lower() == ".pdf"]
    if not pdf_paths:
        logger.info("No PDF attachments to extract text from")
        return ""

    for path in pdf_paths:
        if total_len >= MAX_TOTAL_TEXT:
            logger.info("Reached text limit (%d chars) — skipping remaining files", MAX_TOTAL_TEXT)
            break

        text = extract_text_from_pdf(path)
        if text:
            header = f"--- {path.name} ---"
            all_text.append(f"{header}\n{text}")
            total_len += len(text)

    return "\n\n".join(all_text)[:MAX_TOTAL_TEXT]
