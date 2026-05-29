"""Sync scored opportunities to a Notion database.

Maps OppOS opportunity data to the "OppOS — RFP Pipeline" Notion database
with properties: RFP Title, Fit Score, Action, Agency, Deadline, Source,
Pipeline Status, State, Pattern, Industry, Similar Win, Solicitation #,
URL, Contact Name, Contact Email, Deployment, Notes, Source ID.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from notion_client import Client

from oppos.config import NOTION_DATABASE_ID, NOTION_DATASOURCE_ID, NOTION_TOKEN, SOURCE_STATE_MAP

logger = logging.getLogger(__name__)

_client: Client | None = None


def _get_client() -> Client:
    global _client
    if _client is None:
        if not NOTION_TOKEN:
            raise RuntimeError("NOTION_TOKEN not set")
        _client = Client(auth=NOTION_TOKEN)
    return _client


def _truncate(text: str, max_len: int = 2000) -> str:
    return text[:max_len] if text else ""


# --- Display-name maps --------------------------------------------------

# Pipeline status keys → Notion select labels
_PIPELINE_LABELS: dict[str, str] = {
    "new": "New",
    "qualified": "Qualified",
    "expiring_soon": "Expiring Soon",
    "in_progress": "In Progress",
    "submitted": "Submitted",
    "won": "Won",
    "lost": "Lost",
    "skipped": "Skipped",
    "expired": "Expired",
}

# Source keys → friendly platform names for the Source select
_SOURCE_DISPLAY: dict[str, str] = {
    "sam_gov": "SAM.gov",
    "manual": "Manual Upload",
    # Periscope/SOVRA
    "nevada_epro": "Periscope — NevadaEPro",
    "massachusetts_commbuys": "Periscope — COMMBUYS",
    "new_jersey_njstart": "Periscope — NJSTART",
    "illinois_bidbuy": "Periscope — BidBuy",
    "oregon_oregonbuys": "Periscope — OregonBuys",
    "arkansas_arbuy": "Periscope — ArBuy",
    "arizona_app": "Periscope — APP",
    "california_caleprocure": "Periscope — CaleProcure",
    # JAGGAER/SciQuest
    "iowa_impacs": "JAGGAER — ImPACS",
    "montana_emacs": "JAGGAER — eMACS",
    "new_mexico_epronm": "JAGGAER — ePro NM",
    "pennsylvania_emarketplace": "JAGGAER — eMarketplace",
    "utah_u3p": "JAGGAER — U3P",
    # CGI Advantage
    "west_virginia_wvoasis": "CGI — wvOASIS",
    "kentucky_emars": "CGI — eMARS",
    "colorado_vss": "CGI — VSS",
    "michigan_sigma": "CGI — SIGMA",
    "alaska_iris": "CGI — IRIS",
    "maine_vss": "CGI — Maine VSS",
    # PeopleSoft/Oracle
    "tennessee_edison": "PeopleSoft — Edison",
    "georgia_tgm": "PeopleSoft — TGM",
    "indiana_idoa": "PeopleSoft — IDOA",
    "kansas_esupplier": "PeopleSoft — eSupplier",
    "minnesota_swift": "PeopleSoft — SWIFT",
    "oklahoma_omes": "PeopleSoft — OMES",
    "wisconsin_esupplier": "PeopleSoft — eSupplier WI",
    "new_york_sfs": "PeopleSoft — SFS",
    # Ivalua
    "maryland_emma": "Ivalua — eMMA",
    "virginia_eva": "Ivalua — eVA",
    "north_dakota_ndbuys": "Ivalua — NDBuys",
    "vermont_vtbuys": "Ivalua — VTBuys",
    "alabama_alabamabuys": "Ivalua — AlabamaBuys",
    "ohio_ohiobuys": "Ivalua — OhioBuys",
    # SAP/Ariba
    "florida_mfmp": "SAP — MFMP",
    "north_carolina_evp": "SAP — EVP",
    "mississippi_magic": "SAP — MAGIC",
    "south_carolina_scpro": "SAP — SCPRO",
    "louisiana_lapac": "SAP — LaPAC",
    # PROACTIS/WebProcure
    "connecticut_ctsource": "PROACTIS — CTsource",
    "missouri_missouribuys": "PROACTIS — MissouriBUYS",
    "rhode_island_osp": "PROACTIS — Ocean State",
}


def _upload_file_to_notion(client: Client, page_id: str, filepath: Path) -> bool:
    """Upload a file to a Notion page using the file uploads API."""
    try:
        upload = client.file_uploads.create(
            parent={"type": "page", "page_id": page_id},
            name=filepath.name,
        )
        upload_id = upload["id"]

        with open(filepath, "rb") as f:
            client.file_uploads.send(
                upload_id,
                file=f,
                filename=filepath.name,
            )

        client.file_uploads.complete(upload_id)

        client.blocks.children.append(
            block_id=page_id,
            children=[{
                "object": "block",
                "type": "file",
                "file": {
                    "type": "file_upload",
                    "file_upload": {"id": upload_id},
                },
            }],
        )
        logger.info("Uploaded attachment: %s", filepath.name)
        return True
    except Exception as e:
        logger.warning("Failed to upload %s to Notion: %s", filepath.name, e)
        return False


def _heading(level: int, text: str) -> dict:
    """Create a Notion heading block (level 1, 2, or 3)."""
    key = f"heading_{level}"
    return {"object": "block", "type": key, key: {"rich_text": [{"text": {"content": text}}]}}


def _paragraph(text: str) -> dict:
    """Create a Notion paragraph block (max 2000 chars per Notion limit)."""
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": [{"text": {"content": _truncate(text, 2000)}}]},
    }


def _bullet(text: str) -> dict:
    """Create a bulleted list item block."""
    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {"rich_text": [{"text": {"content": _truncate(text, 2000)}}]},
    }


def _divider() -> dict:
    return {"object": "block", "type": "divider", "divider": {}}


def _text_to_blocks(text: str, max_chars: int = 80_000) -> list[dict]:
    """Split long text into multiple paragraph blocks (2000 chars each, Notion limit)."""
    text = text[:max_chars].strip()
    if not text:
        return []
    blocks = []
    # Split on paragraph boundaries first, then chunk if still too long
    paragraphs = text.split("\n\n")
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        while len(para) > 2000:
            # Find a line break or space near the limit
            cut = para.rfind("\n", 0, 2000)
            if cut < 500:
                cut = para.rfind(" ", 0, 2000)
            if cut < 500:
                cut = 2000
            blocks.append(_paragraph(para[:cut]))
            para = para[cut:].strip()
        if para:
            blocks.append(_paragraph(para))
    return blocks


def _build_page_body(
    opp: dict[str, Any],
    s2: dict[str, Any],
    attachment_paths: list[Path] | None = None,
) -> list[dict]:
    """Build the full Notion page body with all context Notion AI needs.

    Sections:
    1. AI Assessment — our scoring summary + strengths/risks
    2. RFP Requirements — full description from the listing
    3. Scanned Documents — OCR-extracted text from all attachments
    4. Nutrient Workflow Capabilities — what we sell (for Notion AI context)
    5. Response Draft — empty section for Notion AI to fill
    """
    from oppos.scoring.capability_profile import CAPABILITY_PROFILE

    children: list[dict] = []

    # ── Section 1: AI Assessment ──────────────────────────────
    summary = s2.get("summary", "")
    if summary:
        children.append(_heading(2, "AI Assessment"))
        children.append(_paragraph(summary))

        strengths = s2.get("strengths", [])
        if strengths:
            children.append(_heading(3, "Strengths"))
            for s in strengths[:8]:
                children.append(_bullet(s))

        risks = s2.get("risks", [])
        if risks:
            children.append(_heading(3, "Risks"))
            for r in risks[:5]:
                children.append(_bullet(r))

        dep = s2.get("deployment_recommendation", "")
        comp = s2.get("competitive_notes", "")
        if dep or comp:
            children.append(_heading(3, "Notes"))
            if dep:
                children.append(_paragraph(f"Deployment recommendation: {dep}"))
            if comp:
                children.append(_paragraph(f"Competitive landscape: {_truncate(comp, 1500)}"))

        children.append(_divider())

    # ── Section 2: RFP Requirements ───────────────────────────
    description = opp.get("description", "")
    if description:
        children.append(_heading(2, "RFP Requirements"))
        children.extend(_text_to_blocks(description, max_chars=40_000))
        children.append(_divider())

    # ── Section 3: Scanned Document Content ───────────────────
    attachment_text = opp.get("attachment_text", "") or ""
    if attachment_text.strip():
        children.append(_heading(2, "Scanned Document Content"))
        children.append(_paragraph(
            "The following text was extracted via OCR from the RFP attachments. "
            "Use this as the primary source for understanding detailed requirements."
        ))
        children.extend(_text_to_blocks(attachment_text, max_chars=80_000))
        children.append(_divider())

    # ── Section 4: Nutrient Workflow Capabilities ─────────────
    children.append(_heading(2, "Nutrient Workflow — Capability Reference"))
    children.append(_paragraph(
        "Use this section as context when drafting the RFP response. "
        "It describes what Nutrient Workflow does, proven verticals, "
        "past wins, deployment options, and competitive positioning."
    ))
    children.extend(_text_to_blocks(CAPABILITY_PROFILE, max_chars=40_000))
    children.append(_divider())

    # ── Section 5: Response Draft ─────────────────────────────
    children.append(_heading(2, "Response Draft"))
    children.append(_paragraph(
        "Use Notion AI to draft the RFP response. Select all content above "
        "as context, then ask Notion AI to generate a point-by-point response "
        "mapping Nutrient Workflow capabilities to the RFP requirements."
    ))

    # ── Attachments placeholder ───────────────────────────────
    if attachment_paths:
        children.append(_divider())
        children.append(_heading(3, "Attachments"))

    return children


def push_opportunity(opp: dict[str, Any], attachment_paths: list[Path] | None = None) -> str | None:
    """Create or update a page in the Notion RFP database. Returns the page ID."""
    if not NOTION_DATABASE_ID:
        logger.warning("NOTION_DATABASE_ID not set — skipping Notion sync")
        return None

    client = _get_client()
    s2 = opp.get("stage2") or {}
    if isinstance(s2, str):
        try:
            s2 = json.loads(s2)
        except json.JSONDecodeError:
            s2 = {}

    score = opp.get("fit_score", 0)
    action = s2.get("recommended_action", opp.get("recommended_action", "pending"))

    action_color_map = {
        "pursue": "green",
        "investigate": "yellow",
        "monitor": "orange",
        "skip": "red",
    }

    # Resolve display names for select fields
    source_key = opp.get("source", "sam_gov")
    source_label = _SOURCE_DISPLAY.get(source_key, source_key)
    state_label = SOURCE_STATE_MAP.get(source_key, "")
    pipeline_status = opp.get("pipeline_status", "new")
    pipeline_label = _PIPELINE_LABELS.get(pipeline_status, pipeline_status.replace("_", " ").title())

    # Contact info
    poc = opp.get("point_of_contact") or {}
    if isinstance(poc, str):
        try:
            poc = json.loads(poc)
        except (json.JSONDecodeError, TypeError):
            poc = {}
    contact_name = poc.get("name", "") if isinstance(poc, dict) else ""
    contact_email = poc.get("email", "") if isinstance(poc, dict) else ""

    # Deployment recommendation
    deployment = s2.get("deployment_recommendation", "")

    properties: dict[str, Any] = {
        "RFP Title": {"title": [{"text": {"content": _truncate(opp.get("title", "Untitled"), 200)}}]},
        "Fit Score": {"number": score},
        "Action": {"select": {"name": action.capitalize(), "color": action_color_map.get(action, "default")}},
        "Agency": {"rich_text": [{"text": {"content": _truncate(opp.get("agency", ""), 200)}}]},
        "Deadline": {},
        "Source": {"select": {"name": source_label}},
        "Pipeline Status": {"select": {"name": pipeline_label}},
        "State": {"rich_text": [{"text": {"content": state_label}}]} if state_label else {"rich_text": []},
        "Pattern": {"select": {"name": s2.get("pattern_match", "other")}},
        "Industry": {"rich_text": [{"text": {"content": _truncate(s2.get("industry", ""), 100)}}]},
        "Similar Win": {"rich_text": [{"text": {"content": _truncate(s2.get("similar_win") or "", 200)}}]},
        "Solicitation #": {"rich_text": [{"text": {"content": _truncate(opp.get("solicitation_number", ""), 100)}}]},
        "URL": {"url": opp.get("url") or None},
        "Contact Name": {"rich_text": [{"text": {"content": _truncate(contact_name, 200)}}]},
        "Contact Email": {"email": contact_email or None},
        "Deployment": {"select": {"name": deployment}} if deployment else {"select": None},
        "Notes": {"rich_text": [{"text": {"content": _truncate(opp.get("pipeline_notes", ""), 2000)}}]},
        "Source ID": {"rich_text": [{"text": {"content": _truncate(opp.get("source_id", ""), 200)}}]},
    }

    deadline = opp.get("response_deadline")
    if deadline:
        properties["Deadline"] = {"date": {"start": deadline[:10]}}
    else:
        del properties["Deadline"]

    children = _build_page_body(opp, s2, attachment_paths)

    # Check for existing page by Source ID to avoid duplicates
    source_id = opp.get("source_id", "")
    existing_page_id = _find_page_by_source_id(client, source_id) if source_id else None

    if existing_page_id:
        # Update the existing page properties (don't re-create body content)
        try:
            client.pages.update(
                page_id=existing_page_id,
                properties=properties,
            )
            logger.info("Notion page updated for '%s': %s", opp.get("title", "?"), existing_page_id)
            return existing_page_id
        except Exception as e:
            logger.error("Notion update failed for '%s': %s — creating new page", opp.get("title", "?"), e)

    # Create a new page (Notion allows max 100 blocks per call)
    try:
        page = client.pages.create(
            parent={"database_id": NOTION_DATABASE_ID},
            properties=properties,
            children=children[:100],
        )
        page_id = page["id"]

        # Append overflow blocks in batches of 100
        for i in range(100, len(children), 100):
            try:
                client.blocks.children.append(
                    block_id=page_id,
                    children=children[i : i + 100],
                )
            except Exception as e:
                logger.warning("Overflow append failed at block %d: %s", i, e)
                break

        logger.info(
            "Notion page created for '%s': %s (%d blocks)",
            opp.get("title", "?"), page_id, len(children),
        )

        if attachment_paths:
            for filepath in attachment_paths:
                _upload_file_to_notion(client, page_id, filepath)

        return page_id
    except Exception as e:
        logger.error("Notion sync failed for '%s': %s", opp.get("title", "?"), e)
        return None


def _find_page_by_source_id(client: Client, source_id: str) -> str | None:
    """Look up an existing Notion page by Source ID to avoid duplicates."""
    if not source_id or not NOTION_DATASOURCE_ID:
        return None
    try:
        # notion-client v3: databases.query → data_sources.query
        result = client.data_sources.query(
            data_source_id=NOTION_DATASOURCE_ID,
            filter={
                "property": "Source ID",
                "rich_text": {"equals": source_id},
            },
            page_size=1,
        )
        pages = result.get("results", [])
        if pages:
            return pages[0]["id"]
    except Exception as e:
        logger.debug("Source ID lookup failed for '%s': %s", source_id, e)
    return None


def update_pipeline_status(source_id: str, status: str, notes: str = "") -> bool:
    """Update just the Pipeline Status (and Notes) on an existing Notion page.

    Useful when the dashboard changes status without re-pushing the full opportunity.
    """
    if not NOTION_DATABASE_ID:
        return False

    client = _get_client()
    page_id = _find_page_by_source_id(client, source_id)
    if not page_id:
        logger.debug("No Notion page for source_id '%s' — skipping status update", source_id)
        return False

    label = _PIPELINE_LABELS.get(status, status.replace("_", " ").title())
    props: dict[str, Any] = {
        "Pipeline Status": {"select": {"name": label}},
    }
    if notes:
        props["Notes"] = {"rich_text": [{"text": {"content": _truncate(notes, 2000)}}]}

    try:
        client.pages.update(page_id=page_id, properties=props)
        logger.info("Notion status → '%s' for %s", label, source_id)
        return True
    except Exception as e:
        logger.error("Notion status update failed for '%s': %s", source_id, e)
        return False
