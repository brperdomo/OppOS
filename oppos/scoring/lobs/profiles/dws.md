---
lob: dws
depth: full
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
  - https://github.com/PSPDFKit/nutrient-dws-mcp-server
  - https://github.com/PSPDFKit/nutrient-document-engine-mcp-server
  - https://github.com/PSPDFKit/nutrient-extraction-samples
  - https://github.com/PSPDFKit/pdf-to-markdown
---
# Nutrient DWS — Capability Profile for RFP Qualification

## What it is
- Nutrient Document Web Services (DWS) is Nutrient's "hosted REST API" with "25+ PDF API tools," grouped into four APIs: Processor API ("Generate, Convert, OCR, Redact, Watermark, Sign"), Data Extraction API ("Parse documents into clean structured output, extract exactly the fields a schema defines, or classify documents"), Accessibility API ("Auto-tag PDFs and validate PDF/UA conformance") and Viewer API ("Viewing, annotation, form filling, and signing, embedded in the browser") [src: https://www.nutrient.io/api/].
- The Processor API is "an HTTP API that provides you with a simple document-in, document-out-based workflow that scales as you grow" [src: https://www.nutrient.io/guides/dws-processor/]. Nothing is installed; the buyer sends files and receives results.
- Scale claim on the product page: "1B+ documents processed a year — for 3,000+ teams," used by Lufthansa, Disney, Autodesk, UBS, Dropbox and IBM [src: https://www.nutrient.io/api/].
- Position in Nutrient's portfolio: the same engine as the SDK/Document Engine, delivered as SaaS; the SDK pricing page lists DWS as the "Usage-based" path for growing SaaS products [src: https://www.nutrient.io/sdk/pricing/]. The Viewer API page draws the line: Web SDK with a licence key is "the client-side path for apps that want to own authorization and document delivery themselves, including offline use cases"; DWS is for teams that do not want to "run Document Engine or viewer infrastructure" [src: https://www.nutrient.io/api/viewer-api/].
- RFP relevance: DWS answers lines such as "convert submissions to PDF/A," "OCR scanned records," "redact PII before release," "generate forms/letters from templates," "extract fields from invoices or applications," "make PDFs accessible," with no hosting obligation on the buyer [UNVERIFIED — qualifier judgement].

## Core capabilities
Processor API tools, as named on the tools index [src: https://www.nutrient.io/guides/dws-processor/tools-and-api/]:
- Generation: "PDF generator API" (HTML/CSS templates), "Markdown-to-PDF API," "DOCX templating API" (populate Word templates from JSON with placeholders and loops).
- Conversion: "Office-to-PDF API" (Word, Excel, PowerPoint, with tracked-change handling), "Image-to-PDF API," "PDF-to-Office API" (DOCX/XLSX/PPTX), "PDF-to-image API," "Document-to-image API," "PDF-to-HTML API," "PDF-to-Markdown API," "PDF-to-PDF/A API" (PDF/A-1 through PDF/A-4).
- Recognition and extraction: "PDF OCR API" ("over 80 languages"), table extraction, text/image/key-value extraction [src: https://www.nutrient.io/api/processor-api/].
- Protection: "Redaction API" (permanently removes text, images and vector content), "PDF security API" (passwords, print/copy restrictions), "PDF watermark API," "PDF digital signature API" (visible or invisible).
- Editing: "PDF merge API," "PDF split API," "PDF page manipulation API," "PDF rotate API," "PDF flatten API," "PDF form filling API" (JSON-driven), "Import Instant JSON API," "Import XFDF annotations API."
- Optimisation: "PDF optimization API," "PDF linearization API."
- Accessibility: "PDF/UA auto-tagging API" — "Automatically add accessibility tags to PDFs in a single API call" [src: https://www.nutrient.io/guides/dws-processor/tools-and-api/].
- Cost control: "Analyze Build API" estimates consumption before executing [src: https://www.nutrient.io/guides/dws-processor/tools-and-api/].
- AI features on the Processor page: automated data extraction, table-to-structured output, AI redaction [src: https://www.nutrient.io/api/processor-api/].
Data Extraction API [src: https://www.nutrient.io/guides/dws-data-extraction/]:
- Parse: "Return the document's full structure as typed spatial elements with bounding boxes or whole-document Markdown."
- Extract: "Map a document to your JSON Schema and return the requested fields with per-field citations."
- Classify: "Score a document against labels you define and return a ranked list, so you can route it before extracting anything."
- Inputs "PDFs, images, and Office files," "more than 100 languages with multilingual OCR support"; outputs carry "bounding boxes, confidence scores, and reading order."
- Public sample repo demonstrates grounded extraction on US government forms (Treasury mortgage-assistance request, GSA SF-91 crash report, CMS prior-authorisation form) with per-field bounding boxes [src: https://github.com/PSPDFKit/nutrient-extraction-samples].
Viewer API [src: https://www.nutrient.io/api/viewer-api/]:
- "hosted service for DWS-authorized viewer sessions"; renders "PDFs, Office files, and PNG, JPG, and TIFF documents"; annotations, "Form viewing and filling with native controls," "Electronic and digital signatures," "Real-time multiuser collaboration," password-protected documents.
Developer surface:
- Client libraries for Python, JavaScript/TypeScript, Java, C#, PHP plus raw HTTP [src: https://www.nutrient.io/guides/dws-processor/]; official Python client claims "100% mapping with DWS Processor API" [src: https://github.com/PSPDFKit/nutrient-dws-client-python].
- Integrations named: Zapier, Postman collection, MCP server [src: https://www.nutrient.io/api/processor-api/]. The DWS MCP server is positioned for "Cloud document workflows" via "Nutrient-hosted API (API key)" [src: https://github.com/PSPDFKit/nutrient-document-engine-mcp-server].

## Deployment options
- Nutrient-hosted SaaS only. DWS is the "Cloud APIs" tier of Document Engine delivery: "Start in minutes, no servers needed" [src: https://www.nutrient.io/sdk/document-engine/].
- Hosting regions for Nutrient infrastructure: AWS (United States, Germany, Ireland) and Google Cloud (United States) [src: https://trust.nutrient.io/]. Region selection per DWS plan is not stated on the pages read.
- If the RFP demands on-prem or private cloud, the equivalent is self-hosted Document Engine or Managed Cloud (dedicated instance) under the SDK LOB, not DWS [src: https://www.nutrient.io/sdk/document-engine/]. The Document Engine MCP README states the split: DWS for cloud, Document Engine for "On-prem/private cloud" with "deployment control and data residency" [src: https://github.com/PSPDFKit/nutrient-document-engine-mcp-server].
- Local-only extraction exists as the Nutrient CLI (pdf-to-markdown): "Your documents are not uploaded to Nutrient" — useful when an RFP wants RAG-style conversion without cloud [src: https://github.com/PSPDFKit/pdf-to-markdown].

## Security & compliance
- "SOC 2 Type 2, SOC 3" stated for "DWS API" on the Trust Center, with a report "Nutrient SOC 2 Type 2 (SDKs, Cloud, and Workflow)"; annual third-party pen testing, DR plan, subprocessor list, bug bounty, customer data deletion on request [src: https://trust.nutrient.io/].
- Processor API page: "SOC 2 Type 2 audited and GDPR compliant"; "All documents are encrypted in transit using HTTPS/TLS and at rest"; features "help meet GDPR, HIPAA, and other data privacy regulations"; redaction is permanent rather than masking; isolated request processing [src: https://www.nutrient.io/api/processor-api/].
- Viewer API page: "Security is built into every layer of DWS Viewer API"; SOC 2 Type 2; GDPR-compliant; encrypted in transit and at rest [src: https://www.nutrient.io/api/viewer-api/].
- Data retention (Processor API privacy guide): default plans — "Files you upload as part of your requests and the resulting files we generate are only stored for the time needed to process the request and are deleted within 24 hours"; "Nutrient DWS Processor API doesn't permanently store the files you upload." Retention-enabled plans — "We retain the files you submit and the outputs we generate and use them to operate, improve, and develop our services, including to train and evaluate our models" [src: https://www.nutrient.io/guides/dws-processor/privacy/]. For any public-sector or regulated RFP, the response must specify a no-retention plan.
- Security guide: HTTPS required; account and metrics data "stored in an encrypted database"; payments handled by Paddle so DWS "never has direct access to any of your payment data" [src: https://www.nutrient.io/guides/dws-processor/security/].
- Pricing page lists "GDPR, HIPAA, and SOC 2 Type 2-audited controls" [src: https://www.nutrient.io/api/pricing/processor-api/].
- NOT stated on pages read: FedRAMP, StateRAMP, CJIS, ISO 27001 certificate, a signed HIPAA BAA, customer-selectable region, or an uptime SLA [src: https://trust.nutrient.io/] [src: https://www.nutrient.io/api/processor-api/].

## Licensing & pricing posture
- Credit-based consumption: "every API operation has a fixed credit cost"; heavier operations (e.g. OCR) cost more credits than light ones; monthly or annual billing with an annual discount [src: https://www.nutrient.io/api/pricing/processor-api/].
- Free tier with limited monthly credits and an "evaluation watermark," intended for validating workflows "before procurement enters the conversation" [src: https://www.nutrient.io/api/pricing/processor-api/]. Viewer API free tier: "commercial use on the free tier is restricted" for larger enterprises [src: https://www.nutrient.io/api/viewer-api/].
- Overage: optional pay-as-you-go "with configurable increments, up to a spending cap you control" [src: https://www.nutrient.io/api/pricing/processor-api/].
- Enterprise: "tailored packages with volume discounts" through sales [src: https://www.nutrient.io/api/pricing/processor-api/].
- Viewer API meters "viewer-session quota"; "Upload, storage, and document-count limits apply" [src: https://www.nutrient.io/api/viewer-api/].
- Self-service by design: "Get your API key — free" [src: https://www.nutrient.io/api/]. Fit for RFPs priced per transaction or per document; awkward for fixed-fee or per-seat schedules unless an enterprise package is negotiated.

## Proven verticals (with evidence)
Tier 1 — directly DWS-attributed public evidence
- None. No readable customer story on nutrient.io names DWS, the Processor API, the Data Extraction API or the Viewer API as the product used; the customer-stories index attributes stories to Web SDK, mobile SDKs, Document Engine, Workflow, Document Automation Server and GdPicture.NET [src: https://www.nutrient.io/blog/categories/customer-stories/]. Logo-level claims (Lufthansa, Disney, Autodesk, UBS, Dropbox, IBM; "3,000+ teams") sit on the API page without stories [src: https://www.nutrient.io/api/].

Tier 2 — same engine, adjacent delivery (Document Engine / server-side features that DWS exposes as hosted calls)
- Legal and regulated AI platforms: Harvey (Document Engine, ~50% MoM document growth) [src: https://www.nutrient.io/blog/scaling-legal-document-workflows-harvey/]; Athena Intelligence (redaction, comparison, citations for Fortune 500 regulated customers) [src: https://www.nutrient.io/blog/athena-nutrient-enterprise-ai-compliance/].
- Audit and finance: AuditFile (Document Engine; chose self-hosting for data residency — a counter-signal for DWS) [src: https://www.nutrient.io/blog/auditfile-self-hosted-pdf-editing/].
- Digital signing platforms: FuseWorks, KwikSign (Web SDK signing; the Processor API's digital-signature tool addresses the headless version of this need) [src: https://www.nutrient.io/blog/fuseworks-nutrient-web-sdk-document-signing/] [src: https://www.nutrient.io/blog/kwiksign-case-study-cut-dev-time-six-months/] [src: https://www.nutrient.io/guides/dws-processor/tools-and-api/].
- Fintech forms: Under (400+ field financial applications; form filling and mapping) [src: https://www.nutrient.io/blog/secure-financial-documents-under/].

Tier 3 — vertical signal only
- Government records: New Forest National Park Authority converted 2 million historical documents (TIFF-to-PDF, OCR, merge, 30,000 files daily) using Document Automation Server — proof that Nutrient engines handle public-sector backfile OCR, but delivered via the Low-Code LOB, not DWS [src: https://www.nutrient.io/blog/new-forest-case-study/]. The government solutions page lists OCR of legacy records, "Redaction for public release" and "PDF/A for preservation" as target use cases [src: https://www.nutrient.io/sdk/solutions/government/].
- Logistics imaging: RoadOne (GdPicture.NET billing-document automation) shows the batch imaging pattern DWS addresses in the cloud [src: https://www.nutrient.io/blog/imaging-efficiency-gdpicture-roadone/].
- Healthcare, insurance, mortgage: only sample-repo evidence (CMS, GSA, Treasury forms) [src: https://github.com/PSPDFKit/nutrient-extraction-samples].

## RFP pattern matches
1. `key: hosted_conversion_and_pdfa_archival`
   - Signals: "convert Office/images to PDF," "PDF/A for long-term retention," "records retention schedule," "no additional servers," "API-first," "SaaS preferred."
   - Capabilities: Office-to-PDF, Image-to-PDF, PDF-to-PDF/A (A-1 to A-4), merge, optimisation, linearisation [src: https://www.nutrient.io/guides/dws-processor/tools-and-api/].
   - Evidence: New Forest NPA (engine-level analogue) [src: https://www.nutrient.io/blog/new-forest-case-study/]; SOC 2 Type 2 for DWS API [src: https://trust.nutrient.io/].
2. `key: ocr_and_structured_extraction_intake`
   - Signals: "digitise scanned applications," "extract fields to our system of record," "classify incoming mail," "invoice/claims capture," "accuracy with confidence scores," "RAG/search indexing."
   - Capabilities: OCR 80+ languages, Data Extraction parse/extract/classify with JSON Schema and per-field citations, PDF-to-Markdown [src: https://www.nutrient.io/guides/dws-data-extraction/] [src: https://www.nutrient.io/guides/dws-processor/tools-and-api/].
   - Evidence: grounded-extraction samples on US government forms [src: https://github.com/PSPDFKit/nutrient-extraction-samples].
3. `key: automated_redaction_for_public_release`
   - Signals: "FOIA/public records requests," "PII/PHI redaction at scale," "permanent removal," "pattern-based (SSN, DOB)," "pre-publication review."
   - Capabilities: Redaction API (permanent, text/image/vector), AI redaction, PDF security API [src: https://www.nutrient.io/guides/dws-processor/tools-and-api/] [src: https://www.nutrient.io/api/processor-api/].
   - Evidence: Athena Intelligence (redaction in regulated workflows) [src: https://www.nutrient.io/blog/athena-nutrient-enterprise-ai-compliance/]; government page use case [src: https://www.nutrient.io/sdk/solutions/government/].
4. `key: document_generation_from_templates`
   - Signals: "generate notices/letters/permits/certificates," "merge data into Word templates," "HTML or Markdown to PDF," "batch correspondence," "fill PDF forms from our database."
   - Capabilities: DOCX templating, PDF generator (HTML/CSS), Markdown-to-PDF, PDF form filling from JSON, digital signature, watermark [src: https://www.nutrient.io/guides/dws-processor/tools-and-api/].
   - Evidence: Under (form mapping) as an adjacent story [src: https://www.nutrient.io/blog/secure-financial-documents-under/].
5. `key: pdf_accessibility_remediation`
   - Signals: "ADA Title II," "WCAG," "Section 508," "PDF/UA," "remediate existing PDFs," "accessible public documents."
   - Capabilities: Accessibility API ("Auto-tag PDFs and validate PDF/UA conformance"), PDF/UA auto-tagging API, PDF/A conversion [src: https://www.nutrient.io/api/] [src: https://www.nutrient.io/guides/dws-processor/tools-and-api/].
   - Evidence: product pages only; no customer story [src: https://www.nutrient.io/api/].
6. `key: hosted_viewer_without_infrastructure`
   - Signals: "embed a document viewer," "we have no DevOps," "SaaS vendor hosts everything," "annotate and sign in browser," "usage-based."
   - Capabilities: Viewer API (rendering, annotations, forms, e/digital signatures, collaboration) [src: https://www.nutrient.io/api/viewer-api/].
   - Evidence: Web SDK viewer stories (FuseWorks, KwikSign) as functional analogues [src: https://www.nutrient.io/blog/kwiksign-case-study-cut-dev-time-six-months/].

## Competitive positioning
- Nutrient's own SDK comparison frames Apryse, Foxit, Syncfusion, IronPDF (".NET HTML-to-PDF conversion," "Backend-only") and ComPDFKit as rivals; DWS inherits that engine-level positioning [src: https://www.nutrient.io/blog/enterprise-pdf-sdks/].
- Hosted-API competitors an RFP may name include Adobe PDF Services API, Apryse/PDF.co-style APIs, CloudConvert, PDF.co, Docparser, and hyperscaler OCR (AWS Textract, Azure Document Intelligence, Google Document AI) [UNVERIFIED — general market knowledge].
- Differentiators to lead with: breadth in one API ("over 30 modular tools" spanning generation, conversion, OCR, redaction, signing, accessibility) [src: https://www.nutrient.io/api/processor-api/]; grounded extraction with "per-field citations" and bounding boxes [src: https://www.nutrient.io/guides/dws-data-extraction/]; PDF/UA auto-tagging as a first-class tool [src: https://www.nutrient.io/guides/dws-processor/tools-and-api/]; a path from hosted (DWS) to self-hosted (Document Engine) on the same engine when residency rules tighten [src: https://www.nutrient.io/sdk/document-engine/].
- Reviewer themes (SDK-level, G2 via search snippets, G2 blocked direct fetch): reliability and support praised; price and per-module licensing criticised [src: https://www.g2.com/products/nutrient-sdk/reviews]. No DWS-specific G2 listing was found.
- Weaknesses against hyperscalers: no stated FedRAMP, no customer-selectable region, no public uptime SLA on pages read [src: https://trust.nutrient.io/].

## What makes an RFP a GOOD fit
- Headless, transactional document processing where the buyer explicitly accepts SaaS/cloud and wants no servers [src: https://www.nutrient.io/sdk/document-engine/].
- Mixed requirement list that would otherwise need three vendors: conversion plus OCR plus redaction plus signing plus accessibility [src: https://www.nutrient.io/api/processor-api/].
- SOC 2 Type 2 and GDPR are the security bar; EU or US hosting on AWS/GCP is acceptable [src: https://trust.nutrient.io/] [src: https://www.nutrient.io/api/processor-api/].
- Volume-priced or per-transaction procurement; pilot-first language ("proof of concept before award") suits the free tier and credit model [src: https://www.nutrient.io/api/pricing/processor-api/].
- Integration into an existing system via REST, Python/JS/Java/C#/PHP, Zapier or an MCP/agent framework [src: https://www.nutrient.io/guides/dws-processor/] [src: https://www.nutrient.io/api/processor-api/].
- Accessibility remediation of PDF backlogs (ADA/PDF/UA) — few hosted APIs offer auto-tagging [src: https://www.nutrient.io/guides/dws-processor/tools-and-api/].

## What makes an RFP a BAD fit
- Mandatory on-prem, private cloud, air-gapped or "data never leaves our tenancy" — route to SDK (self-hosted Document Engine or Managed Cloud) [src: https://www.nutrient.io/sdk/document-engine/] [src: https://github.com/PSPDFKit/nutrient-document-engine-mcp-server].
- FedRAMP/StateRAMP/CJIS or a signed HIPAA BAA as pass/fail — not stated publicly; confirm with Nutrient security before any bid [src: https://trust.nutrient.io/].
- Rich interactive UX on mobile or offline (field apps, pilots' EFBs, on-site annotation) — route to SDK [src: https://www.nutrient.io/api/viewer-api/].
- Human-centric process scope: approvals, routing, case management, intake forms with task assignment, dashboards — route to Workflow (Nutrient Workflow Automation) [src: https://trust.nutrient.io/].
- SharePoint Online/on-prem, Microsoft 365, Power Automate, Nintex connectors, or bulk backfile OCR of millions of TIFFs on the buyer's own servers — route to Low-Code (Document Converter, Document Automation Server, Searchability); New Forest NPA is the reference pattern [src: https://www.nutrient.io/blog/new-forest-case-study/].
- End-user desktop PDF software seats (Adobe Acrobat replacement for staff) — no DWS play [UNVERIFIED — judgement].
- Model-training sensitivity: if the buyer prohibits any vendor use of its data, the response must commit to a no-retention plan; retention-enabled plans use files "to train and evaluate our models" [src: https://www.nutrient.io/guides/dws-processor/privacy/].

## Knowledge gaps in this profile
- No HubSpot, internal Slack or Notion access: DWS customer list, win/loss, actual enterprise contract terms, SLA language, BAA availability and region-pinning options are unknown.
- Zero public customer stories name DWS; all vertical evidence is inferred from Document Engine/SDK stories on the same engine or from sample repos. Treat Tier 2/3 as analogues, not references.
- The `.md` suffix trick returned 404 on every nutrient.io URL tried; content came from HTML pages summarised by a fetch model, so quotations may be lightly paraphrased.
- G2 blocked direct fetch (HTTP 403); SDK review themes come from search snippets and there is no DWS-specific listing [src: https://www.g2.com/products/nutrient-sdk/reviews].
- Uptime SLA, rate limits, maximum file size, per-region data pinning and whether the Data Extraction and Accessibility APIs share the Processor API's deletion policy were not confirmed on the pages read.
- Credit costs, plan sizes and the free-tier limits were deliberately omitted per profile rules; they change and should be checked at pursuit time [src: https://www.nutrient.io/api/pricing/processor-api/].
