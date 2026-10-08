---
lob: dws
depth: thin
depth_note: no directly attributable customer evidence yet — verticals are analogues; the score cap stays until real wins exist
version: 1
generated_at: 2026-10-08
generated_by: research agent (public sources)
sources:
  - https://www.nutrient.io/api/
  - https://www.nutrient.io/api/processor-api/
  - https://www.nutrient.io/api/viewer-api/
  - https://www.nutrient.io/api/pricing/processor-api/
  - https://www.nutrient.io/guides/dws-processor/
  - https://www.nutrient.io/guides/dws-processor/tools-and-api/
  - https://www.nutrient.io/guides/dws-processor/privacy/
  - https://www.nutrient.io/guides/dws-processor/security/
  - https://www.nutrient.io/guides/dws-data-extraction/
  - https://www.nutrient.io/sdk/pricing/
  - https://www.nutrient.io/sdk/document-engine/
  - https://www.nutrient.io/sdk/solutions/government/
  - https://trust.nutrient.io/
  - https://www.nutrient.io/blog/categories/customer-stories/
  - https://www.nutrient.io/blog/new-forest-case-study/
  - https://www.nutrient.io/blog/auditfile-self-hosted-pdf-editing/
  - https://www.nutrient.io/blog/scaling-legal-document-workflows-harvey/
  - https://www.nutrient.io/blog/athena-nutrient-enterprise-ai-compliance/
  - https://www.nutrient.io/blog/fuseworks-nutrient-web-sdk-document-signing/
  - https://www.nutrient.io/blog/kwiksign-case-study-cut-dev-time-six-months/
  - https://www.nutrient.io/blog/secure-financial-documents-under/
  - https://www.nutrient.io/blog/imaging-efficiency-gdpicture-roadone/
  - https://www.nutrient.io/blog/enterprise-pdf-sdks/
  - https://www.g2.com/products/nutrient-sdk/reviews
  - https://github.com/PSPDFKit/nutrient-dws-client-python
  - https://github.com/PSPDFKit/nutrient-document-engine-mcp-server
  - https://github.com/PSPDFKit/nutrient-extraction-samples
  - https://github.com/PSPDFKit/pdf-to-markdown
---
# Nutrient DWS — Capability Profile for RFP Qualification

