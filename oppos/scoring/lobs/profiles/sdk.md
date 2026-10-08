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
- Nutrient SDK (formerly PSPDFKit) is a family of embeddable document components: client-side SDKs for Web (JavaScript/WebAssembly), iOS, Android, Flutter, React Native, MAUI, Windows and Electron; server-side libraries for .NET, Java, Python and Node.js; and Document Engine, a self-hostable document server [src: https://www.nutrient.io/sdk/] [src: https://www.nutrient.io/sdk/pricing/].
- It is sold to teams that build software, not to end users. The buyer embeds viewing, markup, forms, signing, redaction, OCR and collaboration into their own product so they do not have to build or maintain a document layer [src: https://www.nutrient.io/sdk/].
- Platform coverage is confirmed by public PSPDFKit repos for React Native, Flutter, MAUI, Xamarin, Cordova/Ionic, Electron and a Helm chart for Document Engine on Kubernetes [src: https://github.com/PSPDFKit/react-native] [src: https://github.com/PSPDFKit/pspdfkit-flutter] [src: https://github.com/PSPDFKit/pspdfkit-maui-catalog] [src: https://github.com/PSPDFKit/helm-charts].
- RFP relevance: an RFP almost never says "buy a PDF SDK." It says "citizen portal with fillable forms," "case management with annotation and redaction," "field app that works offline," or "replace Adobe licences inside our platform." The SDK is the component that answers those lines inside a larger build [UNVERIFIED — qualifier judgement].

## Core capabilities
- Viewing and rendering of PDF, PDF/A, Office (Word, Excel, PowerPoint) and images (PNG, JPEG, TIFF) in browser and on mobile [src: https://www.nutrient.io/guides/web/] [src: https://www.nutrient.io/sdk/].
- Markup: "17+ comment and markup tools" (ink, text, shapes, stamps, links, media, redaction) with Instant JSON and XFDF interchange [src: https://www.nutrient.io/sdk/] [src: https://www.nutrient.io/guides/web/].
- Forms: fill, create, validate and submit PDF forms "programmatically or via UI" [src: https://www.nutrient.io/sdk/] [src: https://www.nutrient.io/guides/web/].
- Signatures: electronic signatures and certificate-based digital signatures, including "Headless PDF digital signing" and HSM integrations on Document Engine [src: https://www.nutrient.io/guides/web/] [src: https://www.nutrient.io/guides/document-engine/].
- Redaction: "Permanently remove sensitive text, images, and data," including search- and regex-driven redaction server-side [src: https://www.nutrient.io/sdk/] [src: https://www.nutrient.io/guides/document-engine/].
- Editing: merge, split, rotate, text replacement, Bates numbering, content editing [src: https://www.nutrient.io/guides/web/].
- OCR and data extraction: "Extract text from scans in 30+ languages" [src: https://www.nutrient.io/sdk/].
- Document comparison (visual, text and AI-assisted), measurement tools, layers [src: https://www.nutrient.io/sdk/] [src: https://www.nutrient.io/guides/web/].
- Collaboration: Instant real-time annotation sync with JWT client authentication [src: https://www.nutrient.io/guides/web/] [src: https://www.nutrient.io/guides/document-engine/].
- Document Authoring: a TypeScript WYSIWYG editor to "Open, view, and edit DOCX files" in-browser or headless in Node.js, with LLM-proposed edits surfaced as tracked changes [src: https://www.nutrient.io/sdk/document-authoring/].
- AI Assistant: a Docker-distributed toolkit with a chat agent and a document-editing agent (summaries, translation, extraction, form filling, redaction); bring-your-own LLM key (OpenAI or Azure OpenAI named) and backend call to purge chat/document data [src: https://www.nutrient.io/sdk/ai-assistant/].
- Agent/MCP surface: an MIT-licensed PDF-editor MCP connector built on the Web Viewer, a Document Engine MCP server for self-hosted agent workflows, and a local PDF-to-Markdown CLI [src: https://github.com/PSPDFKit/nutrient-pdf-editor-mcp] [src: https://github.com/PSPDFKit/nutrient-document-engine-mcp-server] [src: https://github.com/PSPDFKit/pdf-to-markdown].
- Accessibility: viewer UI at "WCAG 2.1 Level AAA conformance for text contrast, and at least AA conformance for icons"; tagged PDF/PDF/UA rendered as WCAG 2.1-compliant HTML; NVDA/JAWS and full keyboard operation [src: https://www.nutrient.io/guides/web/viewer/accessibility/]. Product pages also claim "WCAG 2.2 compliance built in" [src: https://www.nutrient.io/sdk/].

## Deployment options
- Client-side only: Web SDK runs fully in the browser via WebAssembly with no server dependency; mobile SDKs run on-device [src: https://www.nutrient.io/guides/web/] [src: https://www.nutrient.io/sdk/].
- Self-hosted Document Engine: Docker and Kubernetes (Helm), on AWS, GCP, Azure or on-premises; horizontal scaling; JWT auth; customer-controlled storage [src: https://www.nutrient.io/guides/document-engine/] [src: https://github.com/PSPDFKit/helm-charts].
- Managed Cloud: "A private setup without the upkeep," a dedicated Nutrient-operated instance per customer [src: https://www.nutrient.io/sdk/document-engine/].
- Hosted alternative: DWS Viewer API, where "You do not need to run Document Engine or viewer infrastructure" (see DWS profile) [src: https://www.nutrient.io/api/viewer-api/].
- Air-gapped: pricing page states "full air-gapped deployment capability"; the Document Engine product page itself does not repeat this, so confirm scope during pursuit [src: https://www.nutrient.io/sdk/pricing/] [src: https://www.nutrient.io/sdk/document-engine/].

## Security & compliance
- SOC 2 Type 2 and SOC 3 are stated for "SDKs," with a report titled "Nutrient SOC 2 Type 2 (SDKs, Cloud, and Workflow)"; "End User Tools are not yet in scope for SOC 2" [src: https://trust.nutrient.io/].
- Annual third-party penetration testing, disaster-recovery plan, subprocessor list, bug bounty, customer data deletion on request [src: https://trust.nutrient.io/].
- Hosting regions for Nutrient-run infrastructure: AWS (United States, Germany, Ireland) and Google Cloud (United States) [src: https://trust.nutrient.io/].
- Document-level controls: encryption, password protection, digital signatures, redaction, role-based permissions, "redaction with audit trails," PDF/A-1/-2/-3 conversion [src: https://www.nutrient.io/sdk/] [src: https://www.nutrient.io/sdk/solutions/government/].
- Accessibility targets: Nutrient's accessibility solution page says the viewer helps meet Section 508 and EN 301 549 targets (seen via search snippet) [src: https://www.nutrient.io/sdk/solutions/accessibility/].
- NOT stated on the pages read: FedRAMP, StateRAMP, CJIS, HIPAA attestation (only "help meet"), ISO 27001 certificate, a published VPAT/ACR [src: https://trust.nutrient.io/] [src: https://www.nutrient.io/sdk/solutions/government/]. Treat any RFP that hard-requires these as a gap to confirm with Nutrient security, not as a pass.

## Licensing & pricing posture
- Component-based: customers "pay only for what you need," priced by components licensed, deployment model and scale; sold as annual subscriptions with multiyear terms, including "access, updates, and support" [src: https://www.nutrient.io/sdk/pricing/].
- 30-day full-feature trial with no license key or payment info [src: https://www.nutrient.io/sdk/pricing/].
- OEM/SaaS: "OEM licensing provides unlimited deployment under a single agreement with no per-customer overhead" — this is the clause that makes the oem play possible [src: https://www.nutrient.io/sdk/pricing/].
- Usage-based option via DWS Viewer API and Processor API for SaaS teams [src: https://www.nutrient.io/sdk/pricing/].
- Enterprise: custom quotes from Solutions Engineering; add-on support tiers with "dedicated engineers, faster response times, and named technical contacts" [src: https://www.nutrient.io/sdk/pricing/].
- Reviewer friction: G2 and aggregator snippets cite per-module pricing complexity and cost as the most common con [src: https://www.g2.com/products/nutrient-sdk/reviews]. Expect RFP pricing schedules built around "per user" or "per seat" to need translation.

## Proven verticals (with evidence)
Tier 1 — repeated, named, outcome-bearing stories
- Legal and legal-tech: Harvey (Web SDK + self-hosted Document Engine; ~50% MoM document growth; 1,000+ customers, 74,000 users, 58+ countries) [src: https://www.nutrient.io/blog/scaling-legal-document-workflows-harvey/]; Page (VA disability case files of 4,000–50,000 pages) [src: https://www.nutrient.io/blog/web-pdf-sdk-legal-review/]; Mobile Helix (iOS/Android annotation and signatures for 250–3,000-lawyer firms) [src: https://www.nutrient.io/blog/mobile-helix-nutrient-sdk-ios-android/]; Athena Intelligence (Web SDK; hybrid cloud/on-prem for regulated Fortune 500) [src: https://www.nutrient.io/blog/athena-nutrient-enterprise-ai-compliance/].
- Board governance portals: Govenda (iOS 2014, Android 2016, Web 2018) [src: https://www.nutrient.io/blog/case-study-govenda/]; BoardPro (Web SDK + Instant; 2,000+ boards in 30 countries) [src: https://www.nutrient.io/blog/boardpro-board-pack-viewing-annotation/]; Athena Board [src: https://www.nutrient.io/blog/secure-board-management-athena/].
- Accounting, audit, tax and fintech: AuditFile (self-hosted Document Engine in Docker on customer S3; data-residency driven; "One week to production") [src: https://www.nutrient.io/blog/auditfile-self-hosted-pdf-editing/]; Current (Web SDK; tax review) [src: https://www.nutrient.io/blog/current-ai-tax-platform/]; FuseWorks (Web SDK; signing for 150 UK firms) [src: https://www.nutrient.io/blog/fuseworks-nutrient-web-sdk-document-signing/]; Under (Web SDK; 400+ field financial forms) [src: https://www.nutrient.io/blog/secure-financial-documents-under/]; KwikSign (Web SDK; signing) [src: https://www.nutrient.io/blog/kwiksign-case-study-cut-dev-time-six-months/].
- Construction and field operations: CMiC (iOS/Android/Web; drawing management and slip-sheeting; 10+ year partner) [src: https://www.nutrient.io/blog/cmic-transforms-construction-project/]; Capmo (mobile forms, annotations, signatures for site inspections) [src: https://www.nutrient.io/blog/capmo-native-mobile-pdf-sdk-nutrient/]; an unnamed construction firm chosen for offline annotation on no-signal sites [src: https://www.nutrient.io/blog/construction-firm-digitizes-blueprints/].

Tier 2 — single strong story or logo-level evidence
- Aviation / safety-critical: Lufthansa Systems Lido mPilot (iOS SDK; charts to pilots, licensed to other carriers) [src: https://www.nutrient.io/blog/lufthansa-nutrient-pdf-rendering/]; the SDK page cites IBM with "34,000+ commercial pilots" [src: https://www.nutrient.io/sdk/].
- Education: Subject (K–12; 5x growth, 50,000 students onboarded in a day) [src: https://www.nutrient.io/blog/subject-interactive-learning-nutrient-pdf-sdk/]; Faria Education Group named as a customer logo [src: https://www.nutrient.io/sdk/].
- Content/document platforms: Box (mobile previewing, Apple Vision Pro) [src: https://www.nutrient.io/blog/box-document-integrations/]; SuiteFiles (Web SDK; customers cancel standalone PDF subscriptions) [src: https://www.nutrient.io/blog/suitefiles-eliminates-subscription-fatigue-with-web-sdk/]; Dropbox and DocuSign ("200M+ users") listed as customers [src: https://www.nutrient.io/sdk/].
- Transportation/logistics imaging: RoadOne (GdPicture.NET, Nutrient's .NET imaging SDK; replaced LeadTools) [src: https://www.nutrient.io/blog/imaging-efficiency-gdpicture-roadone/].

Tier 3 — claimed but thin on public detail
- Government: the government solutions page claims forms "for more than 1,000 municipalities" via Digitales Amt and names European Patent Office, Bloomberg, UBS, UniCredit and DocuSign; no full public-sector SDK case study was readable [src: https://www.nutrient.io/sdk/solutions/government/]. Note: New Forest National Park Authority is a real public-sector story but uses Document Automation Server (Low-Code LOB), not the SDK [src: https://www.nutrient.io/blog/new-forest-case-study/].
- Healthcare: G2 snippets list Hospital & Health Care reviewers and the SDK page lists healthcare among regulated industries, but no healthcare case study was found [src: https://www.g2.com/products/nutrient-sdk/reviews] [src: https://www.nutrient.io/sdk/].

## RFP pattern matches
1. `key: embedded_viewer_annotation_in_custom_app` — Likely play: partner_si or oem.
   - Signals: "document viewer," "annotate/markup," "redline," "mobile and web parity," "no plug-ins," "offline access," named frameworks (React, Angular, iOS, Android, Flutter, React Native).
   - Capabilities: Web/mobile SDKs, 17+ markup tools, Instant JSON cross-platform annotations, offline WASM/on-device rendering [src: https://www.nutrient.io/sdk/] [src: https://www.nutrient.io/guides/web/].
   - Evidence: CMiC, Capmo, Box, Govenda, Subject [src: https://www.nutrient.io/blog/cmic-transforms-construction-project/] [src: https://www.nutrient.io/blog/box-document-integrations/].
2. `key: citizen_forms_and_esign_portal` — Likely play: partner_si (civic-tech vendor or SI primes); direct only if agency has in-house dev.
   - Signals: "fillable forms," "e-signature," "submit online," "ADA/Section 508," "replace paper forms," "permit/licence application."
   - Capabilities: form creation/fill/validate/submit, electronic and digital signatures, accessibility, PDF/A output [src: https://www.nutrient.io/guides/web/] [src: https://www.nutrient.io/sdk/solutions/government/].
   - Evidence: Under, FuseWorks, KwikSign, Digitales Amt claim [src: https://www.nutrient.io/blog/secure-financial-documents-under/] [src: https://www.nutrient.io/sdk/solutions/government/].
3. `key: records_redaction_and_public_release` — Likely play: partner_si or oem (records/FOIA/case-management vendor embeds).
   - Signals: "FOIA/public records," "redaction," "PII removal," "audit trail," "Bates numbering," "discovery."
   - Capabilities: permanent redaction (UI and regex/search server-side), Bates numbering, redaction audit trails, comparison [src: https://www.nutrient.io/guides/document-engine/] [src: https://www.nutrient.io/guides/web/] [src: https://www.nutrient.io/sdk/solutions/government/].
   - Evidence: Athena Intelligence, Page, Harvey [src: https://www.nutrient.io/blog/athena-nutrient-enterprise-ai-compliance/].
4. `key: self_hosted_document_server_data_residency` — Likely play: direct or partner_si.
   - Signals: "on-premises," "data must not leave our environment," "private cloud," "Kubernetes," "sovereign," "air-gapped."
   - Capabilities: Document Engine in Docker/Helm on customer infrastructure or Managed Cloud dedicated instance; customer storage; JWT [src: https://www.nutrient.io/guides/document-engine/] [src: https://www.nutrient.io/sdk/document-engine/] [src: https://github.com/PSPDFKit/helm-charts].
   - Evidence: AuditFile (30% international revenue protected), Harvey, Athena Intelligence [src: https://www.nutrient.io/blog/auditfile-self-hosted-pdf-editing/].
5. `key: realtime_collaboration_review` — Likely play: oem or partner_si.
   - Signals: "simultaneous review," "shared annotations," "comments synced across devices," "board pack," "collaborative audit."
   - Capabilities: Instant real-time sync, collaboration permissions [src: https://www.nutrient.io/guides/document-engine/] [src: https://www.nutrient.io/guides/web/].
   - Evidence: BoardPro, AuditFile [src: https://www.nutrient.io/blog/boardpro-board-pack-viewing-annotation/].
6. `key: ai_document_assistant_in_regulated_app` — Likely play: partner_si (AI vendor or SI primes).
   - Signals: "summarise/translate documents," "AI extraction with citations," "chat with documents," "bring our own LLM," "AI edits with human approval."
   - Capabilities: AI Assistant (self-hosted container, BYO LLM, data purge), Document Authoring tracked-change AI edits, MCP servers [src: https://www.nutrient.io/sdk/ai-assistant/] [src: https://www.nutrient.io/sdk/document-authoring/] [src: https://github.com/PSPDFKit/nutrient-document-engine-mcp-server].
   - Evidence: Harvey, Athena Intelligence, Current, Page [src: https://www.nutrient.io/blog/current-ai-tax-platform/].

Plays, in brief: direct = Nutrient responds (only when the RFP is literally for a document SDK/server or the buyer builds in-house); partner_si = an integrator primes and embeds Nutrient (signal: SOW for a custom portal/case system, named SI, "respondent may propose COTS components"); oem = a software vendor already licenses and resells (signal: RFP for a board portal, legal DMS, construction PM suite where a Nutrient-powered vendor is a likely bidder) [UNVERIFIED — qualifier framework; plays themselves are supported by the OEM clause at src: https://www.nutrient.io/sdk/pricing/].

## Competitive positioning
- Nutrient's own comparison names Apryse (PDFTron) as the main full-platform rival ("collaboration is DIY"), Foxit as "Traditional enterprise with add-on architecture," Syncfusion as broad but shallow, IronPDF as backend-only .NET, ComPDFKit as low-cost with "elevated vendor risk" [src: https://www.nutrient.io/blog/enterprise-pdf-sdks/].
- Reviewer sentiment: G2 snippets show Nutrient at 4.7/5 on 65 reviews versus Apryse at 4.2/5 on 121, with Nutrient praised for reliability, ease of use and support, and criticised on price and per-module licensing [src: https://www.g2.com/compare/apryse-pdf-sdk-vs-nutrient-sdk] [src: https://www.g2.com/products/nutrient-sdk/reviews].
- The most common displaced incumbent in the stories is not a vendor but open-source viewers (PDF.js-class) that failed on large files, redaction or support: Page, Harvey, Athena Intelligence, Current, Subject [src: https://www.nutrient.io/blog/web-pdf-sdk-legal-review/] [src: https://www.nutrient.io/blog/scaling-legal-document-workflows-harvey/].
- Adobe Acrobat/Document Cloud and Foxit desktop suites are the end-user products RFPs usually name; Nutrient is not a desktop editor and should be positioned as the embedded component that removes those seat licences (SuiteFiles outcome) [src: https://www.nutrient.io/blog/suitefiles-eliminates-subscription-fatigue-with-web-sdk/] [UNVERIFIED — Adobe/Foxit role is general knowledge].

## What makes an RFP a GOOD fit
- A custom or vendor-built application is being procured and the spec enumerates document behaviours (view, annotate, fill, sign, redact, compare, OCR) across web and mobile [src: https://www.nutrient.io/sdk/].
- Data residency, on-prem or private-cloud hosting is mandatory and the buyer has DevOps capacity [src: https://www.nutrient.io/sdk/document-engine/].
- Accessibility (WCAG/PDF/UA) and records standards (PDF/A) are scored requirements [src: https://www.nutrient.io/guides/web/viewer/accessibility/] [src: https://www.nutrient.io/sdk/solutions/government/].
- Scale language: tens of thousands of pages per file, millions of documents, concurrent users [src: https://www.nutrient.io/blog/web-pdf-sdk-legal-review/] [src: https://www.nutrient.io/sdk/document-engine/].
- An SI or ISV is named or implied as prime, and "COTS components permitted" appears — Nutrient's job is to get on their bill of materials.
- SOC 2 Type 2 is the security bar (not FedRAMP) [src: https://trust.nutrient.io/].

## What makes an RFP a BAD fit
- Pure end-user software: "licences for Adobe Acrobat," desktop PDF editors, seat-based e-signature SaaS with no integration — no Nutrient SDK play; decline or route to a reseller [UNVERIFIED — judgement].
- FedRAMP/StateRAMP/CJIS/HIPAA BAA stated as mandatory pass/fail — not stated on Nutrient public pages; flag to security before pursuing [src: https://trust.nutrient.io/].
- Process-centric scope (approvals, routing, case/intake management, dashboards, HR/finance forms with workflow) — route to Workflow (Nutrient Workflow Automation, in SOC 2 scope) [src: https://trust.nutrient.io/].
- SharePoint/Microsoft 365, Power Automate, Nintex, bulk server conversion, archive OCR or TIFF-to-PDF backfile projects — route to Low-Code (Document Converter, Document Automation Server, Searchability); New Forest NPA is the model story [src: https://www.nutrient.io/blog/new-forest-case-study/].
- Headless, no-UI batch conversion/OCR/signing with no appetite to host — route to DWS (hosted REST API) [src: https://www.nutrient.io/api/viewer-api/].
- Buyer has no engineering team and no named integrator — the SDK cannot be consumed; route to DWS Viewer API or Low-Code.

## Knowledge gaps in this profile
- No HubSpot, internal Slack or Notion access: win/loss history, existing public-sector customers under NDA, partner/SI roster, OEM list and actual pricing bands are unknown.
- No public-sector SDK case study was readable; government proof rests on one solutions page claim [src: https://www.nutrient.io/sdk/solutions/government/].
- The `.md` suffix trick returned 404 on every nutrient.io page tried; summaries came from the HTML pages via a fetch model, so phrasing may be paraphrased.
- G2 blocked direct fetch (HTTP 403); rating and review themes come from search-engine snippets of the G2 pages, not the pages themselves [src: https://www.g2.com/products/nutrient-sdk/reviews].
- Air-gapped support, VPAT/ACR availability, HIPAA attestation and ISO 27001 status were not confirmed on the pages read.
- Document Authoring, AI Assistant and MCP tooling have no public customer stories yet; evidence is product pages and repos only.
- Customer logos on the SDK page (Disney, Autodesk, UBS, Dropbox, IBM, FC Bayern München) have no readable story behind them; treat as logo-level only [src: https://www.nutrient.io/sdk/].
