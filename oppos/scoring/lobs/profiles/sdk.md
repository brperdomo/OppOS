---
lob: sdk
depth: full
version: 1
generated_at: 2026-10-08
generated_by: research agent (public sources)
sources:
  - https://www.nutrient.io/sdk/
  - https://www.nutrient.io/sdk/pricing/
  - https://www.nutrient.io/sdk/document-engine/
  - https://www.nutrient.io/sdk/document-authoring/
  - https://www.nutrient.io/sdk/ai-assistant/
  - https://www.nutrient.io/sdk/solutions/government/
  - https://www.nutrient.io/sdk/solutions/accessibility/
  - https://www.nutrient.io/guides/web/
  - https://www.nutrient.io/guides/web/viewer/accessibility/
  - https://www.nutrient.io/guides/document-engine/
  - https://www.nutrient.io/api/viewer-api/
  - https://trust.nutrient.io/
  - https://www.nutrient.io/blog/categories/customer-stories/
  - https://www.nutrient.io/blog/case-study-govenda/
  - https://www.nutrient.io/blog/web-pdf-sdk-legal-review/
  - https://www.nutrient.io/blog/athena-nutrient-enterprise-ai-compliance/
  - https://www.nutrient.io/blog/fuseworks-nutrient-web-sdk-document-signing/
  - https://www.nutrient.io/blog/current-ai-tax-platform/
  - https://www.nutrient.io/blog/auditfile-self-hosted-pdf-editing/
  - https://www.nutrient.io/blog/capmo-native-mobile-pdf-sdk-nutrient/
  - https://www.nutrient.io/blog/subject-interactive-learning-nutrient-pdf-sdk/
  - https://www.nutrient.io/blog/lufthansa-nutrient-pdf-rendering/
  - https://www.nutrient.io/blog/scaling-legal-document-workflows-harvey/
  - https://www.nutrient.io/blog/construction-firm-digitizes-blueprints/
  - https://www.nutrient.io/blog/suitefiles-eliminates-subscription-fatigue-with-web-sdk/
  - https://www.nutrient.io/blog/kwiksign-case-study-cut-dev-time-six-months/
  - https://www.nutrient.io/blog/mobile-helix-nutrient-sdk-ios-android/
  - https://www.nutrient.io/blog/cmic-transforms-construction-project/
  - https://www.nutrient.io/blog/boardpro-board-pack-viewing-annotation/
  - https://www.nutrient.io/blog/secure-financial-documents-under/
  - https://www.nutrient.io/blog/secure-board-management-athena/
  - https://www.nutrient.io/blog/box-document-integrations/
  - https://www.nutrient.io/blog/imaging-efficiency-gdpicture-roadone/
  - https://www.nutrient.io/blog/new-forest-case-study/
  - https://www.nutrient.io/blog/enterprise-pdf-sdks/
  - https://www.g2.com/products/nutrient-sdk/reviews
  - https://www.g2.com/compare/apryse-pdf-sdk-vs-nutrient-sdk
  - https://github.com/PSPDFKit/react-native
  - https://github.com/PSPDFKit/pspdfkit-flutter
  - https://github.com/PSPDFKit/pspdfkit-maui-catalog
  - https://github.com/PSPDFKit/helm-charts
  - https://github.com/PSPDFKit/nutrient-pdf-editor-mcp
  - https://github.com/PSPDFKit/nutrient-document-engine-mcp-server
  - https://github.com/PSPDFKit/pdf-to-markdown
---
# Nutrient SDK — Capability Profile for RFP Qualification

