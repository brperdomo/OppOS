"""Two-stage AI qualification pipeline using Claude.

Stage 1 (router): Haiku — which Nutrient line(s) of business could address this
RFP, if any. Inclusive by design.
Stage 2 (deep score): Sonnet — evidence-backed structured scoring against the
primary LOB's positioning profile. Thin-profile LOBs are capped and limited to
investigate/skip until a vetted profile exists.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import anthropic

from oppos.config import (
    ANTHROPIC_API_KEY,
    SCORING_MODEL_STAGE1,
    SCORING_MODEL_STAGE2,
    STAGE1_FIT_THRESHOLD,
)
from oppos.scoring.lobs import DEFAULT_LOB, LOBS, LOB, get_lob
from oppos.scoring.schema import normalize_points

logger = logging.getLogger(__name__)

_client: anthropic.Anthropic | None = None

# Running token usage for this process — read by eval/cost reporting.
USAGE: dict[str, int] = {"calls": 0, "input_tokens": 0, "output_tokens": 0}

# Router candidates below this confidence are dropped.
ROUTER_MIN_CONFIDENCE = 0.3
# Secondary LOBs at or above this confidence are recorded on the result.
SECONDARY_LOB_MIN_CONFIDENCE = 0.5

_ACTIONS = {"pursue", "investigate", "monitor", "skip"}

# Full profiles produce longer assessments; a truncated JSON loses the summary and tail fields.
STAGE2_MAX_TOKENS = 3000
# A truncated, unparseable assessment is retried once (ungrounded) at this multiple of the ceiling.
STAGE2_TRUNCATION_RETRY_MULTIPLIER = 2
# Server-side MCP loops can pause more than once; give up and score ungrounded after this many continuations.
KAPA_MAX_CONTINUATIONS = 5

# Optional documentation grounding via Kapa's hosted MCP server (Messages API MCP connector).
# Set KAPA_MCP_URL (https://<subdomain>.mcp.kapa.ai) and KAPA_API_KEY to enable.
import os as _os
KAPA_MCP_URL = (_os.environ.get("KAPA_MCP_URL") or "").strip()
KAPA_API_KEY = (_os.environ.get("KAPA_API_KEY") or "").strip()
KAPA_MAX_SEARCHES = int((_os.environ.get("KAPA_MAX_SEARCHES") or "4").strip() or 4)
_MCP_BETA = "mcp-client-2025-11-20"
_KAPA_SERVER_NAME = "nutrient-docs"


def kapa_enabled() -> bool:
    return bool(KAPA_MCP_URL and KAPA_API_KEY)


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client


def _track(resp: Any) -> None:
    usage = getattr(resp, "usage", None)
    USAGE["calls"] += 1
    if usage is not None:
        USAGE["input_tokens"] += int(getattr(usage, "input_tokens", 0) or 0)
        USAGE["output_tokens"] += int(getattr(usage, "output_tokens", 0) or 0)
        USAGE["cache_read_input_tokens"] = USAGE.get("cache_read_input_tokens", 0) + int(getattr(usage, "cache_read_input_tokens", 0) or 0)
        USAGE["cache_creation_input_tokens"] = USAGE.get("cache_creation_input_tokens", 0) + int(getattr(usage, "cache_creation_input_tokens", 0) or 0)


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

def _router_system() -> str:
    lob_lines = "\n".join(f"- `{l.key}` — {l.label}: {l.router_blurb}" for l in LOBS.values())
    return f"""You are the intake router for Nutrient, a document-software company with these lines of business (LOBs):

{lob_lines}
- `none` — no Nutrient LOB could plausibly address this.

Given an RFP title, description, and metadata, decide which LOBs COULD address it. Be INCLUSIVE — we would rather route a false positive than miss a fit. List every plausible LOB with a confidence (0.0-1.0). Return `none` only for things that are clearly unrelated (construction, staffing, pure hardware, unrelated software categories such as ERP or payroll with no document component).

Also set `component_only: true` when the document-related need is a small line item inside a much larger scope (a full ERP replacement, a construction program with a "document portal" requirement, a systems-integrator bid).

Respond with ONLY valid JSON:
{{"lobs": [{{"lob": "<key>", "confidence": 0.0-1.0, "reason": "<short>"}}], "component_only": true/false, "reason": "<one sentence>"}}"""


STAGE1_SYSTEM = _router_system()

_SHARED_SCORING = """## Scoring Instructions

