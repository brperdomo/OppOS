"""Response document — lay a draft into the team's submitted-response skeleton as Markdown.

The skeleton mirrors the responses we have actually submitted: a title that names the buyer and
solicitation, an executive summary, requirement-by-requirement answers grouped under the RFP's
own section numbering, reusable delivery boilerplate (team, methodology, past experience), a
requirements matrix (Appendix A), the security evidence package (Appendix B), and a clearly
marked internal-notes appendix to strip before submission.

The Markdown is the hand-off format: the dashboard imports it into the Nutrient Document
Authoring SDK (in-browser editor, DOCX / PDF export) and `scripts/export_response.mjs` does the
same headless. Review markers ([SECURITY TO CONFIRM], [SALES TO PROVIDE], [TEAM TO PROVIDE],
[NOT DRAFTED]) are kept verbatim so they are visible in the Word document.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any

from oppos.drafting.drafter import NOT_DRAFTED_MARK, SALES_MARK, SECURITY_MARK, TEAM_MARK, TRUST_CENTER_URL
from oppos.scoring.lobs import DEFAULT_LOB, LOBS, get_lob
from oppos.scoring.lobs.base import _FRONTMATTER_RE
from oppos.scoring.schema import lob_label

BOILERPLATE_DIR = Path(__file__).resolve().parent / "boilerplate"
# Boilerplate sections in the order they appear in the document; the LOB file may add or override.
_BOILERPLATE_ORDER = ("Project team", "Implementation methodology", "Past relevant experience")
_EVIDENCE_SECTION = "Security and compliance evidence package"
_UNGROUPED = "Requirements and questions"


# ---------------------------------------------------------------------------
# Boilerplate library
# ---------------------------------------------------------------------------

def _sections(md_path: Path) -> dict[str, str]:
    """{heading: body} for every `## ` section in a boilerplate file (frontmatter dropped)."""
    if not md_path.is_file():
        return {}
    text = md_path.read_text(encoding="utf-8")
    m = _FRONTMATTER_RE.match(text)
    if m:
        text = text[m.end():]
    out: dict[str, str] = {}
    current: str | None = None
    buf: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            if current:
                out[current] = "\n".join(buf).strip()
            current, buf = line[3:].strip(), []
        elif current:
            buf.append(line)
    if current:
        out[current] = "\n".join(buf).strip()
    return out


def boilerplate(lob_key: str) -> dict[str, str]:
    """Common sections overlaid with the LOB's own (e.g. Workflow case studies)."""
    out = _sections(BOILERPLATE_DIR / "common.md")
    out.update(_sections(BOILERPLATE_DIR / f"{lob_key}.md"))
    return out


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_UNKNOWN = {"", "unknown", "n/a", "none", "null", "tbd", "not specified"}


def _known(value: Any) -> str:
    """The value unless it is the drafter's 'unknown' sentinel (or similar), so callers can fall back."""
    s = str(value or "").strip()
    return "" if s.lower() in _UNKNOWN else s


def _cell(text: Any, limit: int = 220) -> str:
    s = re.sub(r"\s+", " ", str(text or "")).strip().replace("|", "\\|")
    return s if len(s) <= limit else s[: limit - 1].rstrip() + "…"


def status_of(req: dict[str, Any]) -> str:
    """Review status of one drafted requirement, from its markers and basis."""
    resp = str(req.get("response") or "").lstrip()
    if resp.startswith(SECURITY_MARK):
        return "Security to confirm"
    if resp.startswith(SALES_MARK):
        return "Sales to provide"
    if resp.startswith(TEAM_MARK):
        return "Team to provide"
    if resp.startswith(NOT_DRAFTED_MARK):
        return "Not drafted"
    if "needs_human" in (req.get("basis") or []):
        return "Needs review"
    return "Drafted"


