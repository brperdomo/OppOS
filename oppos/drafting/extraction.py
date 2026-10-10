"""Requirement extraction from RFP documents with Nutrient's Data Extraction API.

Dogfoods DWS Data Extraction (`POST /extraction/extract`): each RFP PDF is mapped to
a requirements schema and comes back with per-field citations — page number,
bounding box, parse confidence and Nutrient's grounding score — so the response
drafter works from page-cited requirements instead of a text blob.
"""

from __future__ import annotations

import json
import re
import logging
import os
from pathlib import Path
from typing import Any, Callable

import httpx

logger = logging.getLogger(__name__)

EXTRACT_URL = "https://api.nutrient.io/extraction/extract"
# "understand" = AI-augmented parsing (9 credits/page) + extract (6/page). "agentic" is 18 + 6.
EXTRACTION_MODE = (os.environ.get("EXTRACTION_MODE") or "understand").strip()
# Guard against burning credits on 400-page terms-and-conditions dumps.
EXTRACTION_MAX_PAGES = int((os.environ.get("EXTRACTION_MAX_PAGES") or "80").strip() or 80)
_CREDITS_PER_PAGE = {"text": 7, "structure": 7.5, "understand": 15, "agentic": 24}

CATEGORIES = "functional | technical | security_compliance | commercial | company | implementation | other"

REQUIREMENTS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "solicitation": {
            "type": "object",
            "description": "Facts about the solicitation itself, as printed in the document.",
            "properties": {
                "document_type": {"type": "string", "description": "What this document is: solicitation (the RFP/RFI/RFQ itself with scope and requirements), submission_instructions (portal or how-to-respond instructions), terms_and_conditions, form (a form to fill in), amendment, or other"},
                "title": {"type": "string"},
                "solicitation_number": {"type": "string"},
                "agency": {"type": "string"},
                "rfp_type": {"type": "string", "description": "RFI, RFP, RFQ, sources sought, ITB, or other"},
                "submission_method": {"type": "string", "description": "portal name, email address, mail, or in person"},
                "submission_deadline": {"type": "string", "description": "date and time responses are due, with time zone if printed"},
                "questions_deadline": {"type": "string", "description": "deadline for vendor questions, if any"},
                "amendment_number": {"type": "string", "description": "for an amendment/addendum: its number as printed (e.g. 2), else empty"},
                "amendment_date": {"type": "string", "description": "for an amendment/addendum: its issue date as printed, else empty"},
                "contact_name": {"type": "string"},
                "contact_email": {"type": "string"},
                "format_requirements": {"type": "string", "description": "page limits, fonts, required sections, copies, file formats"},
            },
        },
        "requirements": {
            "type": "array",
            "description": "Every requirement, question, or specification a vendor must respond to. One item per requirement, in document order.",
            "items": {
                "type": "object",
                "properties": {
                    "section": {"type": "string", "description": "section number or heading as printed, e.g. '3.4' or 'Scope of Work'"},
                    "text": {"type": "string", "description": "the requirement or question, verbatim or near-verbatim"},
                    "category": {"type": "string", "description": CATEGORIES},
                    "mandatory": {"type": "boolean", "description": "true when phrased as shall / must / required / mandatory / minimum"},
                },
                "required": ["text"],
            },
        },
        "evaluation_criteria": {
            "type": "array",
            "description": "How responses will be scored.",
            "items": {"type": "object", "properties": {"criterion": {"type": "string"}, "weight": {"type": "string", "description": "points or percentage as printed"}}},
        },
        "required_forms": {
            "type": "array",
            "description": "Forms, certifications, or attachments the vendor must include.",
            "items": {"type": "string"},
        },
    },
    "required": ["requirements"],
}


def api_key() -> str:
    return (os.environ.get("NUTRIENT_API_KEY") or "").strip()


def extraction_available() -> bool:
    return bool(api_key())