Analyze the RFP against the profile above and produce a structured assessment. Be specific — reference actual capabilities, customer evidence, and deployment options from the profile.

For fit_score (0-100):
- 80-100: Strong fit — matches a proven pattern, clear capability alignment
- 60-79: Good fit — mostly aligned, some gaps or unknowns
- 40-59: Possible fit — partial alignment, needs investigation
- 20-39: Weak fit — significant gaps, low win probability
- 0-19: Poor fit — wrong category entirely

## Evidence rules (strict)
- Every strength and every risk MUST carry `evidence`: a short verbatim quote (25 words or fewer) from the RFP text that supports it. If nothing in the RFP supports it directly, write exactly "inferred" — never paraphrase and present it as a quote.
- A **risk is something the RFP states** that works against us: a required certification we lack, a mandated platform or integration we do not support, a scope outside the profile, a disqualifying term. It must quote the RFP.
- Anything the RFP does **not** state goes in `knowledge_gaps`, not `risks` — "may require X", "integration with Y not confirmed", "no customer reference in this vertical", "scoring criteria unknown", "needs investigation" are all gaps. Never fill a gap with a guess, and never list a speculation as a risk.
- Procurement stage is context, not risk: an RFI, market-research notice or sources-sought is a normal entry point for us. Mention the stage in `summary`; do not list it as a risk and do not lower the score for it. Likewise never penalise a tight deadline or an unstated budget.
- Score what the RFP asks for against what the profile offers. Unknowns do not lower `fit_score`; they make the assessment less certain, which you express through `knowledge_gaps` and a lower `fit_tier` only when the gaps are material.
- Never invent certifications, customers, pricing, or capabilities that are not in the profile above. If the RFP asks for something the profile does not cover, that is a risk, not a strength.
- Never state prices, list prices, or dollar figures in your output, even if the profile mentions them — pricing is handled by sales. Describe pricing posture qualitatively (e.g. "quote-based on-prem licensing", "usage-metered cloud tier") only when it affects fit.
"""


def _stage2_system(lob: LOB) -> str:
    extras = "\n    ".join(lob.extras_schema)
    extras_block = f"    {extras}\n" if extras else ""
    thin = ""
    if lob.depth != "full":
        thin = f"""
## IMPORTANT — thin profile
The {lob.label} profile above is a description, not a vetted positioning profile. Score conservatively: cap fit_score at {lob.thin_score_cap}, use recommended_action "investigate" or "skip" only, and list what a human must verify in knowledge_gaps.
"""
    return f"""You are an expert RFP qualifier for Nutrient {lob.label}. Analyze the opportunity and score how well it fits this line of business.