def _grouped(reqs: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    """Group requirements by their RFP section, keeping first-appearance order; unsectioned items last."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for r in reqs:
        sec = str(r.get("section") or "").strip() or _UNGROUPED
        groups.setdefault(sec, []).append(r)
    ordered = [(k, v) for k, v in groups.items() if k != _UNGROUPED]
    if _UNGROUPED in groups:
        ordered.append((_UNGROUPED, groups[_UNGROUPED]))
    return ordered


def _cite(r: dict[str, Any]) -> str:
    bits = []
    if r.get("file"):
        bits.append(str(r["file"]))
    if r.get("page"):
        bits.append(f"p. {r['page']}")
    return " · ".join(bits)


def file_stem(opp: dict[str, Any]) -> str:
    """`Nutrient-response-<agency-or-title>` as a safe file name stem."""
    base = str(opp.get("agency") or opp.get("title") or opp.get("source_id") or "rfp")
    slug = re.sub(r"[^A-Za-z0-9]+", "-", base).strip("-")[:60] or "rfp"
    return f"Nutrient-response-{slug}"


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

def render_markdown(draft: dict[str, Any], opp: dict[str, Any], author: str = "", today: date | None = None) -> str:
    """The full response document for `draft` in the team's skeleton, as Markdown."""
    today = today or date.today()
    lob = get_lob(str(draft.get("lob") or opp.get("lob") or DEFAULT_LOB)) or LOBS[DEFAULT_LOB]
    lob_name = lob_label(lob.key)
    agency = str(opp.get("agency") or "").strip()
    title = str(opp.get("title") or "").strip()
    sol = str(opp.get("solicitation_number") or "").strip()
    buyer = agency or title or "the issuing organisation"
    subject = " — ".join(x for x in (sol, title) if x) or "the solicitation"
    reqs: list[dict[str, Any]] = list(draft.get("requirements") or [])
    sub = draft.get("submission") or {}
    bp = boilerplate(lob.key)
    out: list[str] = []
    w = out.append

    w(f"# Response to {buyer} — {subject} – Nutrient")
    w("")
    w(f"*Prepared for {buyer} · {lob_name} · draft of {today.isoformat()}*")
    w("")

    # Executive summary + win themes
    w("## Executive summary")
    w("")
    w(str(draft.get("executive_summary") or "[TEAM TO PROVIDE] — executive summary.").strip())
    themes = [t for t in (draft.get("win_themes") or []) if t]
    if themes:
        w("")
        w("**Why Nutrient**")
        w("")
        for t in themes:
            w(f"- {t}")
    w("")

    # Submission details
    w("## Submission details")
    w("")
    w(f"- **Method:** {_known(sub.get('method')) or opp.get('submission_method') or 'unknown'}")
    w(f"- **Deadline:** {_known(sub.get('deadline')) or opp.get('response_deadline') or 'unknown'}")
    for f in sub.get("format_requirements") or []:
        if draft.get("required_forms") and str(f).startswith("Required form/attachment:"):
            continue  # listed once, below
        w(f"- {f}")
    if draft.get("required_forms"):
        w(f"- **Required forms / attachments:** {'; '.join(draft['required_forms'])}")
    if draft.get("evaluation_criteria"):
        crit = "; ".join(f"{c.get('criterion')}" + (f" ({c['weight']})" if c.get("weight") else "") for c in draft["evaluation_criteria"])
        w(f"- **Evaluation criteria:** {crit}")
    w("")

    # Requirement-by-requirement responses, under the RFP's own sections
    w("## Responses to the solicitation")
    w("")
    if not reqs:
        w("[NOT DRAFTED] — no requirements were drafted.")
        w("")
    for section, items in _grouped(reqs):
        w(f"### {section}")
        w("")
        for r in items:
            head = f"**{r.get('id', '')}** — {str(r.get('text') or '').strip()}"
            cite = _cite(r)
            w(head + (f" *({cite})*" if cite else ""))
            w("")
            w(str(r.get("response") or NOT_DRAFTED_MARK).strip())
            if r.get("human_todo"):
                w("")
                w(f"> ✎ {r['human_todo']}")
            w("")

    # Delivery boilerplate
    for heading in _BOILERPLATE_ORDER:
        w(f"## {heading}")
        w("")
        w(bp.get(heading) or f"{TEAM_MARK} — {heading.lower()} for {lob_name}.")
        w("")

    # Appendix A — requirements matrix
    w("## Appendix A: Requirements matrix")
    w("")
    w("| Req # | Requirement | Category | Status | Response (summary) |")
    w("|---|---|---|---|---|")
    for r in reqs:
        w(f"| {_cell(r.get('id'))} | {_cell(r.get('text'), 160)} | {_cell(str(r.get('category') or '').replace('_', ' '))} "
          f"| {status_of(r)} | {_cell(r.get('response'), 200)} |")
    w("")

    # Appendix B — security evidence package (standard Trust Center position)
    w(f"## Appendix B: {_EVIDENCE_SECTION}")
    w("")
    w(bp.get(_EVIDENCE_SECTION) or f"Security and compliance documentation is available under NDA via the Nutrient Trust Center ({TRUST_CENTER_URL}).")
    w("")

    # Appendix C — internal
    w("## Appendix C: Internal review notes — REMOVE BEFORE SUBMISSION")
    w("")
    stats = draft.get("stats") or {}
    counts: dict[str, int] = {}
    for r in reqs:
        counts[status_of(r)] = counts.get(status_of(r), 0) + 1
    w(f"- Draft generated {str(draft.get('generated_at') or '')[:16].replace('T', ' ')} UTC with {draft.get('model', '')}"
      + (f" in {draft['chunks']} parts" if draft.get("chunks") else "") + ".")
    if counts:
        w("- Status: " + ", ".join(f"{n} {k.lower()}" for k, n in sorted(counts.items(), key=lambda kv: -kv[1])) + ".")
    ex = draft.get("extraction") or {}
    if ex.get("files"):
        w(f"- Requirements extracted with the Nutrient Data Extraction API ({ex.get('mode')}) from {ex.get('pages')} pages across "
          f"{len(ex['files'])} file(s); {ex.get('credits_cost')} credits.")
    comp = draft.get("compliance_source") or {}
    w("- Security items use the Trust Center standard answer; explicit asks are "
      + ("validated against the approved compliance file." if comp.get("approved") else "marked [SECURITY TO CONFIRM] until the compliance file is approved."))
    for label, key in (("Open questions for Q&A", "open_questions"), ("Assumptions", "assumptions"), ("Do not claim", "do_not_claim")):
        items = [x for x in (draft.get(key) or []) if x]
        if items:
            w("")
            w(f"**{label}**")
            w("")
            for x in items:
                w(f"- {x}")
    w("")
    w("---")
    w("")
    who = f"Prepared by {author}. " if author else ""
    w(f"{who}Information is accurate to the best of our knowledge as of {today.strftime('%m/%d/%Y')}.")
    w("")
    return "\n".join(out)
