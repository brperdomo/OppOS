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
EXTRACTION_MAX_PAGES = int((os.environ.get("EXTRACTION_MAX_PAGES") or "400").strip() or 400)
# Office files are converted by the API; their page count is estimated from the text OppOS already read.
EXTRACTABLE = {".pdf", ".doc", ".docx", ".rtf", ".odt", ".xls", ".xlsx", ".xlsm", ".ppt", ".pptx"}
CHARS_PER_PAGE_ESTIMATE = 2500
EXTRACTION_WORKERS = 4
_POLL_LIMIT_S = 40 * 60
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
    """One document through Data Extraction's async endpoint (no 5-minute limit): submit, poll the run, read its
    result, then delete the stored run — runs are kept by the API until deleted, and RFP documents should not be."""
    import mimetypes
    import time
    headers = {"Authorization": f"Bearer {api_key()}"}
    instructions = {"mode": mode, "schema": REQUIREMENTS_SCHEMA, "citationsEnabled": True}
    ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    resp = httpx.post(EXTRACT_URL + "/async", headers=headers, data={"instructions": json.dumps(instructions)},
                      files={"file": (path.name, path.read_bytes(), ctype)}, timeout=120.0)
    resp.raise_for_status()
    run_id = resp.json().get("id")
    base = EXTRACT_URL.rsplit("/", 1)[0] + f"/runs/{run_id}"
    try:
        started, wait, run = time.time(), 3.0, {}
        while True:
            time.sleep(wait)
            run = httpx.get(base, headers=headers, timeout=30.0).json()
            if run.get("status") in ("done", "error", "canceled"):
                break
            if time.time() - started > _POLL_LIMIT_S:
                raise TimeoutError(f"extraction still running after {_POLL_LIMIT_S // 60} minutes")
            wait = min(wait * 1.5, 15.0)
        if run.get("status") != "done":
            raise RuntimeError(f"extraction {run.get('status')}: {run.get('error')}")
        body = httpx.get(base + "/assets/result", headers=headers, timeout=60.0, follow_redirects=True).json()
    finally:
        try:
            httpx.delete(base, headers=headers, timeout=30.0)
        except Exception:
            logger.warning("Could not delete extraction run %s", run_id)
    out = body.get("output") or {}
    credits = ((run.get("usage") or {}).get("data_extraction_credits") or {})
    return {
        "data": out.get("data") or {},
        "metadata": out.get("metadata") or {},
        "pages": len(out.get("pages") or []) or int((run.get("metrics") or {}).get("pagesProcessed") or 0),
        "credits_cost": credits.get("cost"),
        "credits_remaining": credits.get("remainingCredits"),
        "request_id": run_id,
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


_REPLACE_RE = re.compile(r"\b(replace[sd]?|replacing|revise[sd]?|revision|delete[sd]?|remove[sd]?|supersede[sd]?|amended to read|is hereby|in lieu of|changed? to|strike|rescind\w*|withdraw\w*)\b", re.I)
_ADDITIVE_RE = re.compile(r"\b(in addition|additionally|add(?:ed|s)?|new requirement|supplement\w*|also|further requirement|clarif\w+|as well as)\b", re.I)
_SECTION_REF_RE = re.compile(r"(?:section|§|item|paragraph|clause|requirement|part)\s*([0-9]+(?:\.[0-9]+)*[a-z]?)", re.I)


_STOP = {"the", "a", "an", "and", "or", "of", "to", "in", "for", "with", "shall", "must", "will", "vendor", "contractor", "section", "is", "are",
         "be", "by", "on", "at", "as", "that", "this", "it", "its", "all", "any", "replace", "replaced", "revised", "revise", "read", "delete", "deleted",
         "remove", "removed", "supersede", "superseded", "hereby", "lieu", "strike", "amended", "following", "entirety", "provide", "provided", "support"}


def _content_tokens(text: str) -> set[str]:
    toks = set()
    for w in re.findall(r"[a-z0-9][a-z0-9.-]*", (text or "").lower()):
        w = w.strip(".-")
        if w in _STOP or len(w) < 3 and not w.isdigit():
            continue
        toks.add(w.rstrip("s") if len(w) > 3 else w)
    return toks


def _mark_supersessions(result: dict[str, Any]) -> None:
    """Link amendment items to the requirements they replace. An item supersedes an earlier item only when it
    carries replacement / deletion language and targets it specifically: the same section id (or a section it
    names) and — when several items share that section — shared content with the original's text. Additive or
    ambiguous amendments never retire anything; they are listed for human review. Amendments are applied in
    chronology (printed date, then number, then file-name number; unknown order → review) and an amendment item
    is itself a target for a newer amendment, so only the newest revision of a section stays active."""
    reqs = result.get("requirements") or []
    links: list[dict[str, Any]] = []
    reviews: list[dict[str, Any]] = []
    rank_of = lambda r: tuple(r.get("amend_rank")) if r.get("amend_rank") else None
    amendments = [r for r in reqs if r.get("document_type") == "amendment"]
    # One total chronology key for the whole package: printed dates when every amendment has one, else printed /
    # file-name numbers when every amendment has one, else no order at all (amendments then never retire each
    # other — the pairs go to review). Pairwise date-or-number comparison is not transitive and could cycle.
    ranks = [rank_of(a) for a in amendments]
    if ranks and all(r and r[0] for r in ranks):
        chrono = lambda r: (r[0], r[1])
    elif ranks and all(r and r[1] >= 0 for r in ranks):
        # Numbers order everything — unless the dates that ARE printed contradict that order, in which case the
        # metadata is unreliable and nothing is ordered.
        dated = sorted((r for r in ranks if r[0]), key=lambda r: r[1])
        chrono = None if any(a[0] > b[0] for a, b in zip(dated, dated[1:])) else (lambda r: ("", r[1]))
    else:
        chrono = None
    amendments.sort(key=lambda a: (chrono(rank_of(a)) if chrono else ("", -1), a["id"]))
    def _newer(a: dict[str, Any], b: dict[str, Any]) -> bool | None:
        if chrono is None:
            return None
        ka, kb = chrono(rank_of(a)), chrono(rank_of(b))
        return None if ka == kb else ka > kb
    for a in amendments:
        text = a.get("text") or ""
        sec = (a.get("section") or "").strip().lower()
        secs = {sec} if sec else set()
        secs |= {ref.lower() for ref in _SECTION_REF_RE.findall(text)}
        same_section = [o for o in reqs if o is not a and not o.get("superseded_by") and (o.get("section") or "").strip().lower() in secs]
        candidates, unordered = [], []
        for o in same_section:
            if o.get("document_type") == "amendment":
                (candidates if _newer(a, o) is True else unordered).append(o)
            else:
                candidates.append(o)
        if not candidates and not unordered:
            continue
        basis = "same section " + (a.get("section") or next(iter(secs)))
        replacing = bool(_REPLACE_RE.search(text)) and not _ADDITIVE_RE.search(text)
        if replacing and len(candidates) > 1:
            # Several items share the section: retire only those whose content the amendment's *old-value* part
            # refers to — the text before "with"/"to read"/"as follows" names what is replaced; the new value after
            # it must not be used to match ("replace the 90-day retention period with 365 days" must not catch an
            # unrelated item that mentions 365).
            old_part = re.split(r"\b(?:with|to read|as follows|to:|is replaced by|shall now read)\b", _SECTION_REF_RE.sub(" ", text), maxsplit=1, flags=re.I)[0]
            a_toks = _content_tokens(old_part)
            matched = [o for o in candidates if len(_content_tokens(o.get("text")) & a_toks) >= 2]
            if matched:
                candidates = matched
            else:
                unordered += candidates
                candidates = []
                basis += " — no specific match"
        if replacing and candidates:
            for o in candidates:
                o["superseded_by"] = a["id"]
                links.append({"old": o["id"], "new": a["id"], "new_file": a.get("file", ""), "basis": basis + " with replacement language"})
        touches = [o["id"] for o in (candidates if not replacing else []) + unordered]
        if touches:
            why = (" (additive wording)" if _ADDITIVE_RE.search(text) else " (no replacement language)" if not replacing
                   else " (amendment order unknown)" if unordered else "")
            reviews.append({"amendment": a["id"], "file": a.get("file", ""), "touches": touches, "basis": basis + why})
    # Resolve chains: whatever an item points at, it ends up pointing at the newest active revision, and that
    # revision lists everything it retired.
    by_id = {r["id"]: r for r in reqs}
    for r in reqs:
        seen, cur = set(), r.get("superseded_by")
        while cur and cur not in seen and by_id.get(cur, {}).get("superseded_by"):
            seen.add(cur)
            cur = by_id[cur]["superseded_by"]
        if cur and cur != r.get("superseded_by"):
            r["superseded_by"] = cur
    for r in reqs:
        r.pop("supersedes", None)
    for r in reqs:
        if r.get("superseded_by"):
            by_id[r["superseded_by"]].setdefault("supersedes", []).append(r["id"])
    for l in links:
        l["new"] = by_id[l["old"]]["superseded_by"]
        l["new_file"] = by_id[l["new"]].get("file", "")
    result["supersessions"] = links
    result["amendment_reviews"] = reviews


def extract_rfp_requirements(
    file_paths: list[Path],
    mode: str | None = None,
    on_progress: Callable[[str], None] | None = None,
    page_hints: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Run Data Extraction over the RFP documents (PDF and Office files, up to EXTRACTION_WORKERS at a time) and
    merge into one page-cited requirement list. `page_hints`: estimated pages for non-PDF files, by file name.

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

    from concurrent.futures import ThreadPoolExecutor
    from oppos.sources.extract_text import _weight
    page_hints = page_hints or {}
    docs = [p for p in file_paths if p.suffix.lower() in EXTRACTABLE and p.is_file()]
    docs.sort(key=lambda p: (-_weight(p.name), p.name))  # the page budget goes to the solicitation first
    budget = EXTRACTION_MAX_PAGES
    seq = 0
    chosen: list[tuple[Path, int]] = []
    for path in docs:
        n = page_count(path) if path.suffix.lower() == ".pdf" else page_hints.get(path.name)
        if n is None:
            # The API charges per page and the charge cannot be undone — a file whose size we cannot bound
            # locally is never uploaded.
            result["skipped"].append(f"{path.name} (page count unknown — cannot bound credit spend)")
            continue
        if n > budget:
            result["skipped"].append(f"{path.name} ({n} pages — over the remaining {budget}-page budget)")
            continue
        budget -= n  # reserved before upload: a charged request whose response is lost must still count
        chosen.append((path, n))

    def _run(item: tuple[Path, int]) -> tuple[Path, int, dict[str, Any] | None, str]:
        path, n = item
        if on_progress:
            on_progress(f"Pulling out the requirements: {path.name}" + (f" ({n} pages)" if n else ""))
        try:
            return path, n, _extract_one(path, mode), ""
        except httpx.HTTPStatusError as e:
            return path, n, None, f"HTTP {e.response.status_code} {e.response.text[:160]}"
        except Exception as e:  # timeout, disconnect, invalid JSON — the server may have processed and charged it
            return path, n, None, str(e)[:200]

    with ThreadPoolExecutor(max_workers=EXTRACTION_WORKERS) as pool:
        done = list(pool.map(_run, chosen))
    for path, n, one, err in done:  # merge main documents first: the solicitation's own facts win over terms and forms
        if one is None:
            result["errors"].append(f"{path.name}: {err}")
            continue

        data, meta = one["data"], one["metadata"]
        result["files"].append({"file": path.name, "pages": one["pages"], "credits": one["credits_cost"], "request_id": one["request_id"]})
        result["pages"] += one["pages"] or n
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
                "amend_rank": list(rank) if rank else None,
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


_REQ_HEADER = re.compile(r"(requirements?|requirement description|specification|question)", re.I)
_ID_HEADER = re.compile(r"(req(uirement)?\.?\s*(#|no\.?|id|number)|^id$|^#$|^item( #| no\.?)?$|^ref(erence)?\b)", re.I)


def _cells(row: str) -> list[str]:
    import html as _html
    return [_html.unescape(re.sub(r"<[^>]+>", "", re.sub(r"<br\s*/?>", " ", c))).strip()
            for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)]


def _matrix_category(cat: str, text: str) -> str:
    t = f"{cat} {text}".lower()
    if re.search(r"secur|privacy|complian|audit|access control|encrypt|hipaa|cjis|fedramp|soc ?2", t):
        return "security_compliance"
    if re.search(r"interface|integrat|api|data (migration|conversion)|technical|infrastructure|hosting|performance", t):
        return "technical"
    if re.search(r"train|support|maint|implement|transition|project", t):
        return "implementation"
    return "functional"


def matrix_requirements(file_name: str, markdown: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Requirements matrices (a table with a Requirement column, usually a spreadsheet the agency scores): one
    requirement per row, with its ID and category; plus the columns the vendor fills in. Read straight from the
    document's Markdown — exact and free, and Data Extraction often returns nothing for these."""
    out: list[dict[str, Any]] = []
    answer_cols: list[str] = []
    for tbl in re.findall(r"<table>(.*?)</table>", markdown, re.S):
        rows = [_cells(r) for r in re.findall(r"<tr>(.*?)</tr>", tbl, re.S)]
        hi = next((i for i, r in enumerate(rows) if any(_REQ_HEADER.fullmatch(c) for c in r)), None)
        if hi is None:
            continue
        head = rows[hi]
        ri = next(i for i, c in enumerate(head) if _REQ_HEADER.fullmatch(c))
        ii = next((i for i, c in enumerate(head) if i != ri and _ID_HEADER.search(c)), 0 if ri else None)
        ci = next((i for i, c in enumerate(head) if re.fullmatch(r"(category|section|area|module|function)", c, re.I)), None)
        for c in head[ri + 1:]:
            if c and c not in answer_cols:
                answer_cols.append(c)
        for r in rows[hi + 1:]:
            if len(r) <= ri or len(r[ri]) < 8:
                continue
            rid = r[ii] if ii is not None and ii < len(r) else ""
            if ii is not None and not rid:
                continue  # a heading row inside the table
            cat = r[ci] if ci is not None and ci < len(r) else ""
            out.append({"file": file_name, "document_type": "requirements_matrix", "section": " ".join(x for x in (rid, cat) if x)[:80],
                        "text": r[ri][:1500], "category": _matrix_category(cat, r[ri]), "mandatory": False,
                        "page": None, "grounding": None, "confidence": None, "cited": False})
    return out, answer_cols


def add_matrices(extracted: dict[str, Any], documents: list[tuple[str, str]]) -> int:
    """Add requirements-matrix rows from the documents' Markdown to an extraction (skipping ones it already has).
    Returns how many were added; records each matrix's answer columns for the drafter."""
    have = {re.sub(r"\W+", " ", str(r.get("text", "")).lower()).strip() for r in extracted.get("requirements") or []}
    seq = max([int(str(r.get("id", "E0"))[1:] or 0) for r in extracted.get("requirements") or []] + [0])
    added = 0
    for name, text in documents:
        rows, cols = matrix_requirements(name, text or "")
        if not rows:
            continue
        extracted.setdefault("answer_columns", {})[name] = cols
        for r in rows:
            key = re.sub(r"\W+", " ", r["text"].lower()).strip()
            if key in have:
                continue
            have.add(key)
            seq += 1
            extracted.setdefault("requirements", []).append({"id": f"E{seq}", **r})
            added += 1
    if added:
        st_ = extracted.setdefault("stats", {})
        st_["requirements"] = len(extracted["requirements"])
        st_["from_matrices"] = st_.get("from_matrices", 0) + added
    extracted["matrices_checked"] = True
    return added


OBLIGATION_TYPES = ("terms_and_conditions", "form")  # contractual / paperwork: acknowledged, not answered one by one
DRAFT_MAX_REQUIREMENTS = int((os.environ.get("DRAFT_MAX_REQUIREMENTS") or "150").strip() or 150)


def drafting_subset(extracted: dict[str, Any], limit: int = DRAFT_MAX_REQUIREMENTS) -> tuple[dict[str, Any], int]:
    """The requirements the drafter answers one by one: not superseded, not from terms or forms; the solicitation's
    own items first, mandatory before optional, at most `limit`, kept in document order. Returns (extraction with that subset, how many were left out)."""
    pool = [r for r in extracted.get("requirements") or []
            if not r.get("superseded_by") and r.get("document_type") not in OBLIGATION_TYPES]
    rank = {"solicitation": 0, "amendment": 0, "requirements_matrix": 0, "submission_instructions": 1}
    keep = sorted(pool, key=lambda r: (rank.get(r.get("document_type"), 2), not r.get("mandatory"),
                                       int(str(r.get("id", "E0"))[1:] or 0)))[:limit]
    ids = {r["id"] for r in keep}
    sub = dict(extracted)
    sub["requirements"] = [r for r in pool if r["id"] in ids]
    return sub, len(pool) - len(keep)


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
    for name, cols in (extracted.get("answer_columns") or {}).items():
        if cols:
            lines.append(f"Requirements matrix {name}: the agency expects each row answered in these columns: {', '.join(cols)}. "
                         "For each matrix item, say which applies to Nutrient and add a short vendor comment.")
    return "\n".join(lines)