def page_count(path: Path) -> int | None:
    """Local page count from a parser that walks the full page tree, or None when it cannot be bounded —
    then the file is never sent for extraction. (No byte-scan fallback: object streams hide page
    dictionaries, so a regex count can be a partial, falsely small number.)"""
    try:
        from pypdf import PdfReader
        return len(PdfReader(str(path)).pages)
    except Exception:
        return None


def _leaf(meta: Any) -> dict[str, Any]:
    """Normalise one citation leaf from output.metadata.

    Handles both shapes seen from the API: the current one
    (`citation: {confidence: {groundedness}, regions: [{pageNumber, bbox}], status}`) and the
    earlier flat one (`confidence`, `confidenceComponents.groundingScore`, `pageNumber`, `bbox`).
    """
    if not isinstance(meta, dict):
        return {}
    cit = meta.get("citation") if isinstance(meta.get("citation"), dict) else {}
    regions = cit.get("regions") if isinstance(cit.get("regions"), list) else []
    region = regions[0] if regions and isinstance(regions[0], dict) else {}
    page = meta.get("pageNumber") or region.get("pageNumber")
    if page is None:
        idx = meta.get("pageIndex", region.get("pageIndex"))
        page = int(idx) + 1 if idx is not None else None
    comps = meta.get("confidenceComponents") or {}
    cconf = cit.get("confidence") if isinstance(cit.get("confidence"), dict) else {}
    grounding = comps.get("groundingScore")
    if grounding is None:
        grounding = cconf.get("groundedness", cconf.get("grounding"))
    if grounding is None and isinstance(meta.get("confidence"), (int, float)):
        grounding = meta["confidence"]
    return {
        "page": page,
        "bbox": meta.get("bbox") or region.get("bbox"),
        "confidence": meta.get("confidence") if isinstance(meta.get("confidence"), (int, float)) else grounding,
        "grounding": grounding,
        "cited": cit.get("status") == "cited" if cit else bool(page),
    }


def _extract_one(path: Path, mode: str) -> dict[str, Any]:
    instructions = {"mode": mode, "schema": REQUIREMENTS_SCHEMA, "citationsEnabled": True}
    with path.open("rb") as f:
        resp = httpx.post(
            EXTRACT_URL,
            headers={"Authorization": f"Bearer {api_key()}"},
            data={"instructions": json.dumps(instructions)},
            files={"file": (path.name, f, "application/pdf")},
            timeout=300.0,
        )
    resp.raise_for_status()
    body = resp.json()
    out = body.get("output") or {}
    usage = body.get("usage") or {}
    credits = (usage.get("data_extraction_credits") or {})
    return {
        "data": out.get("data") or {},
        "metadata": out.get("metadata") or {},
        "pages": len(out.get("pages") or []),
        "credits_cost": credits.get("cost"),
        "credits_remaining": credits.get("remainingCredits") or resp.headers.get("x-pspdfkit-remaining-credits"),
        "request_id": body.get("requestId"),
    }


_AMEND_NUM_RE = re.compile(r"(?:amendments?|amend|addend(?:um|a)?|modifications?|mod)[\s_#.-]*(?:no\.?\s*)?(\d{1,3})\b", re.I)


def _amend_rank(sol: dict[str, Any], filename: str) -> tuple[str, int]:
    """(iso date or '', number or -1) for an amendment — from the printed metadata, then the file name."""
    date = ""
    raw_date = str(sol.get("amendment_date") or "").strip()
    if raw_date:
        try:
            from dateutil import parser as _dp  # optional
            date = _dp.parse(raw_date, fuzzy=True).date().isoformat()
        except Exception:
            m = re.search(r"(20\d{2})-(\d{1,2})-(\d{1,2})", raw_date)
            date = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" if m else ""
    num = -1
    m = re.search(r"\d{1,3}", str(sol.get("amendment_number") or ""))
    if m:
        num = int(m.group(0))
    else:
        m = _AMEND_NUM_RE.search(filename)
        if m:
            num = int(m.group(1))
    return date, num


