"""Stage 3 — draft a response to a pursued RFP.

One grounded call: extract the RFP's requirements/questions, map each to the LOB
positioning profile (and Nutrient docs via Kapa when configured), and draft an
answer per item with an explicit basis and confidence. Compliance claims come
only from oppos/drafting/compliance.md once the security team has approved it;
until then they are marked [SECURITY TO CONFIRM]. Pricing is never invented.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import anthropic

from oppos.config import SCORING_MODEL_STAGE2
from oppos.drafting.extraction import format_for_prompt
from oppos.scoring.lobs import DEFAULT_LOB, LOBS, get_lob
from oppos.scoring.lobs.base import _FRONTMATTER_RE
from oppos.scoring.qualifier import (
    _KAPA_SERVER_NAME,
    _MCP_BETA,
    KAPA_API_KEY,
    KAPA_MCP_URL,
    _final_text,
    _get_client,
    _grounding_summary,
    _repair_and_parse_json,
    _track,
    kapa_enabled,
)

logger = logging.getLogger(__name__)

# Drafting is rare (one call per pursued RFP) and quality matters more than cost.
DRAFT_MODEL = (os.environ.get("DRAFT_MODEL") or "").strip() or "claude-opus-5"
DRAFT_MAX_TOKENS = int((os.environ.get("DRAFT_MAX_TOKENS") or "16000").strip() or 16000)
MAX_RFP_CHARS = 150_000           # description + attachment text passed to the model
COMPLIANCE_PATH = Path(__file__).resolve().parent / "compliance.md"

_CATEGORIES = ("functional", "technical", "security_compliance", "commercial", "company", "implementation", "other")

SECURITY_MARK = "[SECURITY TO CONFIRM]"
SALES_MARK = "[SALES TO PROVIDE]"
NOT_DRAFTED_MARK = "[NOT DRAFTED]"

# Any sentence making one of these claims is a compliance claim and is gated when compliance.md is unapproved.
_COMPLIANCE_RE = re.compile(
    r"\b(SOC ?[123]|ISO ?\d{4,5}|FedRAMP|StateRAMP|TX-RAMP|HIPAA|BAA|HITRUST|GDPR|CCPA|CJIS|PCI(?:[- ]DSS)?|FIPS(?:[ -]?140)?"
    r"|NIST(?: ?(?:800-53|800-171|CSF))?|IRS ?1075|FERPA|GLBA|SOX|Section ?508|WCAG|VPAT|ACR|penetration[- ]test|pen[- ]test"
    r"|data residency|encrypt(?:ed|ion)(?: at rest| in transit)?|certif(?:ied|ication|icate)s?|accredit(?:ed|ation)|attestation"
    r"|audit report|compliant|compliance|GovCloud|GCC(?: High)?|data (?:center|centre) location)\b",
    re.I,
)
_PRICING_RE = re.compile(
    r"\$\s?\d|\b(pric(?:e|es|ing)|per[- ](?:user|seat|named user|page|document|month|year|annum|transaction)|license fee|subscription fee"
    r"|discount|quote|quotation|cost(?:s|ing)? (?:is|are|will|would|of)|total cost|TCO)\b",
    re.I,
)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\[\"'(])")


def _gate_compliance_prose(text: str) -> tuple[str, bool]:
    """Prefix every sentence that makes a compliance claim with SECURITY_MARK (unapproved mode).

    A sentence counts as gated only if it *starts* with the marker, so compound sentences
    like "We are SOC 2 certified; [SECURITY TO CONFIRM] residency" are still flagged.
    """
    if not text:
        return text, False
    out, flagged = [], False
    for sent in _SENTENCE_SPLIT.split(text.strip()):
        if _COMPLIANCE_RE.search(sent) and not sent.lstrip().startswith(SECURITY_MARK):
            sent = f"{SECURITY_MARK} {sent.strip()}"
            flagged = True
        out.append(sent)
    return " ".join(out), flagged

_BASIS = ("rfp", "profile", "docs", "compliance", "needs_human")
_CONFIDENCE = ("high", "medium", "low")


# ---------------------------------------------------------------------------
# Compliance source (approved file only)
# ---------------------------------------------------------------------------

def compliance_status() -> dict[str, Any]:
    """{"approved": bool, "version", "approved_by", "approved_at", "body"}"""
    if not COMPLIANCE_PATH.is_file():
        return {"approved": False, "version": 0, "approved_by": "", "approved_at": "", "body": ""}
    text = COMPLIANCE_PATH.read_text(encoding="utf-8")
    meta: dict[str, str] = {}
    m = _FRONTMATTER_RE.match(text)
    body = text
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                meta[k.strip()] = v.strip()
        body = text[m.end():]
    approved = str(meta.get("approved", "false")).lower() in ("true", "yes", "1")
    return {"approved": approved, "version": meta.get("version", "0"), "approved_by": meta.get("approved_by", ""),
            "approved_at": meta.get("approved_at", ""), "body": body.strip()}


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

def _system(lob_key: str, grounded: bool) -> str:
    lob = get_lob(lob_key) or LOBS[DEFAULT_LOB]
    comp = compliance_status()
    if comp["approved"]:
        compliance_block = f"""## Approved compliance answers (version {comp['version']}, approved by {comp['approved_by']} on {comp['approved_at']})
