"""Nutrient Document Web Services (DWS) — THIN profile.

Falls back to this THIN description when profiles/dws.md is absent.
Regenerate the real profile with /build-lob-profile. Until then scores are capped
and actions limited to investigate/skip.
"""

from oppos.scoring.lobs.base import make_lob

_BLURB = (
    "Nutrient Document Web Services (DWS): hosted, pay-per-use REST API for document processing — "
    "convert (Office and HTML to PDF), OCR, extract text/tables/key-value data, redact, sign, "
    "merge/split, compress, flatten and generate PDFs from templates. Buyers: teams that need "
    "document processing without hosting infrastructure — integration/ETL projects, RPA and "
    "automation platforms, digital intake pipelines."
)

_PROFILE = f"""# Nutrient DWS — Positioning Profile (THIN)

Depth: thin. This is a product description, not a vetted positioning profile with wins,
verticals and competitive evidence. Score conservatively and name what must be verified.

## What it is
{_BLURB}

## Signals of fit
- Requirement for document conversion, OCR, data extraction, redaction or e-signature as an API or service
- Cloud/SaaS acceptable; no requirement to host document processing on-premises
- Integration project (ETL, RPA, iPaaS, intake automation) where documents are processed in bulk

## Signals against
- On-premises or air-gapped processing required (route to Low-Code / Document Automation Server)
- In-app user interface for documents required (route to SDK)
- A full business process or case-management application is required (route to Workflow)
"""

DWS = make_lob(
    key="dws",
    label="DWS",
    router_blurb=_BLURB,
    thin_profile=_PROFILE,
    extras_schema=(
        '"pattern_match": "<closest pattern: hosted_conversion_and_pdfa_archival | ocr_and_structured_extraction_intake | automated_redaction_for_public_release | document_generation_from_templates | pdf_accessibility_remediation | hosted_viewer_without_infrastructure | other>",',
        '"processing_operations": ["<convert | ocr | extract | redact | sign | merge | generate | other>"],',
    ),
    extras_defaults={"pattern_match": "other", "processing_operations": []},
)