## What it is
- Nutrient Document Web Services (DWS) is a "hosted REST API" with "25+ PDF API tools" in four APIs: Processor ("Generate, Convert, OCR, Redact, Watermark, Sign"), Data Extraction (parse, schema extraction, classification), Accessibility ("Auto-tag PDFs and validate PDF/UA conformance") and Viewer ("Viewing, annotation, form filling, and signing, embedded in the browser") [src: https://www.nutrient.io/api/].
- The Processor API is "a simple document-in, document-out-based workflow that scales as you grow" [src: https://www.nutrient.io/guides/dws-processor/]. Scale claim: "1B+ documents processed a year — for 3,000+ teams," used by Lufthansa, Disney, Autodesk, UBS, Dropbox and IBM [src: https://www.nutrient.io/api/].
- Portfolio position: the SDK/Document Engine engine delivered as SaaS; the SDK pricing page lists DWS as the "Usage-based" path [src: https://www.nutrient.io/sdk/pricing/]. Dividing line: Web SDK with a licence key is "the client-side path for apps that want to own authorization and document delivery themselves, including offline use cases"; with DWS "You do not need to run Document Engine" [src: https://www.nutrient.io/api/viewer-api/].
- RFP relevance: DWS answers "convert to PDF/A," "OCR scanned records," "redact PII," "generate letters from templates," "extract fields," "make PDFs accessible," with no hosting burden [UNVERIFIED — qualifier judgement].

## Core capabilities
Processor API tools, named on the tools index [src: https://www.nutrient.io/guides/dws-processor/tools-and-api/]:
- Generation: "PDF generator API" (HTML/CSS), "Markdown-to-PDF API," "DOCX templating API" (Word templates populated from JSON with placeholders and loops).
- Conversion: "Office-to-PDF API," "Image-to-PDF API," "PDF-to-Office API," PDF/Document-to-image, "PDF-to-HTML API," "PDF-to-Markdown API," "PDF-to-PDF/A API" (PDF/A-1 through PDF/A-4).
- Recognition: "PDF OCR API" ("over 80 languages"); text, image, table and key-value extraction; AI redaction [src: https://www.nutrient.io/api/processor-api/].
- Protection: "Redaction API" (permanently removes text, images and vector content), "PDF security API" (passwords, permissions), "PDF watermark API," "PDF digital signature API."
- Editing: merge, split, page manipulation, rotate, flatten, "PDF form filling API" (JSON-driven), import Instant JSON and XFDF; "PDF optimization API," "PDF linearization API."
- Accessibility: "PDF/UA auto-tagging API" — "Automatically add accessibility tags to PDFs in a single API call." Cost control: "Analyze Build API" estimates consumption before executing.
Data Extraction API [src: https://www.nutrient.io/guides/dws-data-extraction/]:
- Parse: "Return the document's full structure as typed spatial elements with bounding boxes or whole-document Markdown." Extract: "Map a document to your JSON Schema and return the requested fields with per-field citations." Classify: "Score a document against labels you define and return a ranked list."
- Inputs "PDFs, images, and Office files," "more than 100 languages"; outputs carry "bounding boxes, confidence scores, and reading order." Public samples show grounded extraction on US government forms [src: https://github.com/PSPDFKit/nutrient-extraction-samples].
Viewer API: "hosted service for DWS-authorized viewer sessions"; renders "PDFs, Office files, and PNG, JPG, and TIFF documents"; annotations, "Form viewing and filling with native controls," "Electronic and digital signatures," "Real-time multiuser collaboration" [src: https://www.nutrient.io/api/viewer-api/].
Developer surface: clients for Python, JavaScript/TypeScript, Java, C#, PHP [src: https://www.nutrient.io/guides/dws-processor/] [src: https://github.com/PSPDFKit/nutrient-dws-client-python]; Zapier, Postman and MCP integrations [src: https://www.nutrient.io/api/processor-api/].

## Deployment options
- Nutrient-hosted SaaS only: "Start in minutes, no servers needed" [src: https://www.nutrient.io/sdk/document-engine/]. Infrastructure on AWS (United States, Germany, Ireland) and Google Cloud (United States); per-plan region selection not stated [src: https://trust.nutrient.io/].
- On-prem or private-cloud demands are met by self-hosted Document Engine or Managed Cloud under the SDK LOB, not DWS; Nutrient's own README splits DWS (cloud) from Document Engine ("On-prem/private cloud," "deployment control and data residency") [src: https://github.com/PSPDFKit/nutrient-document-engine-mcp-server].
- Local-only extraction exists as the Nutrient CLI: "Your documents are not uploaded to Nutrient" [src: https://github.com/PSPDFKit/pdf-to-markdown].

## Security & compliance
- "SOC 2 Type 2, SOC 3" stated for "DWS API"; report "Nutrient SOC 2 Type 2 (SDKs, Cloud, and Workflow)"; annual third-party pen testing, DR plan, subprocessor list, bug bounty [src: https://trust.nutrient.io/].
- Processor API page: "SOC 2 Type 2 audited and GDPR compliant"; "All documents are encrypted in transit using HTTPS/TLS and at rest"; features "help meet GDPR, HIPAA, and other data privacy regulations" [src: https://www.nutrient.io/api/processor-api/].
- Viewer API: "Security is built into every layer of DWS Viewer API"; SOC 2 Type 2; GDPR-compliant [src: https://www.nutrient.io/api/viewer-api/].
- Retention: default plans — files "are only stored for the time needed to process the request and are deleted within 24 hours." Retention-enabled plans — files are used "to operate, improve, and develop our services, including to train and evaluate our models" [src: https://www.nutrient.io/guides/dws-processor/privacy/]. Regulated responses must specify a no-retention plan.
- Security guide: HTTPS required; account and metrics data "stored in an encrypted database"; payments via Paddle [src: https://www.nutrient.io/guides/dws-processor/security/].
- NOT stated on pages read: FedRAMP, StateRAMP, CJIS, ISO 27001 certificate, signed HIPAA BAA, customer-selectable region, uptime SLA [src: https://trust.nutrient.io/].

## Licensing & pricing posture
- Credit-based: "every API operation has a fixed credit cost," heavier operations such as OCR cost more; monthly or annual billing with an annual discount; free tier with an "evaluation watermark" for validating workflows "before procurement enters the conversation" [src: https://www.nutrient.io/api/pricing/processor-api/].
- Overage: pay-as-you-go "with configurable increments, up to a spending cap you control"; enterprise "tailored packages with volume discounts" [src: https://www.nutrient.io/api/pricing/processor-api/].
- Viewer API meters "viewer-session quota"; "Upload, storage, and document-count limits apply"; free tier restricts commercial use for larger enterprises [src: https://www.nutrient.io/api/viewer-api/].
- Self-service by design ("Get your API key — free") [src: https://www.nutrient.io/api/]. Fits per-transaction RFP pricing; fixed-fee or per-seat schedules need an enterprise package.

## Proven verticals (with evidence)
Tier 1 — directly DWS-attributed
- None. No readable nutrient.io customer story names DWS or any of its APIs; stories are attributed to Web SDK, mobile SDKs, Document Engine, Workflow, Document Automation Server and GdPicture.NET [src: https://www.nutrient.io/blog/categories/customer-stories/]. API-page logos have no stories behind them [src: https://www.nutrient.io/api/].

Tier 2 — same engine, adjacent delivery (Document Engine or server-side features DWS exposes as hosted calls)
- Legal and regulated AI: Harvey (Document Engine; ~50% MoM document growth) [src: https://www.nutrient.io/blog/scaling-legal-document-workflows-harvey/]; Athena Intelligence (redaction, comparison) [src: https://www.nutrient.io/blog/athena-nutrient-enterprise-ai-compliance/].
- Audit: AuditFile (Document Engine; chose self-hosting for data residency — a counter-signal for DWS) [src: https://www.nutrient.io/blog/auditfile-self-hosted-pdf-editing/].
- Signing platforms: FuseWorks, KwikSign (Web SDK signing; the Processor signature tool is the headless equivalent) [src: https://www.nutrient.io/blog/fuseworks-nutrient-web-sdk-document-signing/] [src: https://www.nutrient.io/blog/kwiksign-case-study-cut-dev-time-six-months/].
- Fintech forms: Under (400+ field applications) [src: https://www.nutrient.io/blog/secure-financial-documents-under/].

Tier 3 — vertical signal only
- Government records: New Forest National Park Authority converted 2 million documents (TIFF-to-PDF, OCR, merge) with Document Automation Server — public-sector backfile OCR, but via the Low-Code LOB [src: https://www.nutrient.io/blog/new-forest-case-study/]. The government page lists legacy-record OCR, "Redaction for public release" and "PDF/A for preservation" [src: https://www.nutrient.io/sdk/solutions/government/].
- Logistics imaging: RoadOne (GdPicture.NET) [src: https://www.nutrient.io/blog/imaging-efficiency-gdpicture-roadone/]. Healthcare, insurance, mortgage: sample-repo evidence only [src: https://github.com/PSPDFKit/nutrient-extraction-samples].

## RFP pattern matches
1. `key: hosted_conversion_and_pdfa_archival`
   - Signals: "convert Office/images to PDF," "PDF/A for retention," "no additional servers," "API-first," "SaaS preferred."
   - Capabilities: Office-to-PDF, Image-to-PDF, PDF-to-PDF/A, merge, optimisation, linearisation [src: https://www.nutrient.io/guides/dws-processor/tools-and-api/].
   - Evidence: New Forest NPA (engine analogue) [src: https://www.nutrient.io/blog/new-forest-case-study/]; SOC 2 for DWS API [src: https://trust.nutrient.io/].
2. `key: ocr_and_structured_extraction_intake`
   - Signals: "digitise scanned applications," "extract fields to our system of record," "classify incoming mail," "claims capture," "RAG indexing."
   - Capabilities: OCR, Data Extraction parse/extract/classify with JSON Schema and per-field citations, PDF-to-Markdown [src: https://www.nutrient.io/guides/dws-data-extraction/].
   - Evidence: grounded-extraction samples on US government forms [src: https://github.com/PSPDFKit/nutrient-extraction-samples].
3. `key: automated_redaction_for_public_release`
   - Signals: "FOIA/public records," "PII/PHI redaction at scale," "permanent removal," "pattern-based (SSN, DOB)," "pre-publication review."
   - Capabilities: Redaction API, AI redaction, PDF security API [src: https://www.nutrient.io/guides/dws-processor/tools-and-api/] [src: https://www.nutrient.io/api/processor-api/].
   - Evidence: Athena Intelligence [src: https://www.nutrient.io/blog/athena-nutrient-enterprise-ai-compliance/]; government page use case [src: https://www.nutrient.io/sdk/solutions/government/].
4. `key: document_generation_from_templates`
   - Signals: "generate notices/letters/permits," "merge data into Word templates," "HTML to PDF," "fill PDF forms from our database."
   - Capabilities: DOCX templating, PDF generator, Markdown-to-PDF, form filling from JSON, digital signature, watermark [src: https://www.nutrient.io/guides/dws-processor/tools-and-api/].
   - Evidence: Under (adjacent) [src: https://www.nutrient.io/blog/secure-financial-documents-under/].
5. `key: pdf_accessibility_remediation`
   - Signals: "ADA Title II," "WCAG," "Section 508," "PDF/UA," "remediate existing PDFs."
   - Capabilities: Accessibility API ("Auto-tag PDFs and validate PDF/UA conformance"), PDF/UA auto-tagging, PDF/A [src: https://www.nutrient.io/api/] [src: https://www.nutrient.io/guides/dws-processor/tools-and-api/].
   - Evidence: product pages only; no story.
6. `key: hosted_viewer_without_infrastructure`
   - Signals: "embed a document viewer," "we have no DevOps," "vendor hosts everything," "annotate and sign in browser," "usage-based."
   - Capabilities: Viewer API (rendering, annotations, forms, signatures, collaboration) [src: https://www.nutrient.io/api/viewer-api/].
   - Evidence: FuseWorks, KwikSign as functional analogues [src: https://www.nutrient.io/blog/kwiksign-case-study-cut-dev-time-six-months/].

## Competitive positioning
- Nutrient's own comparison frames Apryse, Foxit, Syncfusion, IronPDF ("Backend-only") and ComPDFKit as rivals; DWS inherits that positioning [src: https://www.nutrient.io/blog/enterprise-pdf-sdks/].
- Hosted-API competitors an RFP may name: Adobe PDF Services API, CloudConvert, PDF.co, Docparser, and hyperscaler OCR (AWS Textract, Azure Document Intelligence, Google Document AI) [UNVERIFIED — general market knowledge].
- Lead differentiators: breadth in one API ("over 30 modular tools") [src: https://www.nutrient.io/api/processor-api/]; extraction with "per-field citations" [src: https://www.nutrient.io/guides/dws-data-extraction/]; PDF/UA auto-tagging [src: https://www.nutrient.io/guides/dws-processor/tools-and-api/]; a path to self-hosted Document Engine when residency rules tighten [src: https://www.nutrient.io/sdk/document-engine/].
- G2 (SDK-level snippets only): reliability and support praised, price criticised; no DWS listing [src: https://www.g2.com/products/nutrient-sdk/reviews]. Against hyperscalers: no stated FedRAMP, region pinning or uptime SLA [src: https://trust.nutrient.io/].

## What makes an RFP a GOOD fit
- Headless, transactional processing where the buyer accepts SaaS and wants no servers [src: https://www.nutrient.io/sdk/document-engine/].
- A mixed list that would otherwise need three vendors: conversion, OCR, redaction, signing, accessibility [src: https://www.nutrient.io/api/processor-api/].
- SOC 2 Type 2 and GDPR are the bar; US or EU hosting on AWS/GCP is acceptable [src: https://trust.nutrient.io/].
- Per-transaction pricing or "proof of concept before award" language, which suits the credit model and free tier [src: https://www.nutrient.io/api/pricing/processor-api/].
- Integration via REST, common language clients, Zapier or MCP [src: https://www.nutrient.io/guides/dws-processor/]; PDF accessibility remediation (ADA/PDF/UA) [src: https://www.nutrient.io/guides/dws-processor/tools-and-api/].

## What makes an RFP a BAD fit
- Mandatory on-prem, private cloud, air-gapped or "data never leaves our tenancy" — route to SDK (self-hosted Document Engine or Managed Cloud) [src: https://www.nutrient.io/sdk/document-engine/].
- FedRAMP/StateRAMP/CJIS or signed HIPAA BAA as pass/fail — not stated publicly; confirm with security first [src: https://trust.nutrient.io/].
- Rich interactive or offline UX on mobile (field apps, EFBs) — route to SDK [src: https://www.nutrient.io/api/viewer-api/].
- Process scope: approvals, routing, case management, task assignment, dashboards — route to Workflow (Nutrient Workflow Automation) [src: https://trust.nutrient.io/].
- SharePoint, Microsoft 365, Power Automate, Nintex, or bulk backfile OCR on the buyer's servers — route to Low-Code (Document Converter, Document Automation Server, Searchability); New Forest NPA is the reference [src: https://www.nutrient.io/blog/new-forest-case-study/].
- End-user desktop PDF seats — no DWS play [UNVERIFIED — judgement]. Buyer prohibits any vendor use of its data — respond only with a no-retention plan [src: https://www.nutrient.io/guides/dws-processor/privacy/].

## Knowledge gaps in this profile
- No HubSpot, internal Slack or Notion access: DWS customer list, win/loss, enterprise terms, SLA language, BAA availability and region-pinning options are unknown.
- Zero public customer stories name DWS; vertical evidence is inferred from Document Engine/SDK stories or sample repos. Treat Tier 2/3 as analogues, not references.
- The `.md` suffix returned 404 on every nutrient.io URL tried; content came from HTML via a fetch model, so quotations may be lightly paraphrased. G2 blocked direct fetch (HTTP 403) [src: https://www.g2.com/products/nutrient-sdk/reviews].
- Uptime SLA, rate limits, maximum file size, region pinning, and whether the Data Extraction and Accessibility APIs share the Processor deletion policy were not confirmed. Credit costs and plan sizes were deliberately omitted [src: https://www.nutrient.io/api/pricing/processor-api/].