{lob.profile}
{thin}
{_SHARED_SCORING}
Respond with ONLY valid JSON matching this schema:
{{
    "fit_score": <int 0-100>,
    "fit_tier": <int 1-3>,
    "lob": "{lob.key}",
    "industry": "<primary industry vertical>",
    "strengths": [{{"claim": "<specific capability match>", "evidence": "<verbatim RFP quote or 'inferred'>"}}],
    "risks": [{{"claim": "<specific gap, missing certification, or concern>", "evidence": "<verbatim RFP quote or 'inferred'>"}}],
    "knowledge_gaps": ["<what the RFP does not tell us that matters>"],
{extras_block}    "competitive_notes": "<who we might compete against, any displacement opportunity>",
    "recommended_action": "<pursue | investigate | monitor | skip>",
    "summary": "<2-3 sentence executive summary for the SDR>"
}}"""


_KAPA_GROUNDING = f"""
## Documentation grounding
You have a documentation search tool connected to Nutrient's product docs. Use it (at most {KAPA_MAX_SEARCHES} searches) when:
- the RFP requires a specific technical capability that the profile above does not clearly cover (file formats, standards such as PDF/UA or PAdES, platform/version support, API limits), or
- you are about to cite a capability as a strength and want to confirm it exists.
When a search confirms a claim, put the documentation URL in that point's `evidence` as `doc: <url>` (RFP quotes still take precedence when both exist). When the docs do not confirm it, record it as a risk or knowledge gap — never assert it. Do not search for pricing, customers, or compliance certifications; those are not in the docs.
"""

_STAGE2_SYSTEM_CACHE: dict[str, str] = {}


def stage2_system_for(lob_key: str, grounded: bool = False) -> str:
    lob = get_lob(lob_key) or LOBS[DEFAULT_LOB]
    cache_key = f"{lob.key}:{'g' if grounded else 'p'}"
    if cache_key not in _STAGE2_SYSTEM_CACHE:
        system = _stage2_system(lob)
        if grounded:
            # Insert grounding guidance before the schema so the JSON contract stays last.
            marker = "Respond with ONLY valid JSON matching this schema:"
            system = system.replace(marker, _KAPA_GROUNDING + "\n" + marker, 1)
        _STAGE2_SYSTEM_CACHE[cache_key] = system
    return _STAGE2_SYSTEM_CACHE[cache_key]


def _final_text(resp: Any) -> str:
    """Last text block of a response — MCP tool_use/tool_result blocks may precede it."""
    texts = [b.text for b in getattr(resp, "content", []) if getattr(b, "type", "") == "text" and getattr(b, "text", "")]
    if not texts:
        raise IndexError("response contained no text block")
    return texts[-1]


def _grounding_summary(resp: Any) -> dict[str, Any]:
    """What the model asked the docs — stored on the result for transparency."""
    queries: list[str] = []
    results = 0
    for b in getattr(resp, "content", []):
        btype = getattr(b, "type", "")
        if btype == "mcp_tool_use":
            inp = getattr(b, "input", {}) or {}
            q = inp.get("query") or inp.get("question") or inp.get("q") or json.dumps(inp)[:200]
            queries.append(str(q)[:200])
        elif btype == "mcp_tool_result":
            results += 1
    return {"provider": "kapa", "queries": queries, "results": results}


class _Collected:
    """All content blocks across a paused/continued MCP turn, plus the final stop reason."""

    def __init__(self, content: list[Any], stop_reason: str):
        self.content = content
        self.stop_reason = stop_reason


def _create_grounded(client: anthropic.Anthropic, system: str, user_text: str) -> _Collected | None:
    """Stage 2 with the Kapa MCP server attached.

    The server-side tool loop may return `pause_turn` repeatedly; keep continuing
    (bounded) until it stops. Returns None when the budget is exhausted or no text
    block was produced, so the caller falls back to ungrounded scoring.
    """
    messages: list[dict[str, Any]] = [{"role": "user", "content": user_text}]
    kwargs = dict(
        model=SCORING_MODEL_STAGE2,
        max_tokens=STAGE2_MAX_TOKENS + 1000,  # room for tool-use blocks
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        betas=[_MCP_BETA],
        mcp_servers=[{"type": "url", "url": KAPA_MCP_URL, "name": _KAPA_SERVER_NAME,
                      "authorization_token": KAPA_API_KEY}],
        tools=[{"type": "mcp_toolset", "mcp_server_name": _KAPA_SERVER_NAME}],
    )
    collected: list[Any] = []
    stop_reason = ""
    for _ in range(KAPA_MAX_CONTINUATIONS + 1):
        resp = client.beta.messages.create(messages=messages, **kwargs)
        _track(resp)
        collected.extend(resp.content)
        stop_reason = getattr(resp, "stop_reason", "") or ""
        if stop_reason != "pause_turn":
            break
        messages.append({"role": "assistant", "content": resp.content})
    else:
        logger.warning("Kapa grounding still paused after %d continuations — scoring ungrounded", KAPA_MAX_CONTINUATIONS)
        return None
    if not any(getattr(b, "type", "") == "text" and getattr(b, "text", "") for b in collected):
        logger.warning("Kapa-grounded response produced no text — scoring ungrounded")
        return None
    return _Collected(collected, stop_reason)


# Backward-compatible alias (Workflow was the only LOB before the router existed).
STAGE2_SYSTEM = stage2_system_for(DEFAULT_LOB)


def _extract_json(text: str) -> str:
    """Strip markdown code fences if present."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()
    return text


def _repair_and_parse_json(text: str) -> dict:
    """Try to parse JSON, repairing common LLM output issues if needed."""
    raw = _extract_json(text)

    # First try: direct parse
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Repair: replace literal newlines inside string values with \\n
    import re
    repaired = re.sub(
        r'(?<=": ")(.*?)(?="[,\s\n]*["}])',
        lambda m: m.group(0).replace("\n", "\\n").replace("\t", "\\t"),
        raw,
        flags=re.DOTALL,
    )
    try:
        return json.loads(repaired)
    except json.JSONDecodeError:
        pass

    # Repair: truncate at last complete key-value pair and close the object
    # Find the last valid "key": value pattern followed by a comma or brace
    last_good = raw.rfind('",')
    if last_good > 0:
        truncated = raw[:last_good + 1] + "}"
        # Balance any unclosed arrays
        open_brackets = truncated.count("[") - truncated.count("]")
        truncated = truncated[:-1] + ("]" * open_brackets) + "}"
        try:
            return json.loads(truncated)
        except json.JSONDecodeError:
            pass

    # Give up — raise so caller hits the fallback
    raise json.JSONDecodeError("Could not repair JSON", raw, 0)