## What it is
- Nutrient SDK (formerly PSPDFKit) is a family of embeddable document components: client SDKs for Web (JavaScript/WebAssembly), iOS, Android, Flutter, React Native, MAUI, Windows and Electron; server libraries for .NET, Java, Python and Node.js; and Document Engine, a self-hostable document server [src: https://www.nutrient.io/sdk/] [src: https://www.nutrient.io/sdk/pricing/].
- Sold to teams that build software, not end users: the buyer embeds viewing, markup, forms, signing, redaction, OCR and collaboration into its own product [src: https://www.nutrient.io/sdk/].
- Public PSPDFKit repos confirm React Native, Flutter, MAUI and Kubernetes (Helm) coverage [src: https://github.com/PSPDFKit/react-native] [src: https://github.com/PSPDFKit/pspdfkit-flutter] [src: https://github.com/PSPDFKit/pspdfkit-maui-catalog] [src: https://github.com/PSPDFKit/helm-charts].
- An RFP almost never says "buy a PDF SDK." It says "citizen portal with fillable forms," "case system with redaction," or "field app that works offline"; the SDK is the component inside a larger build [UNVERIFIED — qualifier judgement].

## Core capabilities
- Rendering of PDF, PDF/A, Office (Word, Excel, PowerPoint) and images in browser and on device [src: https://www.nutrient.io/guides/web/].
- Markup: "17+ comment and markup tools," Instant JSON and XFDF interchange [src: https://www.nutrient.io/sdk/] [src: https://www.nutrient.io/guides/web/].
- Forms: fill, create, validate and submit "programmatically or via UI" [src: https://www.nutrient.io/sdk/].
- Signatures: electronic and certificate-based digital signing, "Headless PDF digital signing," HSM integrations on Document Engine [src: https://www.nutrient.io/guides/web/] [src: https://www.nutrient.io/guides/document-engine/].
- Redaction: "Permanently remove sensitive text, images, and data," including search/regex redaction server-side [src: https://www.nutrient.io/sdk/] [src: https://www.nutrient.io/guides/document-engine/].
- Editing (merge, split, rotate, text replacement, Bates numbering), OCR "in 30+ languages," comparison, measurement, layers; Instant real-time annotation sync with JWT authentication [src: https://www.nutrient.io/guides/web/] [src: https://www.nutrient.io/sdk/].
- Document Authoring: WYSIWYG editor to "Open, view, and edit DOCX files," in-browser or headless Node.js; LLM edits surface as tracked changes [src: https://www.nutrient.io/sdk/document-authoring/].
- AI Assistant: Docker-distributed chat and editing agents; bring-your-own LLM key; backend call to purge chat and document data [src: https://www.nutrient.io/sdk/ai-assistant/].
- Agent surface: PDF-editor MCP connector, Document Engine MCP server, local PDF-to-Markdown CLI [src: https://github.com/PSPDFKit/nutrient-pdf-editor-mcp] [src: https://github.com/PSPDFKit/nutrient-document-engine-mcp-server] [src: https://github.com/PSPDFKit/pdf-to-markdown].
- Accessibility: UI at "WCAG 2.1 Level AAA conformance for text contrast, and at least AA conformance for icons"; tagged PDF/UA rendered as WCAG 2.1-compliant HTML; NVDA/JAWS and keyboard operation [src: https://www.nutrient.io/guides/web/viewer/accessibility/]; product page claims "WCAG 2.2 compliance built in" [src: https://www.nutrient.io/sdk/].

## Deployment options
- Client-side only: Web SDK runs in-browser via WebAssembly with no server; mobile SDKs run on device [src: https://www.nutrient.io/guides/web/].
- Self-hosted Document Engine: Docker and Kubernetes (Helm) on AWS, GCP, Azure or on-premises; horizontal scaling; customer-controlled storage [src: https://www.nutrient.io/guides/document-engine/].
- Managed Cloud: "A private setup without the upkeep," a dedicated Nutrient-operated instance per customer [src: https://www.nutrient.io/sdk/document-engine/].
- Hosted alternative: DWS Viewer API, where "You do not need to run Document Engine or viewer infrastructure" (see DWS profile) [src: https://www.nutrient.io/api/viewer-api/].
- Air-gapped: pricing page states "full air-gapped deployment capability"; confirm scope during pursuit [src: https://www.nutrient.io/sdk/pricing/].

## Security & compliance
- "SOC 2 Type 2, SOC 3" stated for SDKs; report titled "Nutrient SOC 2 Type 2 (SDKs, Cloud, and Workflow)"; "End User Tools are not yet in scope for SOC 2" [src: https://trust.nutrient.io/].
- Annual third-party penetration testing, DR plan, subprocessor list, bug bounty; Nutrient-run infrastructure on AWS (United States, Germany, Ireland) and Google Cloud (United States) [src: https://trust.nutrient.io/].
- Document controls: encryption, password protection, role-based permissions, "redaction with audit trails," PDF/A-1/-2/-3 conversion [src: https://www.nutrient.io/sdk/solutions/government/].
- Accessibility page says the viewer helps meet Section 508 and EN 301 549 targets (search snippet) [src: https://www.nutrient.io/sdk/solutions/accessibility/].
- NOT stated on pages read: FedRAMP, StateRAMP, CJIS, HIPAA attestation (only "help meet"), ISO 27001 certificate, published VPAT/ACR [src: https://trust.nutrient.io/] [src: https://www.nutrient.io/sdk/solutions/government/]. Treat these as gaps to confirm, not passes.

## Licensing & pricing posture
- Component-based: "pay only for what you need," priced by components, deployment model and scale; annual subscriptions with multiyear terms, including "access, updates, and support" [src: https://www.nutrient.io/sdk/pricing/].
- 30-day full-feature trial, no license key or payment info [src: https://www.nutrient.io/sdk/pricing/].
- OEM/SaaS: "OEM licensing provides unlimited deployment under a single agreement with no per-customer overhead" — the clause that enables the oem play [src: https://www.nutrient.io/sdk/pricing/].
- Usage-based path via DWS APIs; enterprise quotes from Solutions Engineering; add-on support tiers with "dedicated engineers, faster response times, and named technical contacts" [src: https://www.nutrient.io/sdk/pricing/].
- Per-module pricing complexity and cost are the most common G2 cons [src: https://www.g2.com/products/nutrient-sdk/reviews]; per-seat RFP price schedules will need translation.

## Proven verticals (with evidence)
Tier 1 — repeated, named, outcome-bearing stories
- Legal and legal-tech: Harvey (Web SDK + self-hosted Document Engine; ~50% MoM document growth) [src: https://www.nutrient.io/blog/scaling-legal-document-workflows-harvey/]; Page (VA case files of 4,000–50,000 pages) [src: https://www.nutrient.io/blog/web-pdf-sdk-legal-review/]; Mobile Helix (iOS/Android for large law firms) [src: https://www.nutrient.io/blog/mobile-helix-nutrient-sdk-ios-android/]; Athena Intelligence (hybrid cloud/on-prem for regulated Fortune 500) [src: https://www.nutrient.io/blog/athena-nutrient-enterprise-ai-compliance/].
- Board governance portals: Govenda (iOS 2014, Android 2016, Web 2018) [src: https://www.nutrient.io/blog/case-study-govenda/]; BoardPro (Web SDK + Instant; 2,000+ boards, 30 countries) [src: https://www.nutrient.io/blog/boardpro-board-pack-viewing-annotation/]; Athena Board [src: https://www.nutrient.io/blog/secure-board-management-athena/].
- Accounting, audit, tax, fintech: AuditFile (self-hosted Document Engine on customer S3) [src: https://www.nutrient.io/blog/auditfile-self-hosted-pdf-editing/]; Current [src: https://www.nutrient.io/blog/current-ai-tax-platform/]; FuseWorks (signing) [src: https://www.nutrient.io/blog/fuseworks-nutrient-web-sdk-document-signing/]; Under (400+ field forms) [src: https://www.nutrient.io/blog/secure-financial-documents-under/]; KwikSign [src: https://www.nutrient.io/blog/kwiksign-case-study-cut-dev-time-six-months/].
- Construction and field work: CMiC (iOS/Android/Web drawing management) [src: https://www.nutrient.io/blog/cmic-transforms-construction-project/]; Capmo (mobile forms, signatures) [src: https://www.nutrient.io/blog/capmo-native-mobile-pdf-sdk-nutrient/]; an unnamed firm chosen for offline annotation [src: https://www.nutrient.io/blog/construction-firm-digitizes-blueprints/].

Tier 2 — single strong story or logo-level
- Aviation: Lufthansa Systems Lido mPilot (iOS SDK; charts to pilots) [src: https://www.nutrient.io/blog/lufthansa-nutrient-pdf-rendering/]; IBM cited with "34,000+ commercial pilots" [src: https://www.nutrient.io/sdk/].
- Education: Subject (K–12; 5x growth) [src: https://www.nutrient.io/blog/subject-interactive-learning-nutrient-pdf-sdk/]; Faria Education Group logo [src: https://www.nutrient.io/sdk/].
- Content platforms: Box (mobile previewing) [src: https://www.nutrient.io/blog/box-document-integrations/]; SuiteFiles (customers cancel standalone PDF subscriptions) [src: https://www.nutrient.io/blog/suitefiles-eliminates-subscription-fatigue-with-web-sdk/]; Dropbox and DocuSign logos [src: https://www.nutrient.io/sdk/].
- Logistics imaging: RoadOne (GdPicture.NET; replaced LeadTools) [src: https://www.nutrient.io/blog/imaging-efficiency-gdpicture-roadone/].

Tier 3 — claimed, thin public detail
- Government: solutions page claims forms "for more than 1,000 municipalities" via Digitales Amt and names European Patent Office, Bloomberg, UBS, UniCredit; no full public-sector SDK story was readable [src: https://www.nutrient.io/sdk/solutions/government/]. New Forest National Park Authority used Document Automation Server (Low-Code LOB) [src: https://www.nutrient.io/blog/new-forest-case-study/].
- Healthcare: G2 snippets list Hospital & Health Care reviewers only [src: https://www.g2.com/products/nutrient-sdk/reviews].

## RFP pattern matches
1. `key: embedded_viewer_annotation_in_custom_app` — play: partner_si or oem.
   - Signals: "document viewer," "annotate/markup," "web and mobile parity," "offline access," named frameworks (React, iOS, Android, Flutter).
   - Capabilities: Web/mobile SDKs, markup tools, Instant JSON, on-device rendering [src: https://www.nutrient.io/guides/web/].
   - Evidence: CMiC, Capmo, Box, Govenda, Subject [src: https://www.nutrient.io/blog/cmic-transforms-construction-project/].
2. `key: citizen_forms_and_esign_portal` — play: partner_si (civic-tech vendor or SI primes); direct only if the agency builds in-house.
   - Signals: "fillable forms," "e-signature," "submit online," "ADA/Section 508," "replace paper forms," "permit/licence application."
   - Capabilities: forms, electronic and digital signatures, accessibility, PDF/A [src: https://www.nutrient.io/guides/web/] [src: https://www.nutrient.io/sdk/solutions/government/].
   - Evidence: Under, FuseWorks, KwikSign, Digitales Amt claim [src: https://www.nutrient.io/blog/secure-financial-documents-under/] [src: https://www.nutrient.io/sdk/solutions/government/].
3. `key: records_redaction_and_public_release` — play: partner_si or oem (records/FOIA/case-management vendor embeds).
   - Signals: "FOIA/public records," "redaction," "PII removal," "audit trail," "Bates numbering," "discovery."
   - Capabilities: permanent redaction (UI and server regex), Bates numbering, audit trails, comparison [src: https://www.nutrient.io/guides/document-engine/] [src: https://www.nutrient.io/sdk/solutions/government/].
   - Evidence: Athena Intelligence, Page, Harvey [src: https://www.nutrient.io/blog/athena-nutrient-enterprise-ai-compliance/].
4. `key: self_hosted_document_server_data_residency` — play: direct or partner_si.
   - Signals: "on-premises," "data must not leave our environment," "private cloud," "Kubernetes," "sovereign," "air-gapped."
   - Capabilities: Document Engine via Docker/Helm or Managed Cloud dedicated instance; customer storage; JWT [src: https://www.nutrient.io/sdk/document-engine/] [src: https://github.com/PSPDFKit/helm-charts].
   - Evidence: AuditFile, Harvey, Athena Intelligence [src: https://www.nutrient.io/blog/auditfile-self-hosted-pdf-editing/].
5. `key: realtime_collaboration_review` — play: oem or partner_si.
   - Signals: "simultaneous review," "shared annotations synced across devices," "board pack," "collaborative audit."
   - Capabilities: Instant sync, collaboration permissions [src: https://www.nutrient.io/guides/document-engine/].
   - Evidence: BoardPro, AuditFile [src: https://www.nutrient.io/blog/boardpro-board-pack-viewing-annotation/].
6. `key: ai_document_assistant_in_regulated_app` — play: partner_si (AI vendor or SI primes).
   - Signals: "summarise/translate documents," "AI extraction with citations," "chat with documents," "bring our own LLM," "AI edits with human approval."
   - Capabilities: AI Assistant (self-hosted, BYO LLM, data purge), Document Authoring tracked-change AI edits, MCP servers [src: https://www.nutrient.io/sdk/ai-assistant/] [src: https://www.nutrient.io/sdk/document-authoring/].
   - Evidence: Harvey, Athena Intelligence, Current [src: https://www.nutrient.io/blog/current-ai-tax-platform/].

Plays: direct = Nutrient responds (RFP is literally for a document SDK/server, or the buyer builds in-house); partner_si = an integrator primes and embeds Nutrient (signals: custom portal/case-system SOW, named SI, "COTS components permitted"); oem = a vendor licenses and resells (signals: board portal, legal DMS or construction PM RFP where a Nutrient-powered vendor is a likely bidder) [src: https://www.nutrient.io/sdk/pricing/] [UNVERIFIED — play framework is qualifier judgement].

## Competitive positioning
- Nutrient's own comparison names Apryse (PDFTron) as the main rival ("collaboration is DIY"), Foxit as "Traditional enterprise with add-on architecture," Syncfusion as broad but shallow, IronPDF as backend-only .NET, ComPDFKit as low-cost with "elevated vendor risk" [src: https://www.nutrient.io/blog/enterprise-pdf-sdks/].
- G2 snippets show Nutrient at 4.7/5 on 65 reviews versus Apryse at 4.2/5 on 121; praised for reliability and support, criticised on price [src: https://www.g2.com/compare/apryse-pdf-sdk-vs-nutrient-sdk] [src: https://www.g2.com/products/nutrient-sdk/reviews].
- The usual displaced incumbent is open-source viewers that failed on large files, redaction or support: Page, Harvey, Athena Intelligence, Current, Subject [src: https://www.nutrient.io/blog/web-pdf-sdk-legal-review/].
- RFPs usually name Adobe Acrobat or Foxit desktop seats; position Nutrient as the embedded component that removes those seats (SuiteFiles outcome) [src: https://www.nutrient.io/blog/suitefiles-eliminates-subscription-fatigue-with-web-sdk/] [UNVERIFIED — Adobe/Foxit role is general knowledge].

## What makes an RFP a GOOD fit
- A custom or vendor-built application is being procured and the spec enumerates document behaviours (view, annotate, fill, sign, redact, compare, OCR) across web and mobile [src: https://www.nutrient.io/sdk/].
- Data residency or on-prem is mandatory and the buyer has DevOps capacity [src: https://www.nutrient.io/sdk/document-engine/]; WCAG/PDF/UA and PDF/A are scored requirements [src: https://www.nutrient.io/guides/web/viewer/accessibility/].
- Scale language: tens of thousands of pages per file, millions of documents, concurrent users [src: https://www.nutrient.io/sdk/document-engine/].
- An SI or ISV is prime, or "COTS components permitted" appears [UNVERIFIED — judgement]; SOC 2 Type 2, not FedRAMP, is the security bar [src: https://trust.nutrient.io/].

## What makes an RFP a BAD fit
- Pure end-user software: Acrobat licences, desktop PDF editors, seat-based e-signature SaaS — no SDK play [UNVERIFIED — judgement].
- FedRAMP/StateRAMP/CJIS/HIPAA BAA as pass/fail — not stated publicly; flag to security first [src: https://trust.nutrient.io/].
- Process scope (approvals, routing, case/intake management, dashboards) — route to Workflow (Nutrient Workflow Automation, in SOC 2 scope) [src: https://trust.nutrient.io/].
- SharePoint/Microsoft 365, Power Automate, Nintex, bulk server conversion or TIFF-to-PDF backfile OCR — route to Low-Code (Document Converter, Document Automation Server, Searchability); New Forest NPA is the model [src: https://www.nutrient.io/blog/new-forest-case-study/].
- Headless batch conversion/OCR/signing with no appetite to host — route to DWS [src: https://www.nutrient.io/api/viewer-api/]. No engineering team and no integrator — route to DWS Viewer API or Low-Code [UNVERIFIED — judgement].

## Knowledge gaps in this profile
- No HubSpot, internal Slack or Notion access: win/loss history, NDA'd public-sector customers, partner/SI roster, OEM list and real pricing bands are unknown.
- None of the 34 stories on the index is a public-sector SDK deployment [src: https://www.nutrient.io/blog/categories/customer-stories/]; government proof rests on one solutions page [src: https://www.nutrient.io/sdk/solutions/government/]. SDK-page logos have no readable story [src: https://www.nutrient.io/sdk/].
- The `.md` suffix returned 404 on every nutrient.io page tried; summaries came from HTML via a fetch model, so phrasing may be paraphrased. G2 blocked direct fetch (HTTP 403); rating and themes come from search snippets [src: https://www.g2.com/products/nutrient-sdk/reviews].
- Air-gapped support, VPAT/ACR, HIPAA attestation and ISO 27001 status were not confirmed. Document Authoring, AI Assistant and MCP tooling have no public customer stories.
