"""Nutrient Low-Code / Integrations — THIN profile.

Falls back to this THIN description when profiles/low_code.md is absent.
Regenerate the real profile with /build-lob-profile generated from the Catalyst
knowledge base (~/.claude/catalyst-data: internal-knowledge.md win/loss and
competitors, field-knowledge.md personas and objections) plus customer stories.
Until then scores are capped and actions limited to investigate/skip.
"""

from oppos.scoring.lobs.base import make_lob

_BLURB = (
    "Nutrient Low-Code / Integrations (fka Muhimbi and Aquaforest): Document Converter for "
    "SharePoint Online/on-prem and for Power Automate, Logic Apps and Nintex (convert, merge, "
    "watermark, OCR, secure and sign PDFs inside Microsoft 365 flows); Document Automation Server "
    "(high-volume server-side OCR, conversion, extraction and watch-folder archiving); Document "
    "Searchability (audit and OCR scanned content in SharePoint and file shares so it is searchable "
    "and compliant); Document Editor for SharePoint/Teams/OneDrive; and Nutrient Documents for "
    "Salesforce. Buyers: SharePoint/Microsoft 365 shops, records and archives teams, Salesforce orgs."
)

_PROFILE = f"""# Nutrient Low-Code / Integrations — Positioning Profile (THIN)

Depth: thin. This is a product description, not a vetted positioning profile with wins,
verticals and competitive evidence. Score conservatively and name what must be verified.

## What it is
{_BLURB}

## Signals of fit
- Microsoft 365 / SharePoint / Power Automate / Nintex named as the platform or incumbent
- Bulk conversion to PDF or PDF/A, records archiving, retention or compliance (PDF/A, OCR for searchability)
- Scanned-document backlogs that must become searchable (OCR at scale, SharePoint or file shares)
- Document generation, merging, watermarking or signing as steps inside an existing business process
- Salesforce document generation or management

## Signals against
- Standalone process/case-management platform requirement (route to Workflow)
- Embedding document capabilities inside a custom-built application (route to SDK)
- Pure hosted API need with no Microsoft 365 or server footprint (route to DWS)
- Large systems-integration program where documents are a minor line item
"""

LOW_CODE = make_lob(
    key="low_code",
    label="Low-Code",
    router_blurb=_BLURB,
    thin_profile=_PROFILE,
    extras_schema=(
        '"pattern_match": "<closest pattern: infopath_sharepoint_migration | sharepoint_watermark_security | power_automate_document_pipeline | repository_ocr_searchability | onprem_batch_document_automation | pii_redaction_compliance | other>",',
        '"platform_context": "<sharepoint | power_automate | nintex | salesforce | server | unknown>",',
    ),
    extras_defaults={"pattern_match": "other", "platform_context": "unknown"},
)