def _build_opportunity_text(opp: dict[str, Any], attachment_text: str = "") -> str:
    parts = [
        f"Title: {opp.get('title', 'N/A')}",
        f"Agency: {opp.get('agency', 'N/A')}",
        f"Notice Type: {opp.get('notice_type', 'N/A')}",
        f"NAICS: {opp.get('naics_code', 'N/A')}",
        f"Set-Aside: {opp.get('set_aside', 'N/A')}",
        f"Classification Code: {opp.get('classification_code', 'N/A')}",
        f"Place of Performance: {opp.get('place_of_performance', 'N/A')}",
        f"Response Deadline: {opp.get('response_deadline', 'N/A')}",
        f"URL: {opp.get('url', 'N/A')}",
    ]
    desc = opp.get("description", "")
    if desc:
        parts.append(f"\nDescription:\n{desc[:8000]}")
    if attachment_text:
        parts.append(f"\n--- RFP ATTACHMENT CONTENT (extracted via OCR) ---\n{attachment_text}")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Stage 1 — LOB router
# ---------------------------------------------------------------------------

def _router_fallback(reason: str) -> dict[str, Any]:
    """On any failure, stay inclusive: route to the default LOB at low confidence."""
    return {
        "relevant": True,
        "confidence": 0.5,
        "reason": reason,
        "lobs": [{"lob": DEFAULT_LOB, "confidence": 0.5, "reason": "fallback"}],
        "component_only": False,
    }


def _normalize_router(raw: dict[str, Any]) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    none_conf: float | None = None
    for item in raw.get("lobs") or []:
        if not isinstance(item, dict):
            continue
        key = str(item.get("lob", "")).strip().lower()
        try:
            conf = float(item.get("confidence", 0) or 0)
        except (TypeError, ValueError):
            conf = 0.0
        conf = max(0.0, min(1.0, conf))
        if key == "none":
            none_conf = conf
        elif key in LOBS and conf >= ROUTER_MIN_CONFIDENCE:
            candidates.append({"lob": key, "confidence": round(conf, 2), "reason": str(item.get("reason", ""))[:200]})
    candidates.sort(key=lambda c: -c["confidence"])
    relevant = bool(candidates)
    if relevant:
        confidence = candidates[0]["confidence"]
    else:
        confidence = none_conf if none_conf is not None else 0.8
    return {
        "relevant": relevant,
        "confidence": confidence,
        "reason": str(raw.get("reason", ""))[:300],
        "lobs": candidates,
        "component_only": bool(raw.get("component_only", False)),
    }


