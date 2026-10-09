"""Requirement extraction from RFP documents with Nutrient's Data Extraction API.

Dogfoods DWS Data Extraction (`POST /extraction/extract`): each RFP PDF is mapped to
a requirements schema and comes back with per-field citations — page number,
bounding box, parse confidence and Nutrient's grounding score — so the response
drafter works from page-cited requirements instead of a text blob.
"""

from __future__ import annotations

import json
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
                "title": {"type": "string"},
                "solicitation_number": {"type": "string"},
                "agency": {"type": "string"},
                "rfp_type": {"type": "string", "description": "RFI, RFP, RFQ, sources sought, ITB, or other"},
                "submission_method": {"type": "string", "description": "portal name, email address, mail, or in person"},
                "submission_deadline": {"type": "string", "description": "date and time responses are due, with time zone if printed"},
                "questions_deadline": {"type": "string", "description": "deadline for vendor questions, if any"},
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
    try:
        from pypdf import PdfReader
        return len(PdfReader(str(path)).pages)
    except Exception:
        return None


def _leaf(meta: Any) -> dict[str, Any]:
    """Normalise one citation leaf from output.metadata."""
    if not isinstance(meta, dict):
        return {}
    comps = meta.get("confidenceComponents") or {}
    return {
        "page": meta.get("pageNumber") or (int(meta["pageIndex"]) + 1 if meta.get("pageIndex") is not None else None),
        "bbox": meta.get("bbox"),
        "confidence": meta.get("confidence"),
        "grounding": comps.get("groundingScore", meta.get("confidence")),
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
    result: dict[str, Any] = {"mode": mode, "requirements": [], "solicitation": {}, "evaluation_criteria": [],
                              "required_forms": [], "files": [], "pages": 0, "credits_cost": 0,
                              "credits_remaining": None, "skipped": [], "errors": []}
    if not extraction_available():
        result["errors"].append("NUTRIENT_API_KEY not set")
        return result

    pdfs = [p for p in file_paths if p.suffix.lower() == ".pdf" and p.is_file()]
    budget = EXTRACTION_MAX_PAGES
    seq = 0
    for path in pdfs:
        n = page_count(path)
        if n is not None and n > budget:
            result["skipped"].append(f"{path.name} ({n} pages — over the remaining {budget}-page budget)")
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
        result["pages"] += one["pages"] or (n or 0)
        if n:
            budget -= n
        if one["credits_cost"]:
            result["credits_cost"] += int(one["credits_cost"])
        if one["credits_remaining"] is not None:
            result["credits_remaining"] = one["credits_remaining"]

        sol = data.get("solicitation") or {}
        for k, v in sol.items():
            if v and not result["solicitation"].get(k):
                result["solicitation"][k] = v

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
                "section": str(item.get("section") or "").strip()[:80],
                "text": str(item.get("text")).strip()[:1500],
                "category": cat if cat in CATEGORIES.replace(" ", "").split("|") else "other",
                "mandatory": bool(item.get("mandatory")),
                "page": cite.get("page"),
                "grounding": cite.get("grounding"),
                "confidence": cite.get("confidence"),
            })
        for c in data.get("evaluation_criteria") or []:
            if isinstance(c, dict) and c.get("criterion"):
                result["evaluation_criteria"].append({"criterion": str(c["criterion"])[:300], "weight": str(c.get("weight") or "")[:40]})
        for frm in data.get("required_forms") or []:
            if frm and str(frm) not in result["required_forms"]:
                result["required_forms"].append(str(frm)[:200])

    result["stats"] = {
        "requirements": len(result["requirements"]),
        "mandatory": sum(1 for r in result["requirements"] if r["mandatory"]),
        "low_grounding": sum(1 for r in result["requirements"] if (r.get("grounding") or 1) < 0.6),
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
    for r in extracted["requirements"]:
        tags = [f"p.{r['page']}" if r.get("page") else "", f"§{r['section']}" if r.get("section") else "",
                r.get("category", ""), "mandatory" if r.get("mandatory") else "",
                f"grounding {r['grounding']:.2f}" if isinstance(r.get("grounding"), (int, float)) else ""]
        lines.append(f"[{r['id']}] ({', '.join(t for t in tags if t)}) {r['text']}")
    if extracted.get("evaluation_criteria"):
        lines.append("Evaluation criteria: " + "; ".join(f"{c['criterion']} ({c['weight']})" if c.get("weight") else c["criterion"]
                                                        for c in extracted["evaluation_criteria"]))
    if extracted.get("required_forms"):
        lines.append("Required forms/attachments: " + "; ".join(extracted["required_forms"]))
    return "\n".join(lines)