def _amend_newer(a: tuple[str, int] | None, b: tuple[str, int] | None) -> bool | None:
    """Is amendment `a` newer than `b`? None when the order cannot be established."""
    if not a or not b:
        return None
    if a[0] and b[0] and a[0] != b[0]:
        return a[0] > b[0]
    if a[1] >= 0 and b[1] >= 0 and a[1] != b[1]:
        return a[1] > b[1]
    return None


_REPLACE_RE = re.compile(r"\b(replace[sd]?|replacing|revise[sd]?|revision|delete[sd]?|remove[sd]?|supersede[sd]?|amended to read|is hereby|in lieu of|changed? to|strike)\b", re.I)
_SECTION_REF_RE = re.compile(r"(?:section|§|item|paragraph|clause|requirement|part)\s*([0-9]+(?:\.[0-9]+)*[a-z]?)", re.I)


def _mark_supersessions(result: dict[str, Any]) -> None:
    """An amendment item that targets an original item's section (same section id, or replacement language
    naming it) supersedes it: the original is marked, the amendment item records what it replaces, and the
    link is listed for a human to confirm. Nothing is deleted."""
    reqs = result.get("requirements") or []
    originals = [r for r in reqs if r.get("document_type") != "amendment"]
    by_section: dict[str, list[dict[str, Any]]] = {}
    for o in originals:
        if o.get("section"):
            by_section.setdefault(o["section"].strip().lower(), []).append(o)
    links: list[dict[str, Any]] = []
    for a in (r for r in reqs if r.get("document_type") == "amendment"):
        targets: list[tuple[dict[str, Any], str]] = []
        sec = (a.get("section") or "").strip().lower()
        if sec and sec in by_section:
            targets += [(o, f"same section {a['section']}") for o in by_section[sec]]
        if not targets and _REPLACE_RE.search(a.get("text") or ""):
            for ref in _SECTION_REF_RE.findall(a.get("text") or ""):
                for o in by_section.get(ref.lower(), []):
                    targets.append((o, f"amendment text replaces section {ref}"))
        for o, basis in targets:
            if o.get("superseded_by"):
                continue
            o["superseded_by"] = a["id"]
            a.setdefault("supersedes", []).append(o["id"])
            links.append({"old": o["id"], "new": a["id"], "new_file": a.get("file", ""), "basis": basis})
    result["supersessions"] = links


