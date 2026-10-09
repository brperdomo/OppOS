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
DRAFT_MAX_TOKENS = int((os.environ.get("DRAFT_MAX_TOKENS") or "24000").strip() or 24000)
# Large RFPs are drafted in chunks of this many pre-extracted requirements so no single call overflows.
DRAFT_CHUNK_SIZE = int((os.environ.get("DRAFT_CHUNK_SIZE") or "15").strip() or 15)
TRUST_CENTER_URL = (os.environ.get("TRUST_CENTER_URL") or "https://trust.nutrient.io").strip()
# Default answer for security / compliance items: documentation is shared under NDA via the Trust Center,
# and it is the prospect who requests access. We only verify specifics when the RFP explicitly demands them.
TRUST_CENTER_ANSWER = (
    "Nutrient's security and compliance documentation — including independent audit reports, policies, "
    "and completed security questionnaires — is available under NDA through the Nutrient Trust Center "
    f"({TRUST_CENTER_URL}). We will grant the evaluation team access on request so this requirement can be "
    "reviewed against current documentation rather than a summary."
)
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
# Actual price language only — procurement vocabulary ("submit a quote", "bid opening", "cost schedule attached")
# must not trip this, or every portal instruction becomes a sales item.
_PRICING_RE = re.compile(
    r"\$\s?\d|\d\s?(?:USD|EUR|GBP)\b|\b(?:our|the|nutrient'?s?) pric(?:e|es|ing)\b|\bpric(?:e|es|ing) (?:is|are|starts?|begins?|ranges?|model|structure|tiers?)\b"
    r"|\bper[- ](?:user|seat|named user|page|document|transaction)(?: per (?:month|year))?\b|\blicen[cs]e fee|\bsubscription fee|\b\d{1,3} ?% discount|\bdiscount ?%|\bdiscount of\b|\bTCO\b"
    r"|\bunit (?:cost|price)s?\b|\b(?:cost|price|pricing|rate) (?:schedule|sheet|proposal|breakdown)\b|\bbid (?:price|amount)s?\b|\bfreight (?:charge|cost)s?\b|\bhourly rate|\bnot[- ]to[- ]exceed\b",
    re.I,
)
TEAM_MARK = "[TEAM TO PROVIDE]"
_SECURITY_ASK_RE = re.compile(
    r"\b(SOC ?[123]|ISO ?\d{4,5}|FedRAMP|StateRAMP|TX-RAMP|HIPAA|BAA|HITRUST|CJIS|PCI(?:[- ]DSS)?|FIPS|NIST|IRS ?1075|FERPA|GLBA"
    r"|Section ?508|WCAG|VPAT|ACR|encrypt\w*|data residency|data (?:center|centre)|penetration|vulnerabilit\w*|incident response|breach"
    r"|disaster recovery|business continuity|backup|multi-?factor|MFA|single sign-on|SSO|SAML|audit (?:log|trail)|security (?:controls?|polic|questionnaire|assessment|certif|audit|standard|requirement)"
    r"|privacy|confidentialit\w*|background check|insurance certificate|cyber ?(?:security|liability))\b",
    re.I,
)


def _gate_pricing_prose(text: str) -> tuple[str, bool]:
    """Replace any sentence containing price language with the sales placeholder (summary, themes, assumptions)."""
    if not text:
        return text, False
    out, flagged = [], False
    for sent in _SENTENCE_SPLIT.split(text.strip()):
        if _PRICING_RE.search(sent) and not sent.lstrip().startswith(SALES_MARK):
            sent = f"{SALES_MARK} — pricing statement removed from draft."
            flagged = True
        out.append(sent)
    return " ".join(out), flagged
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\[\"'(])")
# The RFP explicitly demands a specific security statement or artifact *in the response* (not just "be secure").
_EXPLICIT_SECURITY_ASK_RE = re.compile(
    r"\b(provide|attach|submit|include|furnish|supply|enclose)\b.{0,80}\b(SOC|ISO|report|certificat|attestation|audit|questionnaire|VPAT|ACR|policy|policies|evidence|documentation)"
    r"|\b(describe|detail|explain|document|demonstrate|confirm|certify|state|specify|list)\b.{0,60}\b(security|encrypt|authentication|access control|incident|vulnerab|penetration|data (?:residency|retention|center)|backup|disaster|business continuity|SOC|ISO|HIPAA|FedRAMP|StateRAMP|CJIS|PCI|NIST|FIPS|508|WCAG|privacy)"
    r"|\b(must|shall|required to|is required|mandatory)\b.{0,40}\b(SOC ?[123]|ISO ?\d{4,5}|FedRAMP|StateRAMP|HIPAA|BAA|HITRUST|CJIS|PCI|FIPS|NIST|IRS ?1075|FERPA|Section ?508|WCAG|VPAT)\b",
    re.I,
)