Use ONLY the facts below for any security, certification, hosting, privacy, accessibility or insurance question. If the RFP asks for something not listed here, answer with "[SECURITY TO CONFIRM]" and set basis to needs_human.

{comp['body']}
"""
    else:
        compliance_block = """## Compliance answers — NOT AVAILABLE
No approved compliance source exists yet. For every security, certification, hosting, privacy, accessibility or insurance question, write the response as "[SECURITY TO CONFIRM] — <one sentence stating exactly what needs confirming>", set confidence "low", basis ["needs_human"] and human_todo accordingly. Never assert a certification, attestation, BAA, FedRAMP/StateRAMP status, or data-residency guarantee.
"""
    docs_block = ""
    if grounded:
        docs_block = """## Documentation grounding
You have a documentation search tool connected to Nutrient's product docs. Use it (up to 8 searches) to confirm specific technical capabilities before asserting them, and add the doc URL to `sources` with basis "docs". If the docs do not confirm a capability, do not claim it — use needs_human.
"""
    thin = "" if lob.depth == "full" else "\nNOTE: this LOB profile is THIN (description only). Be conservative: prefer needs_human over confident claims about wins, verticals, or competitive position.\n"
    return f"""You are drafting Nutrient's response to a public-sector or enterprise RFP/RFI for the **Nutrient {lob.label}** line of business. The reader is the SDR/SE who will finish and submit it; your job is a strong, honest first draft that maps every requirement to what we can actually offer.

{lob.profile}
{thin}
{compliance_block}
{docs_block}
## Drafting rules
- Extract EVERY requirement, question, or evaluation criterion the RFP states (functional, technical, security/compliance, commercial, company, implementation). Keep the RFP's own numbering/section labels in `section` when present and quote or closely paraphrase the requirement in `text`.
- If a PRE-EXTRACTED REQUIREMENTS block is present, it came from Nutrient's Data Extraction API with page citations: respond to every item in it, reuse its ids (E1, E2 …) and copy its `page` and `file`; add anything it missed with new ids (R1, R2 …). Do not drop or merge pre-extracted items.
- Draft each `response` in first person plural ("we", "Nutrient"), 2–6 sentences, concrete: name the capability, how it meets the requirement, and any configuration or integration involved. No marketing filler.
- `basis` lists where the answer comes from: "rfp" (restating facts in the RFP), "profile" (the profile above), "docs" (documentation you searched), "compliance" (the approved compliance section), "needs_human" (a person must supply or verify it). `sources` names the profile section or doc URL used.
- Never invent customers, certifications, pricing, SLAs, or capabilities. Pricing/commercial terms → "[SALES TO PROVIDE]" with basis needs_human. References/case studies → only those named in the profile.
- Where we genuinely cannot meet a requirement, say so plainly in the response (and list it in `do_not_claim`) — a credible partial answer beats an overclaim.
- `open_questions` are questions worth submitting during the RFP's Q&A period. `assumptions` are the assumptions your draft relies on.