def extract_rfp_requirements(
    file_paths: list[Path],
    mode: str | None = None,
    on_progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Run Data Extraction over the RFP PDFs and merge into one page-cited requirement list.

    Returns {"requirements": [...], "solicitation": {...}, "evaluation_criteria": [...],
             "required_forms": [...], "files": [...], "pages": n, "credits_cost": n,
             "credits_remaining": ..., "skipped": [...], "errors": [...]}
    """
    mode = mode or EXTRACTION_MODE
    result: dict[str, Any] = {"mode": mode, "requirements": [], "solicitation": {}, "solicitation_sources": {},
                              "solicitation_conflicts": [], "evaluation_criteria": [],
                              "required_forms": [], "files": [], "pages": 0, "credits_cost": 0,
                              "credits_remaining": None, "skipped": [], "errors": []}
    if not extraction_available():
        result["errors"].append("NUTRIENT_API_KEY not set")
        return result

    pdfs = [p for p in file_paths if p.suffix.lower() == ".pdf" and p.is_file()]
    budget = EXTRACTION_MAX_PAGES
    seq = 0
    for path in pdfs:
        if budget <= 0:
            result["skipped"].append(f"{path.name} (page budget of {EXTRACTION_MAX_PAGES} exhausted)")
            continue
        n = page_count(path)
        if n is not None and n > budget:
            result["skipped"].append(f"{path.name} ({n} pages — over the remaining {budget}-page budget)")
            continue
        if n is None:
            # The API charges per page and the charge cannot be undone — a file whose size we cannot bound
            # locally is never uploaded, first in line or not.
            result["skipped"].append(f"{path.name} (page count unknown — cannot bound credit spend; "
                                     f"convert or unlock the PDF and retry)")
            continue
        if on_progress:
            on_progress(f"Extracting requirements from {path.name}" + (f" ({n} pages)" if n else ""))
        try:
            one = _extract_one(path, mode)
        except httpx.HTTPStatusError as e:
            result["errors"].append(f"{path.name}: HTTP {e.response.status_code} {e.response.text[:160]}")
            continue
        except Exception as e:  # network, JSON, etc.
            result["errors"].append(f"{path.name}: {e}")
            continue

        data, meta = one["data"], one["metadata"]
        result["files"].append({"file": path.name, "pages": one["pages"], "credits": one["credits_cost"], "request_id": one["request_id"]})
        effective_pages = one["pages"] or (n or 0)
        result["pages"] += effective_pages
        budget -= effective_pages  # the API's count applies even when pypdf could not read the file
        if one["credits_cost"]:
            result["credits_cost"] += int(one["credits_cost"])
        if one["credits_remaining"] is not None:
            result["credits_remaining"] = one["credits_remaining"]

        sol = data.get("solicitation") or {}
        doc_type = str(sol.get("document_type") or "other").strip().lower().replace(" ", "_")
        result["files"][-1]["document_type"] = doc_type
        rank = _amend_rank(sol, path.name) if doc_type == "amendment" else None
        for k, v in sol.items():
            if k in ("document_type", "amendment_number", "amendment_date") or not v:
                continue
            have = result["solicitation"].get(k)
            src = result.setdefault("solicitation_sources", {})
            if not have:
                result["solicitation"][k] = v
                src[k] = {"file": path.name, "document_type": doc_type, "rank": rank}
            elif str(have).strip() == str(v).strip():
                # Same value restated by a newer amendment: provenance moves to it, so an older amendment seen
                # later (lexical file order) cannot override with an obsolete value.
                prev = src.get(k) or {}
                if doc_type == "amendment" and (prev.get("document_type") != "amendment" or _amend_newer(rank, prev.get("rank")) is True):
                    src[k] = {"file": path.name, "document_type": doc_type, "rank": rank}
            else:
                # An amendment overrides the original; between amendments the newer one (by printed date, then
                # number, then a number in the file name) wins. When the order cannot be established nothing is
                # guessed: the first value stands and the disagreement is surfaced for a human.
                prev = src.get(k) or {}
                conflicts = result.setdefault("solicitation_conflicts", [])
                if doc_type == "amendment" and prev.get("document_type") != "amendment":
                    conflicts.append({"field": k, "kept": v, "kept_file": path.name, "other": have, "other_file": prev.get("file", "?"), "reason": "amendment overrides"})
                    result["solicitation"][k] = v
                    src[k] = {"file": path.name, "document_type": doc_type, "rank": rank}
                elif doc_type == "amendment":
                    newer = _amend_newer(rank, prev.get("rank"))
                    if newer is True:
                        conflicts.append({"field": k, "kept": v, "kept_file": path.name, "other": have, "other_file": prev.get("file", "?"), "reason": "later amendment overrides"})
                        result["solicitation"][k] = v
                        src[k] = {"file": path.name, "document_type": doc_type, "rank": rank}
                    elif newer is False:
                        conflicts.append({"field": k, "kept": have, "kept_file": prev.get("file", "?"), "other": v, "other_file": path.name, "reason": "earlier amendment superseded"})
                    else:
                        conflicts.append({"field": k, "kept": have, "kept_file": prev.get("file", "?"), "other": v, "other_file": path.name, "reason": "amendment order unknown — confirm which is current"})
                else:
                    conflicts.append({"field": k, "kept": have, "kept_file": prev.get("file", "?"), "other": v, "other_file": path.name, "reason": "first document kept"})

        req_meta = meta.get("requirements") if isinstance(meta.get("requirements"), list) else []
        for i, item in enumerate(data.get("requirements") or []):
            if not isinstance(item, dict) or not str(item.get("text") or "").strip():
                continue
            seq += 1
            m = req_meta[i] if i < len(req_meta) and isinstance(req_meta[i], dict) else {}
            cite = _leaf(m.get("text")) or _leaf(m)
            cat = str(item.get("category") or "other").strip().lower().replace(" ", "_")
            result["requirements"].append({
                "id": f"E{seq}",
                "file": path.name,
                "document_type": doc_type,
                "section": str(item.get("section") or "").strip()[:80],
                "text": str(item.get("text")).strip()[:1500],
                "category": cat if cat in CATEGORIES.replace(" ", "").split("|") else "other",
                "mandatory": bool(item.get("mandatory")),
                "page": cite.get("page"),
                "grounding": cite.get("grounding"),
                "confidence": cite.get("confidence"),
                "cited": cite.get("cited", False),
            })
        for c in data.get("evaluation_criteria") or []:
            if isinstance(c, dict) and c.get("criterion"):
                result["evaluation_criteria"].append({"criterion": str(c["criterion"])[:300], "weight": str(c.get("weight") or "")[:40]})
        for frm in data.get("required_forms") or []:
            if frm and str(frm) not in result["required_forms"]:
                result["required_forms"].append(str(frm)[:200])

    _mark_supersessions(result)
    result["stats"] = {
        "requirements": len(result["requirements"]),
        "by_document_type": {t: sum(1 for r in result["requirements"] if r.get("document_type") == t)
                             for t in sorted({r.get("document_type") or "other" for r in result["requirements"]})},
        "mandatory": sum(1 for r in result["requirements"] if r["mandatory"]),
        "low_grounding": sum(1 for r in result["requirements"]
                             if isinstance(r.get("grounding"), (int, float)) and r["grounding"] < 0.6),
        "estimated_credits_per_page": _CREDITS_PER_PAGE.get(mode),
    }
    return result


def format_for_prompt(extracted: dict[str, Any]) -> str:
    """Render the extraction for the drafter prompt — compact, page-cited, numbered."""
    if not extracted or not extracted.get("requirements"):
        return ""
    lines = ["=== PRE-EXTRACTED REQUIREMENTS (Nutrient Data Extraction API — page-cited; reuse these ids) ==="]
    sol = extracted.get("solicitation") or {}
    if sol:
        lines.append("Solicitation facts: " + "; ".join(f"{k}: {v}" for k, v in sol.items() if v))
    files = extracted.get("files") or []
    if files:
        lines.append("Documents: " + "; ".join(f"{f['file']} = {f.get('document_type', 'other')}" for f in files))
    lines.append("Items from submission_instructions / terms_and_conditions / form documents are process or contractual "
                 "obligations: acknowledge them briefly (how we will comply) rather than selling capabilities; items from the "
                 "solicitation document are the requirements to answer in full.")
    if extracted.get("supersessions"):
        lines.append("Amendments replace earlier items: for an item tagged 'SUPERSEDED by Ex' do not draft an answer — its "
                     "response is filled in automatically; answer the replacing amendment item in full.")
    for r in extracted["requirements"]:
        tags = [f"file:{r['file']}" if r.get("file") else "", r.get("document_type", "") if r.get("document_type") not in (None, "", "solicitation") else "",
                f"p.{r['page']}" if r.get("page") else "",
                f"§{r['section']}" if r.get("section") else "",
                r.get("category", ""), "mandatory" if r.get("mandatory") else "",
                f"grounding {r['grounding']:.2f}" if isinstance(r.get("grounding"), (int, float)) else "",
                f"SUPERSEDED by {r['superseded_by']}" if r.get("superseded_by") else "",
                f"supersedes {', '.join(r['supersedes'])}" if r.get("supersedes") else ""]
        lines.append(f"[{r['id']}] ({', '.join(t for t in tags if t)}) {r['text']}")
    if extracted.get("evaluation_criteria"):
        lines.append("Evaluation criteria: " + "; ".join(f"{c['criterion']} ({c['weight']})" if c.get("weight") else c["criterion"]
                                                        for c in extracted["evaluation_criteria"]))
    if extracted.get("required_forms"):
        lines.append("Required forms/attachments: " + "; ".join(extracted["required_forms"]))
    return "\n".join(lines)