def _gate_compliance_prose(text: str) -> tuple[str, bool]:
    """Prefix every sentence that makes a compliance claim with SECURITY_MARK (unapproved mode).

    A sentence counts as gated only if it *starts* with the marker, so compound sentences
    like "We are SOC 2 certified; [SECURITY TO CONFIRM] residency" are still flagged.
    """
    if not text:
        return text, False
    out, flagged = [], False
    for sent in _SENTENCE_SPLIT.split(text.strip()):
        if "Trust Center" in sent:  # the standard pointer is always allowed
            out.append(sent)
            continue
        if _COMPLIANCE_RE.search(sent) and not sent.lstrip().startswith(SECURITY_MARK):
            sent = f"{SECURITY_MARK} {sent.strip()}"
            flagged = True
        out.append(sent)
    return " ".join(out), flagged

_BASIS = ("rfp", "profile", "docs", "compliance", "standard", "needs_human")
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
Default for security, certification, hosting, privacy, accessibility or insurance items is still the Trust Center pointer ({TRUST_CENTER_URL}) — documentation is shared under NDA on the prospect's request. When the RFP explicitly demands a specific statement or artifact in the response, answer it ONLY with the approved facts below (basis ["compliance"]); if the fact is not listed, write "[SECURITY TO CONFIRM]" and set basis to needs_human.

{comp['body']}
"""
    else:
        compliance_block = f"""## Security & compliance answers
Default: Nutrient shares security documentation under NDA through the Trust Center ({TRUST_CENTER_URL}), and it is the prospect who requests access. For a security, certification, hosting, privacy, accessibility or insurance item, answer with that standard pointer (basis ["standard"], confidence "high") — do NOT assert any certification, attestation, BAA, FedRAMP/StateRAMP status, encryption detail or data-residency guarantee yourself.
Exception — ONLY when the RFP explicitly demands a specific statement or artifact in the response itself (e.g. "provide a copy of your SOC 2 report", "describe your encryption at rest", "vendor must hold FedRAMP Moderate"): write "[SECURITY TO CONFIRM] — <exactly what must be confirmed or supplied>", set confidence "low", basis ["needs_human"] and human_todo accordingly.
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
- Never invent customers, certifications, pricing, SLAs, or capabilities. We do not discuss pricing in RFI/RFP responses at all — do not volunteer prices, discounts, TCO or commercial terms anywhere (summary, themes, answers). Only when the RFP explicitly asks for a pricing model, cost schedule or rates, answer with "[SALES TO PROVIDE] — <what is asked>" and basis needs_human. Blanks that only a person can fill (contact names, addresses, phone numbers, signatures, tax IDs, insurance certificates) → "[TEAM TO PROVIDE] — <what>" with basis needs_human. References/case studies → only those named in the profile.
- Portal instructions and form mechanics (how to log in, which tab to use, acknowledge amendments) are not requirements to sell against: answer "Acknowledged — <how we will comply>" with basis ["rfp"].
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
        rid_probe = str(r.get("id") or "").strip()
        ext = by_ext.get(rid_probe)  # authoritative source for extracted items — the model may not rewrite these
        cat = str(r.get("category") or "other").strip()
        cat = cat if cat in _CATEGORIES else "other"
        if ext and ext.get("category") in _CATEGORIES and ext["category"] != "other":
            cat = ext["category"]
        conf = str(r.get("confidence") or "low").strip().lower()
        conf = conf if conf in _CONFIDENCE else "low"
        response = str(r.get("response") or "").strip()
        todo = str(r.get("human_todo") or "").strip()
        req_text = str((ext or {}).get("text") or r.get("text") or "").strip()
        # The requirement's own words decide whether it is a security/compliance item, not the model's label.
        if cat != "security_compliance" and _SECURITY_ASK_RE.search(req_text):
            cat = "security_compliance"
        # Hard gates, applied to EVERY category — the model's category and markers are not trusted.
        if cat == "security_compliance":
            explicit = bool(_EXPLICIT_SECURITY_ASK_RE.search(req_text))
            if explicit and not comp["approved"]:
                # The RFP demands a specific statement/artifact in the response → a human must confirm it.
                if not response.lstrip().startswith(SECURITY_MARK):
                    response = f"{SECURITY_MARK} {response}".strip() if response else SECURITY_MARK
                basis, conf = ["needs_human"], "low"
                todo = todo or "Security team to confirm or supply what this requirement explicitly asks for."
            elif explicit and comp["approved"]:
                response, gated = _gate_compliance_prose(response) if "compliance" not in basis else (response, False)
                if gated:
                    basis, conf = ["needs_human"], "low"
            else:
                # Not an explicit ask → the standard Trust Center answer; nothing to verify.
                response, basis, conf, todo = TRUST_CENTER_ANSWER, ["standard"], "high", ""
        elif not comp["approved"]:
            response, gated = _gate_compliance_prose(response)
            if gated:
                basis, conf = ["needs_human"], "low"
                todo = todo or "Security team to confirm the compliance statement in this answer, or remove it."
        # Pricing: replace the whole answer only when price language is actually present (in the ask or the answer);
        # a "commercial" label alone is not enough — bid validity days or opening dates are not pricing.
        if _PRICING_RE.search(response) or (cat == "commercial" and _PRICING_RE.search(req_text)):
            response = f"{SALES_MARK} — pricing / commercial terms for: {req_text[:160] or 'this requirement'}"
            basis, conf = ["needs_human"], "low"
            todo = "Sales to provide pricing and commercial terms."
        elif response.lstrip().startswith(SALES_MARK) and cat != "commercial":
            # The model reached for the sales marker on a non-pricing blank (contact name, address, signature…).
            response = TEAM_MARK + response.lstrip()[len(SALES_MARK):]
            basis, conf = ["needs_human"], "low"
            todo = todo or "Team to supply this company / contact detail."
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
            "file": str((ext or {}).get("file") or r.get("file") or "").strip()[:120],
            "section": str((ext or {}).get("section") or r.get("section") or "").strip()[:80],
            "page": (ext or {}).get("page") if ext and ext.get("page") is not None else page,
            "text": req_text[:1500],
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
    exec_summary, _ = _gate_pricing_prose(exec_summary)
    win_themes = [_gate_pricing_prose(t)[0] for t in win_themes]
    assumptions = [_gate_pricing_prose(a)[0] for a in assumptions]

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


