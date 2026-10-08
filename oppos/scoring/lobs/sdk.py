"""Nutrient SDK — THIN profile.

TODO: replace with a vetted positioning profile built from nutrient.io customer
stories (Customer Stories blog category), G2 reviews, public repo READMEs and
HubSpot closed-won data. Until then scores are capped and actions limited to
investigate/skip.
"""

from oppos.scoring.lobs.base import LOB

_BLURB = (
    "Nutrient SDK (fka PSPDFKit): developer SDKs for embedding PDF and document viewing, annotation, "
    "editing, forms, redaction, digital signatures, real-time collaboration (Instant), document "
    "generation and Document Authoring into web, iOS, Android, Flutter, React Native, .NET and "
    "server applications; plus Document Engine (server) and AI Assistant. Buyers: software vendors, "
    "systems integrators and in-house development teams building a product or custom system that "
    "needs document capabilities. Usually a component inside a larger build or an OEM/partner "
    "arrangement — rarely a standalone RFP."
)

_PROFILE = f"""# Nutrient SDK — Positioning Profile (THIN)

Depth: thin. This is a product description, not a vetted positioning profile with wins,
verticals and competitive evidence. Score conservatively and name what must be verified.

## What it is
{_BLURB}

## Signals of fit
- A custom application, portal or product is being built and needs in-app document viewing,
  annotation, form filling, redaction, signing or collaboration
- Requirements name platforms (web, iOS, Android, cross-platform) and developer integration (SDK, API, components)
- Large document volumes or sizes rendered in-browser (e.g. case files, plans, medical or legal records)
- Accessibility, offline or on-device requirements for document handling
- A systems integrator or software vendor is the likely prime, with Nutrient as a component

## Signals against
- Buyer wants a finished business application, not a development component (route to Workflow or Low-Code)
- Hosted document-processing API with no UI need (route to DWS)
- Hardware, staffing or unrelated software categories

## How Nutrient participates
Set `play` to: `direct` (Nutrient could respond itself), `partner_si` (a systems integrator or
vendor would prime and embed Nutrient), `oem` (a software vendor would license and resell), or
`unknown`.
"""

SDK = LOB(
    key="sdk",
    label="SDK",
    router_blurb=_BLURB,
    profile=_PROFILE,
    depth="thin",
    extras_schema=(
        '"play": "<direct | partner_si | oem | unknown>",',
        '"platforms": ["<web | ios | android | flutter | react_native | dotnet | server>"],',
    ),
    extras_defaults={"play": "unknown", "platforms": []},
)