Respond with ONLY valid JSON matching this schema:
{{
  "rfp_type": "<RFI | RFP | RFQ | sources_sought | other>",
  "submission": {{"method": "<portal | email | mail | unknown>", "deadline": "<as stated or unknown>", "format_requirements": ["<page limits, forms, sections required>"]}},
  "executive_summary": "<2–3 paragraphs we could open the response with>",
  "win_themes": ["<3–5 themes to carry through the response>"],
  "requirements": [
    {{"id": "E1 or R1", "section": "<RFP section/number or ''>", "page": <page number or null>, "file": "<source PDF name or ''>", "text": "<the requirement or question>",
      "category": "<functional | technical | security_compliance | commercial | company | implementation | other>",
      "response": "<draft answer>", "confidence": "<high | medium | low>",
      "basis": ["<rfp | profile | docs | compliance | needs_human>"], "sources": ["<profile section or URL>"],
      "human_todo": "<what a person must add or verify, or ''>"}}
  ],
  "open_questions": ["<question for Q&A>"],
  "assumptions": ["<assumption>"],
  "do_not_claim": ["<requirement we cannot honestly claim to meet>"]
}}"""


def _rfp_text(opp: dict[str, Any], attachment_text: str, extracted: dict[str, Any] | None = None) -> str:
    parts = [
        f"Title: {opp.get('title', '')}",
        f"Agency: {opp.get('agency', '')}",
        f"Solicitation: {opp.get('solicitation_number', '') or ''}",
        f"Notice type: {opp.get('notice_type', '') or ''}",
        f"Response deadline: {opp.get('response_deadline', '') or 'unknown'}",
        f"Place of performance: {opp.get('place_of_performance', '') or ''}",
        f"URL: {opp.get('url', '') or ''}",
        f"Contact: {opp.get('contact_name', '') or ''} {opp.get('contact_email', '') or ''}".strip(),
        "",
        "=== RFP DESCRIPTION ===",
        (opp.get("description") or "").strip(),
    ]
    pre = format_for_prompt(extracted) if extracted else ""
    if pre:
        parts += ["", pre]
    att = (attachment_text or opp.get("attachment_text") or "").strip()
    if att:
        parts += ["", "=== RFP DOCUMENTS (extracted text) ===", att]
    text = "\n".join(parts)
    if len(text) > MAX_RFP_CHARS:
        text = text[:MAX_RFP_CHARS] + "\n\n[... RFP text truncated for length ...]"
    return text


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

def _norm_list(v: Any, limit: int = 30) -> list[str]:
    if not isinstance(v, list):
        return []
    return [str(x).strip() for x in v if str(x).strip()][:limit]


def _normalize(raw: dict[str, Any], lob_key: str, grounding: dict[str, Any] | None, truncated: bool,
               extracted: dict[str, Any] | None = None) -> dict[str, Any]:
    comp = compliance_status()
    reqs_out: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    by_ext: dict[str, dict[str, Any]] = {e["id"]: e for e in ((extracted or {}).get("requirements") or [])}
    for i, r in enumerate(raw.get("requirements") or [], 1):
        if not isinstance(r, dict):
            continue
        basis = [b for b in _norm_list(r.get("basis"), 5) if b in _BASIS] or ["needs_human"]
        cat = str(r.get("category") or "other").strip()
        cat = cat if cat in _CATEGORIES else "other"
        conf = str(r.get("confidence") or "low").strip().lower()
        conf = conf if conf in _CONFIDENCE else "low"
        response = str(r.get("response") or "").strip()
        todo = str(r.get("human_todo") or "").strip()
        req_text = str(r.get("text") or "").strip()
        # Hard gates, applied to EVERY category — the model's category and markers are not trusted.
        if not comp["approved"]:
            if cat == "security_compliance" and not response.lstrip().startswith(SECURITY_MARK):
                response = f"{SECURITY_MARK} {response}".strip() if response else SECURITY_MARK
                gated = True
            else:
                response, gated = _gate_compliance_prose(response)
            if gated or cat == "security_compliance":
                basis, conf = ["needs_human"], "low"
                todo = todo or "Security team to confirm every compliance statement in this answer."
        if cat == "commercial" or _PRICING_RE.search(response):
            response = f"{SALES_MARK} — pricing / commercial terms for: {req_text[:160] or 'this requirement'}"
            basis, conf = ["needs_human"], "low"
            todo = "Sales to provide pricing and commercial terms."
        page = r.get("page")
        try:
            page = int(page) if page not in (None, "", "null") else None
        except (TypeError, ValueError):
            page = None
        rid = str(r.get("id") or f"R{i}").strip()
        if rid in seen_ids:
            continue  # duplicate id from the model — keep the first answer
        seen_ids.add(rid)
        reqs_out.append({
            "id": rid,
            "file": str(r.get("file") or by_ext.get(rid, {}).get("file") or "").strip()[:120],
            "section": str(r.get("section") or by_ext.get(rid, {}).get("section") or "").strip()[:80],
            "page": page if page is not None else by_ext.get(rid, {}).get("page"),
            "text": str(r.get("text") or "").strip()[:1500],
            "category": cat,
            "response": response[:4000],
            "confidence": conf,
            "basis": basis,
            "sources": _norm_list(r.get("sources"), 8),
            "human_todo": todo[:500],
        })
    # Every extracted requirement must be answered; synthesize a needs_human entry for any the model dropped.
    missing = [e for rid, e in by_ext.items() if rid not in seen_ids]
    for e in missing:
        reqs_out.append({
            "id": e["id"], "file": e.get("file") or "", "section": e.get("section") or "", "page": e.get("page"),
            "text": e.get("text", "")[:1500], "category": e.get("category") or "other",
            "response": f"{NOT_DRAFTED_MARK} — the model did not return an answer for this extracted requirement; draft it manually.",
            "confidence": "low", "basis": ["needs_human"], "sources": [], "human_todo": "Draft this answer.",
        })

    exec_summary = str(raw.get("executive_summary") or "").strip()
    win_themes = _norm_list(raw.get("win_themes"), 8)
    assumptions = _norm_list(raw.get("assumptions"), 20)
    if not comp["approved"]:
        exec_summary, _ = _gate_compliance_prose(exec_summary)
        win_themes = [_gate_compliance_prose(t)[0] for t in win_themes]
        assumptions = [_gate_compliance_prose(a)[0] for a in assumptions]

    sub = raw.get("submission") if isinstance(raw.get("submission"), dict) else {}
    return {
        "lob": lob_key,
        "model": DRAFT_MODEL,
        "generated_at": datetime.utcnow().isoformat(timespec="seconds"),
        "compliance_source": {"approved": comp["approved"], "version": comp["version"]},
        "grounding": grounding,
        "extraction": ({k: extracted.get(k) for k in ("mode", "files", "pages", "credits_cost", "credits_remaining", "skipped", "errors", "stats")}
                       if extracted else None),
        "truncated": truncated,
        "rfp_type": str(raw.get("rfp_type") or "other"),
        "submission": {"method": str(sub.get("method") or "unknown"), "deadline": str(sub.get("deadline") or "unknown"),
                       "format_requirements": _norm_list(sub.get("format_requirements"), 15)},
        "executive_summary": exec_summary,
        "win_themes": win_themes,
        "requirements": reqs_out,
        "open_questions": _norm_list(raw.get("open_questions"), 20),
        "assumptions": assumptions,
        "do_not_claim": _norm_list(raw.get("do_not_claim"), 20),
        "stats": {
            "requirements": len(reqs_out),
            "needs_human": sum(1 for r in reqs_out if "needs_human" in r["basis"]),
            "high_confidence": sum(1 for r in reqs_out if r["confidence"] == "high"),
            "missing_from_model": len(missing),
        },
    }


# ---------------------------------------------------------------------------
# API calls (streaming — the output is long)
# ---------------------------------------------------------------------------

def _call_plain(client: anthropic.Anthropic, system: str, user_text: str) -> Any:
    with client.messages.stream(
        model=DRAFT_MODEL,
        max_tokens=DRAFT_MAX_TOKENS,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user_text}],
    ) as stream:
        resp = stream.get_final_message()
    _track(resp)
    return resp


class _Collected:
    def __init__(self, content: list[Any], stop_reason: str):
        self.content, self.stop_reason = content, stop_reason


def _call_grounded(client: anthropic.Anthropic, system: str, user_text: str) -> _Collected | None:
    messages: list[dict[str, Any]] = [{"role": "user", "content": user_text}]
    kwargs = dict(
        model=DRAFT_MODEL, max_tokens=DRAFT_MAX_TOKENS + 2000,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        betas=[_MCP_BETA],
        mcp_servers=[{"type": "url", "url": KAPA_MCP_URL, "name": _KAPA_SERVER_NAME, "authorization_token": KAPA_API_KEY}],
        tools=[{"type": "mcp_toolset", "mcp_server_name": _KAPA_SERVER_NAME}],
    )
    collected: list[Any] = []
    stop = ""
    for _ in range(6):
        with client.beta.messages.stream(messages=messages, **kwargs) as stream:
            resp = stream.get_final_message()
        _track(resp)
        collected.extend(resp.content)
        stop = getattr(resp, "stop_reason", "") or ""
        if stop != "pause_turn":
            break
        messages.append({"role": "assistant", "content": resp.content})
    else:
        logger.warning("Kapa-grounded drafting still paused after 6 continuations — drafting ungrounded")
        return None
    if not any(getattr(b, "type", "") == "text" and getattr(b, "text", "") for b in collected):
        return None
    return _Collected(collected, stop)


def draft_response(opp: dict[str, Any], attachment_text: str = "", lob_key: str | None = None,
                   extracted: dict[str, Any] | None = None) -> dict[str, Any]:
    """Produce the structured draft for one opportunity. Raises anthropic.APIError on hard failure.

    `extracted` is the optional output of extraction.extract_rfp_requirements — page-cited
    requirements from Nutrient's Data Extraction API that the model must answer item by item.
    """
    lob = (get_lob(lob_key or opp.get("lob")) or LOBS[DEFAULT_LOB]).key
    client = _get_client()
    user_text = "Draft our response to this RFP.\n\n" + _rfp_text(opp, attachment_text, extracted)

    grounding = None
    resp: Any = None
    if kapa_enabled():
        try:
            resp = _call_grounded(client, _system(lob, grounded=True), user_text)
            if resp is not None:
                grounding = _grounding_summary(resp)
        except anthropic.APIError as e:
            logger.warning("Grounded drafting failed (%s); drafting without docs", e)
            resp = None
    if resp is None:
        resp = _call_plain(client, _system(lob, grounded=False), user_text)

    if getattr(resp, "stop_reason", "") == "max_tokens":
        # A repaired prefix would silently drop trailing requirements / do-not-claim items. Refuse it.
        raise RuntimeError(f"Draft hit the {DRAFT_MAX_TOKENS}-token output limit and was discarded — raise DRAFT_MAX_TOKENS "
                           "or split the RFP (e.g. draft per attachment)")
    try:
        raw = _repair_and_parse_json(_final_text(resp))
    except (json.JSONDecodeError, IndexError, KeyError, AttributeError) as e:
        raise RuntimeError(f"Draft could not be parsed: {e}") from e
    return _normalize(raw, lob, grounding, False, extracted)