def _one_call(client: anthropic.Anthropic, lob: str, user_text: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """One drafting call (grounded when Kapa is configured). Returns (raw_json, grounding_summary)."""
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
                           f"or lower DRAFT_CHUNK_SIZE (currently {DRAFT_CHUNK_SIZE})")
    try:
        return _repair_and_parse_json(_final_text(resp)), grounding
    except (json.JSONDecodeError, IndexError, KeyError, AttributeError) as e:
        raise RuntimeError(f"Draft could not be parsed: {e}") from e


def draft_response(opp: dict[str, Any], attachment_text: str = "", lob_key: str | None = None,
                   extracted: dict[str, Any] | None = None,
                   on_progress: Any = None) -> dict[str, Any]:
    """Produce the structured draft for one opportunity. Raises anthropic.APIError on hard failure.

    `extracted` is the optional output of extraction.extract_rfp_requirements — page-cited
    requirements from Nutrient's Data Extraction API that the model must answer item by item.
    When there are more than DRAFT_CHUNK_SIZE of them, the draft is produced in chunks: the first
    call also writes the overview (summary, themes, questions…); later calls answer only their
    slice of requirements. Results are merged before normalisation.
    """
    lob = (get_lob(lob_key or opp.get("lob")) or LOBS[DEFAULT_LOB]).key
    client = _get_client()
    reqs = (extracted or {}).get("requirements") or []

    if len(reqs) <= DRAFT_CHUNK_SIZE:
        user_text = "Draft our response to this RFP.\n\n" + _rfp_text(opp, attachment_text, extracted)
        if on_progress:
            on_progress("Drafting the full response")
        raw, grounding = _one_call(client, lob, user_text)
        return _normalize(raw, lob, grounding, False, extracted)

    chunks = [reqs[i:i + DRAFT_CHUNK_SIZE] for i in range(0, len(reqs), DRAFT_CHUNK_SIZE)]
    merged: dict[str, Any] | None = None
    groundings: list[dict[str, Any]] = []
    for n, chunk in enumerate(chunks, 1):
        sub = dict(extracted); sub["requirements"] = chunk
        ids = f"{chunk[0]['id']}–{chunk[-1]['id']}"
        if n == 1:
            lead = (f"Draft our response to this RFP. This is part 1 of {len(chunks)}: write the executive summary, win themes, "
                    f"submission details, open questions, assumptions and do-not-claim list, and answer pre-extracted items {ids} "
                    f"(other items are drafted separately — do not answer them here).")
        else:
            lead = (f"This is part {n} of {len(chunks)} of our response to this RFP. Answer ONLY pre-extracted items {ids} in "
                    f"`requirements`. Leave executive_summary empty, and win_themes, open_questions, assumptions and do_not_claim "
                    f"as empty lists unless something in these items changes them.")
        if on_progress:
            on_progress(f"Drafting part {n}/{len(chunks)} ({ids})")
        raw, grounding = _one_call(client, lob, lead + "\n\n" + _rfp_text(opp, attachment_text, sub))
        if grounding:
            groundings.append(grounding)
        if merged is None:
            merged = raw
            merged["requirements"] = list(raw.get("requirements") or [])
        else:
            merged["requirements"].extend(raw.get("requirements") or [])
            for key in ("open_questions", "assumptions", "do_not_claim", "win_themes"):
                extra = [x for x in (raw.get(key) or []) if x and x not in (merged.get(key) or [])]
                if extra:
                    merged[key] = list(merged.get(key) or []) + extra
    grounding = ({"provider": "kapa", "queries": [q for g in groundings for q in g.get("queries", [])],
                  "results": sum(g.get("results", 0) for g in groundings)} if groundings else None)
    out = _normalize(merged or {}, lob, grounding, False, extracted)
    out["chunks"] = len(chunks)
    return out