def stage1_filter(opportunity: dict[str, Any], attachment_text: str = "") -> dict[str, Any]:
    """Route to LOB(s). Returns {"relevant", "confidence", "reason", "lobs": [...], "component_only"}.

    `relevant` is True when at least one LOB is a plausible candidate; `confidence`
    is the top candidate's confidence (or the confidence in `none` when rejected).
    """
    client = _get_client()
    opp_text = _build_opportunity_text(opportunity, attachment_text)

    try:
        resp = client.messages.create(
            model=SCORING_MODEL_STAGE1,
            max_tokens=400,
            system=[{"type": "text", "text": STAGE1_SYSTEM, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": opp_text}],
        )
        _track(resp)
        raw = _repair_and_parse_json(resp.content[0].text)
        return _normalize_router(raw)
    except (json.JSONDecodeError, IndexError, KeyError, AttributeError) as e:
        logger.warning("Stage 1 parse error for '%s': %s", opportunity.get("title", "?"), e)
        return _router_fallback(f"Parse error — defaulting to {DEFAULT_LOB}: {e}")
    except anthropic.APIError as e:
        logger.error("Stage 1 API error: %s", e)
        return _router_fallback(f"API error — defaulting to {DEFAULT_LOB}: {e}")


# ---------------------------------------------------------------------------
# Stage 2 — per-LOB deep score
# ---------------------------------------------------------------------------

def _tier_for(score: int) -> int:
    return 1 if score >= 80 else 2 if score >= 60 else 3


# Risks written in these terms are speculation about what the RFP does not say — they belong in
# knowledge_gaps, however the model labelled them. A claim *about* the procurement stage ("this is
# only an RFI", "market research phase, no award") is context, never a risk — but a requirement an
# RFI states ("the RFI mandates an Oracle Forms integration") is still a risk when quoted.
_SPECULATIVE_RISK_RE = re.compile(
    r"\bnot (confirmed|stated|specified|named|yet)\b|\b(is|are|remains?|still|currently) unknown\b|\bunknown (whether|if|at this (time|stage|point))\b"
    r"|\bunclear\b|\bneeds? (investigation|verification|confirmation)\b"
    r"|\bno (direct|named|known|existing)?\s*(customer|parole|public[- ]sector|vertical)?\s*reference\b"
    r"|\bnot a (named|proven|listed) (vertical|pattern|industry)\b"
    r"|\b(this|it) is (only |just |merely )?(an? |the )?(rfi|request for information|market research|sources[- ]sought|pre[- ]solicitation)\b"
    r"|\b(only|just|merely) (an? |the )?(rfi|request for information|market research|sources[- ]sought|pre[- ]solicitation)\b"
    r"|\b(rfi|request for information|market research|sources[- ]sought|pre[- ]solicitation)\b.{0,60}"
    r"\b(rather than|not (a|an) (solicitation|rfp|procurement|bid|commitment)|no (award|contract|guarantee|formal|obligation)|not yet"
    r"|may not (result|lead)|will not result|stage|phase|informational?|planning purposes|budgetary|does not (commit|obligate|constitute|guarantee))\b"
    r"|\bcannot be (confirmed|verified|determined)\b",
    re.I,
)
# A tight deadline is never a risk (scoring rule); the model occasionally writes one anyway.
_DEADLINE_RISK_RE = re.compile(
    r"\b(deadline|due date|response (window|period|time|timeline)|turnaround|time ?frame|timeline|submission window|days? (to|until) (respond|submit|the deadline))\b"
    r".{0,80}\b(tight|short|compressed|aggressive|limited|insufficient|little time|only \d+ (business |calendar )?days|\d+ (business |calendar )?days (away|out|remaining|left)|constrain|pressure|risk)"
    r"|\b(tight|short|compressed|aggressive|limited) (response |submission )?(deadline|window|timeline|time ?frame|turnaround)\b"
    r"|\b\d+ (business |calendar )?days? to (respond|submit|prepare)\b"
    r"|\b(only )?\d+ (business |calendar )?days? (remain|remaining|left|until|before|away)\b.{0,40}\b(deadline|due|respond|submit|response|submission|proposal|bid)\b"
    r"|\b(deadline|due date|due|respond|submit|response|submission|proposal)\b.{0,60}\b(only )?\d+ (business |calendar )?days? (remain|remaining|left)\b"
    r"|\b(deadline|due date|due|respond|submit|response|submission|proposal)\b.{0,60}\bonly \d+ (business |calendar )?days\b",
    re.I,
)
# Conditional wording is speculation when the model wrote it, but a stated condition the RFP
# itself spells out ("cloud hosting would require FedRAMP High") is a real requirement — such a
# claim is kept when its evidence quotes the condition.
_CONDITIONAL_RISK_RE = re.compile(
    r"\b(may|might|could|likely|possibly|potentially|probably)\s+(require|need|involve|include|expect|be)\b"
    r"|\bif (the|a|an|this|any|future)\b.*\b(require|mandate|demand|need)"
    r"|\bwould (need|require)\b",
    re.I,
)


def _norm_text(t: str) -> str:
    """Lower-case token text. Keeps the symbols that distinguish technology names (C++, C#, .NET,
    v8.21) while dropping sentence punctuation, so "C++" cannot match "C#" or "C"."""
    t = (t or "").lower()
    t = re.sub(r"\.(?=\s|$)", " ", t)          # sentence-ending periods are punctuation, not part of a token
    t = re.sub(r"[^a-z0-9+#.]+", " ", t)        # keep + # . inside tokens
    return re.sub(r"\s+", " ", t).strip()


_ELLIPSIS_RE = re.compile(r"\.{3}|…|\[\s*\.{3}\s*\]|\[…\]")
_MIN_SEGMENT_WORDS = 3


def evidence_in_text(evidence: str, corpus: str) -> bool:
    """True when the COMPLETE quote genuinely occurs in the RFP text.

    Matching is case/punctuation/whitespace-insensitive. A quote may use an ellipsis to skip
    words ("intake ... audit trails"); then every segment (≥ 3 words each) must occur in the
    corpus, in order. No partial-fragment credit: six matching words do not make an invented
    tail acceptable.
    """
    # Token-sequence containment: pad with spaces so "ai" cannot match inside "training",
    # "net" inside "internet", or "c" (from "C++") inside anything.
    corpus_n = f" {_norm_text(corpus)} "
    if not corpus_n.strip():
        return False
    segments = [f" {_norm_text(seg)} " for seg in _ELLIPSIS_RE.split(evidence or "") if _norm_text(seg)]
    if not segments:
        return False
    if len(segments) == 1:
        return segments[0] in corpus_n
    pos = 0
    for seg in segments:
        if len(seg.split()) < _MIN_SEGMENT_WORDS:
            return False
        found = corpus_n.find(seg, pos)
        if found < 0:
            return False
        pos = found + len(seg) - 1  # segments may share the boundary space
    return True


# Metadata our own prompt builder writes: a title proves the topic, a URL often carries the title as a
# slug, an agency name proves who is buying and a deadline value proves when — none states a requirement.
_NON_EVIDENCE_LINES = ("title:", "url:", "agency:", "response deadline:")
# Values _build_opportunity_text writes when a field is missing; they are ours, not the RFP's.
_PLACEHOLDER_VALUES = {"n/a", "na", "none", "null", "tbd", "unknown", "not specified", "not stated", "not provided", ""}
_METADATA_LINE_RE = re.compile(r"^(agency|notice type|naics|set-aside|classification code|place of performance|response deadline):\s*(.*)$", re.I)


def _body_without_title(corpus: str) -> str:
    """The opportunity text minus the Title / URL / Agency / Response Deadline lines and any
    placeholder-valued metadata line — see _NON_EVIDENCE_LINES. The same words still ground a
    risk when they occur in the description or attachments.
    """
    kept = []
    for line in (corpus or "").splitlines():
        low = line.strip().lower()
        if low.startswith(_NON_EVIDENCE_LINES):
            continue
        m = _METADATA_LINE_RE.match(line.strip())
        if m and m.group(2).strip().lower() in _PLACEHOLDER_VALUES:
            continue
        kept.append(line)
    return "\n".join(kept)


def _ground_risks(risks: list[dict[str, str]], gaps: list[str], title: str = "",
                  corpus: str | None = None) -> tuple[list[dict[str, str]], list[str]]:
    """Keep only risks the RFP actually states; demote the rest to knowledge gaps.

    A risk is ungrounded when it has no evidence, says "inferred", only quotes the
    opportunity title/agency (a title proves the topic, not a requirement), or — when the
    RFP text is available — quotes something that does not occur in that text.
    """
    kept: list[dict[str, str]] = []
    demoted: list[str] = []
    title_n = _norm_text(title)
    body = _body_without_title(corpus) if corpus is not None else None
    for r in risks:
        claim, ev = r.get("claim", ""), (r.get("evidence") or "").strip()
        ev_n = _norm_text(ev)
        ungrounded = (not ev) or ev.lower() == "inferred" or ev_n in _PLACEHOLDER_VALUES
        if not ungrounded:
            if body is not None:
                # With the RFP text available, the quote must occur in the body (not merely in the title).
                ungrounded = not evidence_in_text(ev, body)
            elif title_n and (ev_n == title_n or ev_n in title_n):
                ungrounded = True  # no text to check against: a title-only quote proves nothing
        speculative = bool(_SPECULATIVE_RISK_RE.search(claim)) or bool(_DEADLINE_RISK_RE.search(claim))
        if not speculative and _CONDITIONAL_RISK_RE.search(claim):
            # Model-written condition → speculation; RFP-quoted condition → stated requirement.
            speculative = not _CONDITIONAL_RISK_RE.search(ev)
        if ungrounded or speculative:
            gap = claim.rstrip(".")
            if gap and gap not in demoted:
                demoted.append(gap)  # a copy already in gaps is dropped below so it joins the protected prefix
        else:
            kept.append(r)
    # Demoted claims lead the list so a cap on knowledge gaps can never silently drop them.
    return kept, demoted + [g for g in gaps if g not in demoted]


MAX_GAPS = 12


def cap_gaps(gaps: list[str], n_demoted: int) -> list[str]:
    """Cap knowledge gaps at MAX_GAPS without ever cutting the demoted risks at the front."""
    return gaps[:max(MAX_GAPS, n_demoted)]


def _normalize_stage2(result: dict[str, Any], lob: LOB, title: str = "", corpus: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = dict(lob.extras_defaults)
    out.update(result or {})
    out["lob"] = lob.key
    out["strengths"] = normalize_points(out.get("strengths"))
    gaps_raw = out.get("knowledge_gaps") or []
    gaps = [str(g).strip()[:200] for g in gaps_raw if str(g).strip()] if isinstance(gaps_raw, list) else []
    risks_in = normalize_points(out.get("risks"))
    out["risks"], gaps = _ground_risks(risks_in, gaps, title=title, corpus=corpus)
    out["knowledge_gaps"] = cap_gaps(gaps, len(risks_in) - len(out["risks"]))

    try:
        score = int(round(float(out.get("fit_score", 0) or 0)))
    except (TypeError, ValueError):
        score = 0
    score = max(0, min(100, score))

    action = str(out.get("recommended_action", "investigate") or "investigate").strip().lower()
    if action not in _ACTIONS:
        action = "investigate"

    if lob.depth != "full":
        score = min(score, lob.thin_score_cap)
        if action == "pursue":
            action = "investigate"

    out["fit_score"] = score
    out["recommended_action"] = action
    out["profile_depth"] = lob.depth
    out["fit_tier"] = _tier_for(score)  # always from the final score — the thin cap may have lowered it
    out["summary"] = str(out.get("summary", "") or "")
    out["industry"] = str(out.get("industry", "") or "")
    out["competitive_notes"] = str(out.get("competitive_notes", "") or "")
    return out


def _stage2_failure(lob: LOB, message: str) -> dict[str, Any]:
    out: dict[str, Any] = dict(lob.extras_defaults)
    out.update({
        "fit_score": 0,
        "fit_tier": 3,
        "lob": lob.key,
        "industry": "",
        "strengths": [],
        "risks": [],  # a diagnostic is not an RFP risk — the grounding invariant holds for failures too
        "knowledge_gaps": ["Scoring failed — manual review needed"],
        "competitive_notes": "",
        "recommended_action": "investigate",
        "summary": message,
        "profile_depth": lob.depth,
    })
    return out


def stage2_score(
    opportunity: dict[str, Any],
    attachment_text: str = "",
    lob_key: str | None = None,
) -> dict[str, Any]:
    """Deep qualification scoring against one LOB's profile. Returns the structured assessment."""
    lob = get_lob(lob_key or opportunity.get("lob")) or LOBS[DEFAULT_LOB]
    client = _get_client()
    opp_text = _build_opportunity_text(opportunity, attachment_text)

    user_text = f"Score this RFP opportunity:\n\n{opp_text}"
    title = opportunity.get("title", "?")
    try:
        grounding: dict[str, Any] | None = None
        resp: Any = None
        if kapa_enabled():
            try:
                resp = _create_grounded(client, stage2_system_for(lob.key, grounded=True), user_text)
            except anthropic.APIError as e:
                # Grounding is an enhancement — fall back to the plain scorer rather than fail the opp.
                logger.warning("Kapa-grounded scoring failed (%s); retrying without grounding", e)
                resp = None
            if resp is not None:
                grounding = _grounding_summary(resp)

        max_tokens = STAGE2_MAX_TOKENS
        for attempt in range(2):
            if resp is None:
                resp = client.messages.create(
                    model=SCORING_MODEL_STAGE2,
                    max_tokens=max_tokens,
                    system=[{"type": "text", "text": stage2_system_for(lob.key), "cache_control": {"type": "ephemeral"}}],
                    messages=[{"role": "user", "content": user_text}],
                )
                _track(resp)
            # Decide truncation BEFORE parsing — a cutoff inside a nested value is often unrepairable.
            truncated = getattr(resp, "stop_reason", "") == "max_tokens"
            try:
                result = _repair_and_parse_json(_final_text(resp))
            except (json.JSONDecodeError, IndexError, KeyError, AttributeError) as e:
                if truncated and attempt == 0:
                    max_tokens = STAGE2_MAX_TOKENS * STAGE2_TRUNCATION_RETRY_MULTIPLIER
                    logger.warning("Stage 2 output for '%s' truncated and unparseable — retrying at %d tokens", title, max_tokens)
                    resp, grounding = None, None  # retry ungrounded with more room
                    continue
                if truncated:
                    out = _stage2_failure(lob, f"Assessment truncated at {max_tokens} output tokens and could not be parsed "
                                               f"— raise STAGE2_MAX_TOKENS or shorten the profile: {e}")
                    out["truncated"] = True
                    return out
                raise
            out = _normalize_stage2(result, lob, title=str(opportunity.get("title") or ""), corpus=opp_text)
            if truncated:
                logger.warning("Stage 2 output truncated at %d tokens for '%s' — raise STAGE2_MAX_TOKENS", max_tokens, title)
                out["truncated"] = True
                if not out.get("summary"):
                    out["summary"] = "(assessment truncated — summary unavailable; see strengths and risks)"
            if grounding:
                out["grounding"] = grounding
            return out
        raise RuntimeError("unreachable")  # loop always returns or raises
    except (json.JSONDecodeError, IndexError, KeyError, AttributeError) as e:
        logger.warning("Stage 2 parse error for '%s': %s", opportunity.get("title", "?"), e)
        return _stage2_failure(lob, f"Automated scoring failed: {e}")
    except anthropic.APIError as e:
        logger.error("Stage 2 API error: %s", e)
        return _stage2_failure(lob, f"Automated scoring failed: {e}")


def _primary_lob(opportunity: dict[str, Any], lob_key: str | None = None) -> str:
    if lob_key and get_lob(lob_key):
        return get_lob(lob_key).key
    if get_lob(opportunity.get("lob")):
        return get_lob(opportunity.get("lob")).key
    s1 = opportunity.get("stage1") or {}
    if isinstance(s1, dict) and s1.get("lobs"):
        return s1["lobs"][0]["lob"]
    return DEFAULT_LOB


def _attach_stage2(opportunity: dict[str, Any], s2: dict[str, Any]) -> None:
    s1 = opportunity.get("stage1") or {}
    if isinstance(s1, dict):
        secondary = [
            c["lob"] for c in (s1.get("lobs") or [])[1:]
            if c.get("confidence", 0) >= SECONDARY_LOB_MIN_CONFIDENCE and c.get("lob") != s2.get("lob")
        ]
        if secondary:
            s2["secondary_lobs"] = secondary
        if s1.get("component_only"):
            s2["component_only"] = True
    opportunity["stage2"] = s2
    opportunity["lob"] = s2.get("lob", DEFAULT_LOB)
    opportunity["fit_score"] = s2.get("fit_score", 0)
    opportunity["recommended_action"] = s2.get("recommended_action", "investigate")


def force_score(
    opportunity: dict[str, Any],
    attachment_text: str = "",
    lob_key: str | None = None,
) -> dict[str, Any]:
    """Skip Stage 1 and go straight to deep scoring.

    Use when Stage 1 incorrectly filtered out a relevant opportunity, or to
    re-score an opportunity against a specific LOB.
    """
    lob = _primary_lob(opportunity, lob_key)
    s2 = stage2_score(opportunity, attachment_text, lob_key=lob)
    opportunity["stage1"] = {
        "relevant": True,
        "confidence": 1.0,
        "reason": "Force-scored — Stage 1 bypassed",
        "lobs": [{"lob": lob, "confidence": 1.0, "reason": "forced"}],
        "component_only": False,
    }
    _attach_stage2(opportunity, s2)
    logger.info(
        "Force-scored [%s]: '%s' — %d/100 (%s)",
        lob, opportunity.get("title", "?"), opportunity["fit_score"], opportunity["recommended_action"],
    )
    return opportunity


def qualify(opportunity: dict[str, Any], attachment_text: str = "") -> dict[str, Any]:
    """Run the full two-stage pipeline. Returns the opportunity enriched with scoring."""
    s1 = stage1_filter(opportunity, attachment_text)
    opportunity["stage1"] = s1

    if not s1["relevant"] and s1["confidence"] > STAGE1_FIT_THRESHOLD:
        opportunity["stage2"] = None
        opportunity["lob"] = None
        opportunity["fit_score"] = 0
        opportunity["recommended_action"] = "skip"
        logger.info("Filtered out: '%s' — %s", opportunity.get("title", "?"), s1["reason"])
        return opportunity

    primary = s1["lobs"][0]["lob"] if s1["lobs"] else DEFAULT_LOB
    s2 = stage2_score(opportunity, attachment_text, lob_key=primary)
    _attach_stage2(opportunity, s2)

    logger.info(
        "Scored [%s]: '%s' — %d/100 (%s)",
        opportunity["lob"], opportunity.get("title", "?"), opportunity["fit_score"], opportunity["recommended_action"],
    )
    return opportunity
