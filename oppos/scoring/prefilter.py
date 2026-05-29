"""Rules-based pre-filter to reject obviously non-software RFPs.

Runs BEFORE the AI qualifier — zero API cost, instant.

Design principles:
  • Only reject when BOTH title AND description clearly indicate non-software work.
  • Sparse/empty descriptions always pass — attachments may contain the real scope.
  • Software + services (training, support, staffing augmentation alongside software)
    are allowed through — Stage 1 / Stage 2 will score them appropriately.
  • NAICS codes in the 5112xx range (software) always pass regardless of keywords.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Minimum text length to even attempt filtering.
# Anything shorter passes automatically — might have details in attachments.
# ---------------------------------------------------------------------------
_MIN_TEXT_LENGTH = 40

# ---------------------------------------------------------------------------
# NAICS codes that are ALWAYS relevant (software / IT)
# ---------------------------------------------------------------------------
_SOFTWARE_NAICS_PREFIXES = (
    "5112",   # Software publishers
    "5415",   # Computer systems design
    "518",    # Data processing, hosting
    "5191",   # Other information services
    "541512", # Computer systems design
    "541511", # Custom programming
    "541513", # Computer facilities management
    "541519", # Other computer related
    "334",    # Computer & electronic products
    "5182",   # Data processing & hosting
)

# NAICS codes that are NEVER relevant (physical / labor / unrelated)
_REJECT_NAICS_PREFIXES = (
    "236",    # Construction of buildings
    "237",    # Heavy / civil engineering construction
    "238",    # Specialty trade contractors
    "484",    # Truck transportation
    "485",    # Transit / ground passenger
    "488",    # Support for transportation
    "561720", # Janitorial services
    "561710", # Exterminating / pest control
    "561730", # Landscaping
    "561790", # Other services to buildings
    "562",    # Waste management
    "722",    # Food services
    "621",    # Ambulatory health (medical staffing)
    "811",    # Repair & maintenance
    "812",    # Personal / laundry services
    "112",    # Animal production
    "111",    # Crop production
    "113",    # Forestry / logging
    "114",    # Fishing / hunting
    "212",    # Mining
    "213",    # Mining support
    "321",    # Wood product mfg
    "327",    # Nonmetallic mineral mfg
    "331",    # Primary metal mfg
    "332",    # Fabricated metal mfg
    "333",    # Machinery mfg
    "336",    # Transportation equipment mfg
    "482",    # Rail transportation
    "483",    # Water transportation
)

# ---------------------------------------------------------------------------
# Keyword patterns — case-insensitive word-boundary matching
# ---------------------------------------------------------------------------

# If title+desc match ANY of these AND NONE of the software signals → reject.
# These must be strong, unambiguous signals of non-software work.
_REJECT_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE) for p in [
        # Physical services
        r"\bjanitorial\b",
        r"\bcustodial\s+service",
        r"\bjanitor\b",
        r"\bcleaning\s+service",
        r"\bfloor\s+(care|cleaning|waxing|stripping)",
        r"\blandscaping\b",
        r"\blawn\s+(care|maint)",
        r"\bsnow\s+removal\b",
        r"\bpest\s+control\b",
        r"\bexterminat",
        r"\bwaste\s+(removal|hauling|disposal|collection)",
        r"\bgarbage\b",
        r"\btrash\s+(removal|collection|pickup)",
        r"\bdumpster\b",
        r"\brefuse\s+collection\b",
        # Construction / trades
        r"\broof(ing)?\s+(repair|replacement|install)",
        r"\bpaving\b",
        r"\basphalt\b",
        r"\bconcrete\s+(repair|pour|work|install)",
        r"\bdemolition\b",
        r"\bexcavation\b",
        r"\bplumbing\s+(repair|service|install)",
        r"\belectrical\s+(repair|service|install|wiring|contractor)",
        r"\bhvac\s+(repair|service|install|maint|replace)",
        r"\belevator\s+(repair|service|maint|modern|inspect)",
        r"\bpainting\s+(service|contract|interior|exterior)",
        r"\bcarpentry\b",
        r"\bwelding\b",
        r"\bflooring\s+(install|replace)",
        r"\bfence\s+(install|repair|replace)",
        r"\bbridge\s+(repair|construct|replace)",
        r"\broad\s+(repair|construct|pav|resurfac|maint)",
        r"\bsidewalk\s+(repair|replace|construct)",
        r"\bwater\s+(main|line|pipe)\s+(repair|replace)",
        r"\bsewer\s+(repair|replace|line|main)",
        # Food / catering
        r"\bcatering\s+service",
        r"\bfood\s+service\b",
        r"\bmeal\s+(prep|delivery|service)",
        r"\bvending\s+machine",
        r"\bcafeteria\s+(operat|manag|service)",
        # Vehicles / fleet (physical)
        r"\bvehicle\s+(repair|maint|fleet|body\s+shop)",
        r"\btire\s+(repair|replace|service)",
        r"\btowing\s+service",
        r"\bfuel\s+(deliver|supply|dispens)",
        # Uniforms / physical supplies
        r"\buniform\s+(rental|supply|laundry)",
        r"\blaundry\s+service",
        r"\blinen\s+service",
        # Security guards (not cybersecurity)
        r"\bsecurity\s+guard",
        r"\barmed\s+guard",
        r"\bunarmed\s+guard",
        r"\bguard\s+service",
        # Medical / clinical (not health IT)
        r"\bphysician\s+staffing",
        r"\bnursing\s+staff",
        r"\bmedical\s+exam",
        r"\bdrug\s+test",
        r"\blab(oratory)?\s+test",
        r"\bblood\s+(draw|test|collect)",
        # Heavy equipment
        r"\bheavy\s+equipment\s+(rental|lease|repair)",
        r"\bbackhoe\b",
        r"\bbulldozer\b",
        r"\bcrane\s+(rental|service)",
        r"\bforklift\s+(repair|maint|rental)",
    ]
]

# If ANY of these appear, the opportunity PASSES regardless of reject patterns.
# These indicate software, IT, or technology relevance.
_PASS_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE) for p in [
        r"\bsoftware\b",
        r"\bsaas\b",
        r"\bcloud\b",
        r"\bplatform\b",
        r"\bapplication\b",
        r"\bweb\s*(based|portal|app)",
        r"\bworkflow\b",
        r"\bautomation\b",
        r"\bcase\s+management\b",
        r"\bdocument\s+management\b",
        r"\bcontent\s+management\b",
        r"\brecords\s+management\b",
        r"\belectronic\s+(form|signature|record)",
        r"\be-?sign",
        r"\bdigital\s+(signature|form|transform)",
        r"\bBPM\b",
        r"\bRPA\b",
        r"\bERP\b",
        r"\bCRM\b",
        r"\bITSM\b",
        r"\bhelp\s*desk\b",
        r"\bservice\s*desk\b",
        r"\bticket(ing)?\s+system\b",
        r"\bdatabase\b",
        r"\bdata\s*(base|warehouse|lake|analytics|integration|migration)",
        r"\bAPI\b",
        r"\bintegration\b",
        r"\bcybersecurity\b",
        r"\bnetwork\s+security\b",
        r"\binformation\s+(technology|system|security)",
        r"\bIT\s+(system|service|solution|infrastructure|support|moderniz|consult)",
        r"\bAI\b",
        r"\bartificial\s+intelligence\b",
        r"\bmachine\s+learning\b",
        r"\banalytics\b",
        r"\bdashboard\b",
        r"\breporting\s+(system|tool|platform|solution)",
        r"\bpermit(ting)?\s+(system|management|software|portal)",
        r"\blicens(e|ing)\s+(system|management|software|portal)",
        r"\binspection\s+(system|management|software|portal)",
        r"\bcompliance\s+(system|management|software|platform)",
        r"\bcontract\s+(management|lifecycle|system)",
        r"\bprocurement\s+(system|software|platform|solution)",
        r"\binvoice\s+(processing|automation|system)",
        r"\bonboarding\s+(system|platform|software|portal)",
        r"\bredaction\b",
        r"\bOCR\b",
        r"\bimplementation\s+service",  # software impl
        r"\bconfigur(e|ation)\b",
        r"\bdeployment\b",
        r"\bhosting\b",
        r"\blicens(e|ing)\s+(renew|subscript|fee)",
        r"\bsubscription\b",
        r"\bmoderniz(e|ation)\b",
    ]
]


def _combine_text(opp: dict[str, Any]) -> str:
    """Build searchable text from title + description + category."""
    parts = [
        opp.get("title") or "",
        opp.get("description") or "",
        opp.get("notice_type") or "",
        opp.get("classification_code") or "",
    ]
    return " ".join(parts)


def prefilter(opp: dict[str, Any]) -> dict[str, Any]:
    """Apply rules-based pre-filter. Returns the opp with a `prefilter` key added.

    opp["prefilter"] = {
        "passed": True/False,
        "reason": str,
        "rule": "naics_pass" | "naics_reject" | "sparse_pass" | "keyword_pass" | "keyword_reject" | "default_pass",
    }
    """
    title = opp.get("title") or ""
    description = opp.get("description") or ""
    naics = opp.get("naics_code") or ""
    combined = _combine_text(opp)

    # ── NAICS fast-track ──────────────────────────────────────
    if naics:
        # Software NAICS → always pass
        if any(naics.startswith(p) for p in _SOFTWARE_NAICS_PREFIXES):
            opp["prefilter"] = {"passed": True, "reason": f"Software NAICS: {naics}", "rule": "naics_pass"}
            return opp

        # Physical/labor NAICS → reject UNLESS software signals present
        if any(naics.startswith(p) for p in _REJECT_NAICS_PREFIXES):
            if not any(pat.search(combined) for pat in _PASS_PATTERNS):
                opp["prefilter"] = {"passed": False, "reason": f"Non-software NAICS: {naics}", "rule": "naics_reject"}
                logger.debug("Pre-filter REJECT (NAICS %s): %s", naics, title[:80])
                return opp
            # Has software signals despite physical NAICS — let through
            opp["prefilter"] = {"passed": True, "reason": f"Physical NAICS {naics} but has software signals", "rule": "naics_override_pass"}
            return opp

    # ── Sparse description → auto-pass ────────────────────────
    text_length = len(title) + len(description)
    if text_length < _MIN_TEXT_LENGTH:
        opp["prefilter"] = {"passed": True, "reason": "Sparse description — may have attachments", "rule": "sparse_pass"}
        return opp

    # ── Keyword matching ──────────────────────────────────────
    has_software_signal = any(pat.search(combined) for pat in _PASS_PATTERNS)
    has_reject_signal = any(pat.search(combined) for pat in _REJECT_PATTERNS)

    if has_software_signal:
        # Software signal found → always pass, even if reject patterns also match
        # (e.g., "HVAC monitoring SOFTWARE" should pass)
        opp["prefilter"] = {"passed": True, "reason": "Software/IT signal detected", "rule": "keyword_pass"}
        return opp

    if has_reject_signal:
        # Strong non-software signal, no software signals → reject
        # Find which pattern matched for logging
        matched = next((pat.pattern for pat in _REJECT_PATTERNS if pat.search(combined)), "?")
        opp["prefilter"] = {"passed": False, "reason": f"Non-software: matched '{matched}'", "rule": "keyword_reject"}
        logger.debug("Pre-filter REJECT (keyword): %s — %s", title[:80], matched)
        return opp

    # ── Default: pass ─────────────────────────────────────────
    # No strong signals either way — let Stage 1 decide
    opp["prefilter"] = {"passed": True, "reason": "No strong signals — passing to Stage 1", "rule": "default_pass"}
    return opp


def batch_prefilter(opps: list[dict[str, Any]]) -> tuple[list[dict], list[dict]]:
    """Filter a batch. Returns (passed, rejected)."""
    passed = []
    rejected = []
    for opp in opps:
        prefilter(opp)
        if opp["prefilter"]["passed"]:
            passed.append(opp)
        else:
            rejected.append(opp)

    if rejected:
        logger.info(
            "Pre-filter: %d passed, %d rejected out of %d total",
            len(passed), len(rejected), len(opps),
        )
    return passed, rejected
