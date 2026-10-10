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
    # Aggregators
    # Private sector
    "google_cse": "Google CSE — Private Sector",
    "target_accounts": "Target Account Monitor",
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
    from oppos.scoring.lobs import DEFAULT_LOB, LOBS, get_lob
    from oppos.scoring.schema import point_claim, point_evidence

    lob = get_lob(opp.get("lob") or s2.get("lob")) or LOBS[DEFAULT_LOB]

    def _point_line(point) -> str:
        claim, ev = point_claim(point), point_evidence(point)
        return f'{claim} — "{ev}"' if ev else claim

    children: list[dict] = []

    # ── Section 1: AI Assessment ──────────────────────────────
    summary = s2.get("summary", "")
    if summary:
        children.append(_heading(2, "AI Assessment"))
        children.append(_paragraph(f"Line of business: Nutrient {lob.label}"))
        children.append(_paragraph(summary))

        strengths = s2.get("strengths", [])
        if strengths:
            children.append(_heading(3, "Strengths"))
            for s in strengths[:8]:
                children.append(_bullet(_point_line(s)))

        risks = s2.get("risks", [])
        if risks:
            children.append(_heading(3, "Risks"))
            for r in risks[:5]:
                children.append(_bullet(_point_line(r)))

        gaps = s2.get("knowledge_gaps") or []
        if gaps:
            children.append(_heading(3, "Unknowns to verify"))
            for g in gaps[:8]:
                children.append(_bullet(str(g)))

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

    # ── Section 4: LOB capability reference ───────────────────
    children.append(_heading(2, f"Nutrient {lob.label} — Capability Reference"))
    children.append(_paragraph(
        "Use this section as context when drafting the RFP response. "
        f"It describes what Nutrient {lob.label} does, proven verticals, "
        "past wins, deployment options, and competitive positioning."
        + (" (Thin profile — verify capability claims before relying on them.)" if lob.depth != "full" else "")
    ))
    children.extend(_text_to_blocks(lob.profile, max_chars=40_000))
    children.append(_divider())

    # ── Section 5: Response Draft ─────────────────────────────
    children.append(_heading(2, "Response Draft"))
    children.append(_paragraph(
        "Use Notion AI to draft the RFP response. Select all content above "
        "as context, then ask Notion AI to generate a point-by-point response "
        f"mapping Nutrient {lob.label} capabilities to the RFP requirements."
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


def _block_sig(block: dict[str, Any]) -> tuple[str, str]:
    """(type, text) identity of a block — works for blocks we build and blocks Notion returns."""
    btype = str(block.get("type") or "")
    body = block.get(btype) or {}
    parts = []
    for rt in body.get("rich_text") or []:
        txt = rt.get("plain_text")
        if txt is None:
            txt = ((rt.get("text") or {}).get("content")) or ""
        parts.append(str(txt))
    return btype, "".join(parts)[:300]


def _page_blocks(client: Any, page_id: str) -> list[tuple[str, str]]:
    """Identity signatures of every top-level block on the page, in order (paginated)."""
    sigs: list[tuple[str, str]] = []
    cursor = None
    while True:
        res = client.blocks.children.list(block_id=page_id, start_cursor=cursor, page_size=100) if cursor else \
            client.blocks.children.list(block_id=page_id, page_size=100)
        sigs += [_block_sig(b) for b in (res.get("results") or [])]
        if not res.get("has_more"):
            return sigs
        cursor = res.get("next_cursor")


def _count_children(client: Any, page_id: str) -> int:
    return len(_page_blocks(client, page_id))


def _find_seq(hay: list[tuple[str, str]], want: list[tuple[str, str]], start: int = 0) -> int:
    n = len(want)
    for i in range(max(start, 0), len(hay) - n + 1):
        if hay[i:i + n] == want:
            return i
    return -1


def _batch_present(page: list[tuple[str, str]], base: int, batch: list[dict[str, Any]]) -> bool:
    """Is this batch's exact block sequence on the page after our section start? Identity, not count."""
    want = [_block_sig(b) for b in batch]
    return _find_seq(page, want, base) >= 0 if want else True


def _section_base(page: list[tuple[str, str]], children: list[dict[str, Any]]) -> int:
    """Index where THIS draft's section starts on the page, found by its header (divider + heading + the
    generated-at paragraph, unique per draft). If nothing of ours is there yet, the end of the page."""
    head = [_block_sig(b) for b in children[:3]]
    idx = _find_seq(page, head)
    return idx if idx >= 0 else len(page)


def append_response_draft(page_id: str, draft: dict[str, Any], start_batch: int = 0,
                          on_batch: Any = None, base_children: int | None = None) -> dict[str, Any]:
    """Append the AI draft to an existing Notion page in 100-block batches.

    Resumable: pass `start_batch` to continue after a partial failure (the caller persists
    progress via `on_batch(done, total, base_children)`), so a retry never re-appends earlier
    batches. Before writing, the page is read and this draft's section located by its unique header;
    the first batch of every run, and any batch whose append call fails, is reconciled against the
    page by block identity — so a lost response or a lost checkpoint never duplicates a batch, and
    unrelated blocks added by people cannot fake one. `base_children` is informational.
    Returns {"ok": bool, "done": batches_appended, "total": batches, "base": base_children, "error": str | None,
             "checkpoint_failed": True when a batch was appended but on_batch raised — resume from `done`,
             "ambiguous": True when the page could not be re-counted after a failed call — check the page}.
    """
    if not page_id:
        return {"ok": False, "done": 0, "total": 0, "error": "no page id"}
    client = _get_client()
    children: list[dict] = [
        _divider(),
        _heading(2, "Response Draft (AI — needs review)"),
        _paragraph(
            f"Generated {draft.get('generated_at', '')[:16].replace('T', ' ')} UTC by OppOS ({draft.get('model', '')}). "
            f"{draft['stats']['requirements']} requirements · {draft['stats']['high_confidence']} high confidence · "
            f"{draft['stats']['needs_human']} need a human. Compliance source "
            + ("approved v" + str(draft['compliance_source'].get('version')) if draft['compliance_source'].get('approved') else "NOT approved — all security items marked [SECURITY TO CONFIRM]")
            + ". Review every answer before it leaves the building."
        ),
    ]
    sub = draft.get("submission") or {}
    children.append(_paragraph(f"RFP type: {draft.get('rfp_type', '')} · Submission: {sub.get('method', 'unknown')} · Deadline: {sub.get('deadline', 'unknown')}"
                               + (f" · Questions due: {sub['questions_deadline']}" if sub.get("questions_deadline") else "")))
    for f in sub.get("format_requirements") or []:
        children.append(_bullet(f"Format: {f}"))
    if draft.get("evaluation_criteria"):
        children.append(_heading(3, "Evaluation criteria (extracted from the RFP)"))
        children += [_bullet(f"{c['criterion']}" + (f" — {c['weight']}" if c.get("weight") else "")) for c in draft["evaluation_criteria"]]
    if draft.get("required_forms"):
        children.append(_heading(3, "Required forms and attachments (extracted from the RFP)"))
        children += [_bullet(f) for f in draft["required_forms"]]
    if draft.get("executive_summary"):
        children.append(_heading(3, "Executive summary (draft)"))
        children.extend(_text_to_blocks(draft["executive_summary"], max_chars=8000))
    if draft.get("win_themes"):
        children.append(_heading(3, "Win themes"))
        children += [_bullet(t) for t in draft["win_themes"]]
    children.append(_heading(3, "Requirements and draft responses"))
    for r in draft.get("requirements") or []:
        label = (f"{r['id']}" + (f" · {r['section']}" if r.get("section") else "")
                 + (f" · {r['file']} p.{r['page']}" if r.get("page") and r.get("file") else f" · p.{r['page']}" if r.get("page") else "")
                 + f" · {r['category'].replace('_', ' ')}")
        children.append(_heading(3, _truncate(label, 100)))
        children.append(_paragraph(_truncate("Requirement: " + r.get("text", ""), 2000)))
        children.extend(_text_to_blocks(r.get("response", ""), max_chars=6000))
        meta = f"Confidence: {r['confidence']} · Basis: {', '.join(r['basis'])}"
        if r.get("sources"):
            meta += " · Sources: " + "; ".join(r["sources"][:4])
        if r.get("human_todo"):
            meta += f" · TODO: {r['human_todo']}"
        children.append(_paragraph(_truncate(meta, 2000)))
    for title, key in (("Open questions for Q&A", "open_questions"), ("Assumptions", "assumptions"), ("Do not claim", "do_not_claim")):
        items = draft.get(key) or []
        if items:
            children.append(_heading(3, title))
            children += [_bullet(x) for x in items]
    batches = [children[i:i + 100] for i in range(0, len(children), 100)]
    total = len(batches)
    done = start_batch

    # Where our section starts is re-derived from the page itself (the draft header is unique per generated_at),
    # so a lost pre-count, a lost response or blocks someone else added can neither hide nor fake our batches.
    try:
        base_children = _section_base(_page_blocks(client, page_id), children)
    except Exception as e:  # reading is best effort — without it we fall back to the checkpoint alone
        logger.warning("Notion: could not read page children (%s); proceeding without reconciliation", e)
        base_children = None

    def _landed(i: int) -> bool | None:
        """True/False if batch i's blocks are (not) on the page after our section start, by identity; None if
        the page cannot be read right now."""
        try:
            page = _page_blocks(client, page_id)
        except Exception:
            return None
        return _batch_present(page, _section_base(page, children), batches[i])

    def _checkpoint(d: int) -> dict[str, Any] | None:
        if not on_batch:
            return None
        try:
            on_batch(d, total, base_children)
            return None
        except Exception as e:
            logger.error("Notion draft append: batch %d/%d appended but progress could not be saved: %s", d, total, e)
            return {"ok": False, "done": d, "total": total, "base": base_children, "checkpoint_failed": True,
                    "error": f"batch {d} was appended but progress could not be saved ({str(e)[:160]})"}

    if done >= total:
        # Resuming after the final batch already landed but its checkpoint did not: persist completion now,
        # otherwise the UI keeps offering Append/Resume and a later click would duplicate the draft.
        failed = _checkpoint(total)
        return failed or {"ok": True, "done": total, "total": total, "base": base_children, "error": None}

    for i in range(start_batch, total):
        # The first batch of ANY run is checked before writing: a previous attempt may have landed it without
        # the response (or the checkpoint) surviving — including a run that is restarting from batch 0.
        if i == start_batch and _landed(i) is True:
            logger.info("Notion: batch %d/%d already on the page (reconciled) — skipping", i + 1, total)
        else:
            try:
                client.blocks.children.append(block_id=page_id, children=batches[i])
            except Exception as e:
                landed = _landed(i)
                if landed is True:
                    logger.warning("Notion append raised but batch %d/%d is on the page (%s) — continuing", i + 1, total, e)
                elif landed is None:
                    logger.error("Notion draft append failed at batch %d/%d and the page could not be re-counted: %s", i + 1, total, e)
                    return {"ok": False, "done": done, "total": total, "base": base_children, "ambiguous": True,
                            "error": f"{str(e)[:200]} — the page could not be re-counted, so batch {i + 1} may or may not be there"}
                else:
                    logger.error("Notion draft append failed at batch %d/%d: %s", i + 1, total, e)
                    return {"ok": False, "done": done, "total": total, "base": base_children, "error": str(e)[:300]}
        done = i + 1
        failed = _checkpoint(done)
        if failed:
            return failed
    logger.info("Appended response draft to Notion page %s (%d blocks, %d batches)", page_id, len(children), total)
    return {"ok": True, "done": done, "total": total, "base": base_children, "error": None}
