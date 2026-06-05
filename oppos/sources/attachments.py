"""Download RFP attachments from various sources."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import httpx

from oppos.config import DB_PATH

logger = logging.getLogger(__name__)

ATTACHMENTS_DIR = DB_PATH.parent / "attachments"


def _sanitize_filename(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    return name[:200].strip('. ')


def _ensure_dir(source_id: str) -> Path:
    opp_dir = ATTACHMENTS_DIR / _sanitize_filename(source_id)
    opp_dir.mkdir(parents=True, exist_ok=True)
    return opp_dir


def download_sam_gov(opp: dict[str, Any]) -> list[Path]:
    """Download attachments from SAM.gov resource links."""
    links = opp.get("resource_links") or []
    if not links:
        return []

    source_id = opp.get("source_id", "unknown")
    opp_dir = _ensure_dir(source_id)
    downloaded: list[Path] = []

    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        for i, url in enumerate(links):
            try:
                resp = client.get(url)
                resp.raise_for_status()

                disposition = resp.headers.get("content-disposition", "")
                fname_match = re.search(r'filename="?([^";\n]+)"?', disposition)
                if fname_match:
                    fname = _sanitize_filename(fname_match.group(1))
                else:
                    ext = ".pdf"
                    ct = resp.headers.get("content-type", "")
                    if "word" in ct or "docx" in ct:
                        ext = ".docx"
                    elif "excel" in ct or "xlsx" in ct:
                        ext = ".xlsx"
                    fname = f"attachment_{i+1}{ext}"

                filepath = opp_dir / fname
                filepath.write_bytes(resp.content)
                downloaded.append(filepath)
                logger.info("Downloaded: %s (%d bytes)", filepath.name, len(resp.content))
            except httpx.HTTPError as e:
                logger.warning("Failed to download %s: %s", url, e)

    return downloaded


def download_periscope(
    opp: dict[str, Any],
    base_url: str,
) -> list[Path]:
    """Download attachments from a Periscope/SOVRA bid detail page."""
    source_id = opp.get("source_id", "unknown")
    doc_id = opp.get("solicitation_number", "")
    if not doc_id:
        return []

    opp_dir = _ensure_dir(source_id)
    downloaded: list[Path] = []
    detail_url = f"{base_url}/bso/external/bidDetail.sda"

    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        resp = client.get(
            detail_url,
            params={"docId": doc_id, "external": "true", "parentUrl": "close"},
        )
        if resp.status_code != 200:
            return []

        csrf_match = re.search(r'name="_csrf"\s+value="([^"]+)"', resp.text)
        csrf = csrf_match.group(1) if csrf_match else ""

        file_entries = re.findall(
            r"downloadFile\('(\d+)'\);\"\s*class=\"[^\"]*\">([^<]+)",
            resp.text,
        )
        if not file_entries:
            file_ids = re.findall(r"downloadFile\('(\d+)'\)", resp.text)
            file_entries = [(fid, f"attachment_{fid}") for fid in file_ids]

        for file_id, file_name in file_entries:
            try:
                dl_resp = client.post(
                    detail_url,
                    data={
                        "_csrf": csrf,
                        "mode": "download",
                        "bidId": doc_id,
                        "docId": doc_id,
                        "currentPage": "1",
                        "querySql": "",
                        "downloadFileNbr": file_id,
                        "itemNbr": "0",
                        "parentUrl": "close",
                        "fromQuote": "",
                        "destination": "",
                    },
                )
                dl_resp.raise_for_status()

                disposition = dl_resp.headers.get("content-disposition", "")
                fname_match = re.search(r'filename="?([^";\n]+)"?', disposition)
                if fname_match:
                    fname = _sanitize_filename(fname_match.group(1))
                else:
                    fname = _sanitize_filename(file_name.strip())
                    if not Path(fname).suffix:
                        fname += ".pdf"

                filepath = opp_dir / fname
                filepath.write_bytes(dl_resp.content)
                downloaded.append(filepath)
                logger.info("Downloaded: %s (%d bytes)", filepath.name, len(dl_resp.content))
            except httpx.HTTPError as e:
                logger.warning("Failed to download file %s from %s: %s", file_id, doc_id, e)

    return downloaded


def download_attachments(opp: dict[str, Any]) -> list[Path]:
    """Download attachments based on the opportunity source."""
    source = opp.get("source", "")

    if source == "sam_gov":
        return download_sam_gov(opp)

    if source in ("manual", "google_cse", "target_accounts", "starbridge"):
        # These sources download files inline or have no server-side attachments
        opp_dir = ATTACHMENTS_DIR / _sanitize_filename(opp.get("source_id", ""))
        if opp_dir.is_dir():
            return sorted(f for f in opp_dir.iterdir() if f.is_file())
        return []

    from oppos.sources.platforms.periscope import SITES
    if source in SITES:
        return download_periscope(opp, SITES[source].base_url)

    return []
