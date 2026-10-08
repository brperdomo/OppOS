---
lob: low_code
depth: full
version: 1
generated_at: 2026-10-08
generated_by: catalyst agent
sources:
  - ~/.claude/catalyst-data/document-converter.md
  - ~/.claude/catalyst-data/document-automation-server.md
  - ~/.claude/catalyst-data/document-searchability.md
  - ~/.claude/catalyst-data/adjacent-integrations.md
  - ~/.claude/catalyst-data/internal-knowledge.md
  - ~/.claude/catalyst-data/field-knowledge.md
---
# Nutrient Low-Code / Integrations — Capability Profile for RFP Qualification

## What it is

- The ex-**Muhimbi** (Document Converter, Document Editor) and ex-**Aquaforest** (Document Automation Server, Document Searchability, PDF Connector) products. They add conversion, OCR, watermarking, security, redaction, extraction and tagging to platforms the customer already runs: SharePoint 2007–Subscription Edition and Online, Power Automate / Logic Apps, Nintex, K2, Windows file servers, Azure Storage [src: internal-knowledge.md §1; document-converter.md §1.2].
- Headless/automation-first; Document Editor is the only end-user UI product [src: adjacent-integrations.md §(e)].
- Legacy names persist (connector slug "muhimbi", invoices from Muhimbi Ltd / Aquaforest Ltd); rebrand still backlog Oct 2026 — expect RFPs to use old names [src: internal-knowledge.md §1; field-knowledge.md §FAQ].
- Small-ticket, high-volume business: Document Converter is ~87% of low-code deals; 2025 Online ~$1.12M over 259 orders, SP On-Prem ~$481k over 89 orders; only 19 deals above $25k [src: internal-knowledge.md §8].
- Strategy (Jan 2026): compete on security, governance and on-prem, not generic conversion [src: internal-knowledge.md §8].

## Core capabilities (by product)

**Document Converter Online — Power Automate / Logic Apps / Power Apps / Copilot Studio connector, Nintex Automation Cloud Xtension, K2 broker, REST API, SharePoint Online SPFx app**
- 60+ inputs to PDF or other formats: Office, HTML/URL, images, InfoPath, MSG/EML with attachments, Visio, AutoCAD; outputs include PDF/A-1b/2b/3b, XPS, Office, images [src: document-converter.md §8].
- 33 actions: convert family, Convert to OCRed PDF, zonal OCR text, Extract Text, Extract Key Value Pairs (AI), PDF form import/export, Merge, Split, Secure, Compress, AI-powered and regex Redact, ten watermark types, Copy metadata [src: document-converter.md §3.1, §3.3].
- **Standard (non-premium) connector; available in GCC, not GCC High/DoD** [src: document-converter.md §3.1].
- One subscription covers SPO app, connectors and REST, unlimited users, multi-tenant linking [src: document-converter.md §1.2].

**Document Converter for SharePoint (On-Prem 2007 → SE; Online)**
- In-SharePoint Convert to PDF, merge up to 200 files, SPD/Nintex/K2/Workflow Manager actions [src: document-converter.md §5.1, §6].
- **Real-time watermark and security on Insert / Update / Open** with user, timestamp and IP merge codes, per-library filters; blocks Copy/Move/Preview to stop unwatermarked egress [src: document-converter.md §5.2; field-knowledge.md §Troubleshooting].
- Windows Server 2008–2022; SharePoint WSS 3.0 through SE [src: document-converter.md §1.4].

**Document Converter Services (DCS)**
- Self-hosted Windows service, SOAP/WCF port 41734, clients in .NET/Java/PHP/Ruby/Python/PowerShell, no REST; Base needs Office, Professional Add-On adds Office-free conversion, OCR, KVP, redaction, PDF/A [src: document-converter.md §1.2; field-knowledge.md §FAQ].
- The answer to "zero shared element" / air-gapped requirements [src: document-converter.md §1.2].

**Document Automation Server (DAS, fka Autobahn DX; Content Extraction = Kingfisher)**
- Unattended Windows service: watched folders, schedules, XML jobs, CLI, .NET API, distributed polling, up to 64 cores, ~1,000 pages/hour/core [src: document-automation-server.md §2; internal-knowledge.md §3].
- Steps: OCR (Standard, IRIS 129 languages, GdPicture, Microsoft/Google cloud handwriting), Any File to PDF, PDF/A, PDF/UA (6.0.2606), merge/split, barcode split/rename, Smart and Pattern Redaction, KVP extraction, Detect Signatures, compression, Zip, custom scripts; SharePoint, Azure Storage and mailbox connectors [src: document-automation-server.md §8].
- Content Extraction: rename/split/extract pages by zonal text or barcode, tables to CSV/XLSX [src: document-automation-server.md §11].

**Document Searchability (fka Searchlight / Tagger)**
- **Audit & OCR**: classifies files Fully / Partially / Image-only searchable, OCRs **in place** to PDF or PDF/A on schedule with reporting; targets file shares, SharePoint on-prem/Online, OneDrive, Azure Storage [src: document-searchability.md §2].
- **Tagging**: writes SharePoint columns / Term Store from NLP entities (third-party APIs), taxonomy matching, PDF metadata, form fields, zonal text, barcodes; tags PDF and Office formats [src: document-searchability.md §9; field-knowledge.md §FAQ].

**Document Editor (SharePoint Online, Teams, OneDrive, On-Prem)** — in-browser view, annotate, page edit, forms, selective redaction, DWS digital signing; on-prem runs an older SDK [src: adjacent-integrations.md §(c); field-knowledge.md §FAQ].

**Aquaforest PDF Connector** — hosted, unit-metered PA actions; secondary to Converter [src: internal-knowledge.md §5].

**Adjacent, separate LOB — flag, don't bid:** Documents for Salesforce (generation, redaction, eSign on the record), Document Merge (AppExchange), Nutrient for HubSpot, ServiceNow viewer [src: adjacent-integrations.md §(a), §(b)].

## Deployment options

- **Nutrient-hosted Online**: multi-tenant Azure; regions US, Canada, Europe, Australia (Asia/South America/Germany via Custom); region choice on Enterprise (Professional UNVERIFIED); dedicated servers Nutrient- or customer-hosted on Custom [src: document-converter.md §1.3].
- **Customer SharePoint farm**: WSP moving to SPFx, Conversion Service on an app server [src: internal-knowledge.md §2.1].
- **Customer Windows server / IaaS VM**: DCS, DAS, Searchability. DAS has no SaaS edition; Searchability has an Azure Marketplace VM image; a Nutrient-hosted Searchability SaaS is described internally but UNVERIFIED [src: document-automation-server.md §2; document-searchability.md §2; internal-knowledge.md §4.1].
- **SharePoint Online**: SPFx app distributed directly, not on AppSource; legacy add-in model retired Apr 2026 [src: field-knowledge.md §FAQ, §Recent announcements].

## Security & compliance

- Online is **stateless** (files deleted after the operation), TLS in transit, metadata-only audit logs, published subprocessor list and DPA [src: document-converter.md §1.3].
- **SOC 2 (Online)**: Linear project Completed Sep 2026, Notion marks Online compliant, pen tests ran 2025 and 2026 — but the sales KB says do not claim it, and SharePoint/DCS are marked not SOC 2. Treat as UNVERIFIED pending human confirmation [src: internal-knowledge.md §2.2].
- **HIPAA BAA not signable** — lost a 2025 deal [src: internal-knowledge.md §2.2, §9].
- Connector in **GCC**, not GCC High/DoD/China [src: document-converter.md §3.1].
- On-prem products keep files inside the customer environment [src: document-converter.md §11].
- PDF/A across Converter and DAS; PDF/UA in DAS only (Converter backlog PCOPL-548); Searchability claims FIPS-compliant crypto [src: document-converter.md §8.2; document-automation-server.md §8; internal-knowledge.md §2.4, §4.1].
- Limits: IRM/AIP-protected inputs unsupported everywhere; PDF/A forbids encryption; Tagging NLP sends text to third parties [src: document-converter.md §11; internal-knowledge.md §4.1].
- **Not stated in KB**: FedRAMP, StateRAMP, ISO 27001, Section 508/VPAT, DWS data residency [UNVERIFIED].

## Licensing & pricing posture

- Online is **operation-metered** (one action call = one op; OCR per page; each on-open watermark = one op). Tiers Free / Basic / Professional / Enterprise / Custom; Oct 2026 list $109 / $366 / $549 per month billed annually; OCR and redaction need Enterprise; 5 / 25 / 100 MB per op by tier, Custom up to 500 MB seen [src: document-converter.md §2.1–2.3; field-knowledge.md §FAQ].
- Bulk/custom guidance ~$0.04 per operation in 25k+ blocks [src: field-knowledge.md §FAQ].
- SP On-Prem: Server / Small Farm (up to 3 servers) / Enterprise (all environments); Server ~$1,999/yr, Enterprise "from $9,999"; Professional Add-On is tier-independent [src: field-knowledge.md §FAQ, §Licensing & SKUs].
- DAS and Searchability: per-core subscription, quote only, 14-day trials [src: document-automation-server.md §12; document-searchability.md §10].
- Editor Online: $9 / $17 per user/month, 10-user minimum, redaction needs Pro+ [src: adjacent-integrations.md §(a); field-knowledge.md §FAQ].
- 5% annual renewal uplift; perpetual + M&S persists for legacy holders; resellers carry much of the renewal base; single Integrations SOF switches between Muhimbi Ltd and Aquaforest Ltd [src: field-knowledge.md §Licensing & SKUs, §Personas].

## Proven verticals (with evidence)

- **Tier 1 — Government and regulated finance**: on-prem is "a proven driver of large deals in regulated finance and government"; a large banking InfoPath deal and a multi-million-file migration cited; RTWM and redaction "common in government and regulated industries" [src: internal-knowledge.md §9, §2.5; field-knowledge.md §Use cases].
- **Tier 2 — Partner-led archives (legal, real estate, aviation) and M365 enterprise IT**: archive OCR "often run by partners for real-estate, legal or aviation document stores"; auto-tagging millions of SharePoint documents; InfoPath decommissioning is the most common driver across sectors [src: field-knowledge.md §Use cases].
- **Tier 3 — Healthcare, SMB departments, Salesforce-centric orgs**: HIPAA-sensitive OCR scoped at 20k–25k ops/month but the BAA gap lost a deal; small firms churn on price [src: field-knowledge.md §Use cases, §Objections; internal-knowledge.md §2.2].
- No named customers in the KB; all evidence is aggregate.

## RFP pattern matches

**1. `key: infopath_sharepoint_migration`**
- Signals: "InfoPath", "retire legacy forms", "SharePoint 2013/2016/2019 decommission", "migrate to SharePoint Online / Power Platform", "convert N thousand forms to PDF/PDF-A".
- Products: Converter for SharePoint or DCS for bulk; Online REST cloud-side.
- Evidence: most common deal driver; ~$0.04/op one-off deals; large banking and multi-million-file wins; low renewal expectation [src: field-knowledge.md §Use cases; internal-knowledge.md §2.5, §9].

**2. `key: sharepoint_watermark_security`**
- Signals: "dynamic watermark with user name on view/download", "prevent unprotected download", "restrict print/copy", "confidential document control in SharePoint", "classification stamping".
- Products: Converter for SharePoint RTWM + Secure; Editor for review.
- Evidence: top differentiator, Encodian has no equivalent [src: internal-knowledge.md §9]. Caveats: ~2x open latency, no guest users, open issues PCONL-399/382/356 [src: document-converter.md §5.2; internal-knowledge.md §7].

**3. `key: power_automate_document_pipeline`**
- Signals: "Power Automate", "Logic Apps", "Nintex", "K2", "convert to PDF in workflow", "merge/split", "email archiving to PDF", "Forms/Power Apps to PDF", "no premium connector licensing".
- Products: Converter Online connector / Nintex Xtension / REST.
- Evidence: 87% of 2025 deals were basic OCR/conversion; Standard connector; >100 MB merges via SharePoint file references [src: internal-knowledge.md §8, §9, §7].

**4. `key: repository_ocr_searchability`**
- Signals: "make existing archive searchable", "scanned/image-only PDFs", "audit percentage non-searchable", "OCR in place", "auto-tag managed metadata / Term Store", "eDiscovery readiness".
- Products: Searchability Audit & OCR + Tagging; DAS when pipeline-shaped.
- Evidence: partner-run legal/real-estate/aviation archives; ~50% of OCR buyers add Tagger; but 3 of 14 won in 2025 H1 at ~$8k average vs competitors under $3k [src: field-knowledge.md §Use cases; internal-knowledge.md §4.1, §4.2].

**5. `key: onprem_batch_document_automation`**
- Signals: "watch/hot folder", "unattended batch OCR", "scan-to-archive", "split by barcode", "rename/route by content", "extract tables to Excel", "mailbox ingestion", "on-prem only".
- Products: DAS + Content Extraction; DCS when API-driven.
- Evidence: 5 of 13 won in 2025 H1; losses mostly no response, cancelled, or price [src: internal-knowledge.md §3, §9].

**6. `key: pii_redaction_compliance`**
- Signals: "redact PII/PHI", "SSN/card/IBAN patterns", "regex redaction", "FOIA / public-records release", "staged redaction with approval", "redaction audit trail".
- Products: Converter Online redaction (Enterprise), DAS Smart/Pattern Redaction, Editor Pro+ for manual review.
- Evidence: redaction shipped Jan and Aug 2026; DAS Smart Redaction covers cards, DOB, email, IBAN, phone, SSN, address; 79% survey demand for intelligent extraction [src: internal-knowledge.md §2.4, §3, §9]. Caveat: Editor redaction approval is backlog (PEONLL-673); DAS keep-last-4 regex UNVERIFIED [src: internal-knowledge.md §6; field-knowledge.md §FAQ].

## Competitive positioning

- **Beat Encodian (Flowr)** on real-time watermarking (no equivalent), in-SharePoint UI, on-prem, large/complex files, InfoPath, PDF/A; **lose** on action breadth, PA signing (shipped first), and price (~$500/yr) [src: internal-knowledge.md §9; field-knowledge.md §Objections].
- **Beat Microsoft Syntex OCR** on backfile: Syntex does not process existing library content; but it and native PA conversion take price-sensitive deals [src: internal-knowledge.md §9].
- **Beat generic PDF APIs** (Adobe PDF Services, ConvertAPI, CloudConvert, pdfRest, PDF4me, Cloudmersive) where SharePoint-native UI, Standard connector or on-prem is mandatory; lose where price alone decides [src: internal-knowledge.md §9].
- **Searchability loses on price** to Encodian Indxr, Ocrato, FabSoft, ABBYY FineReader Server, KWizCom, Websio [src: internal-knowledge.md §4.2, §9].
- **Nintex as platform**: historically won on price/personalization, lost on features/UI [src: field-knowledge.md §Objections].
- Compliance losses: HIPAA BAA; perpetual-license expectations on small farms [src: internal-knowledge.md §9].

## What makes an RFP a GOOD fit

- Microsoft-centric estate naming SharePoint (2007–SE or Online), Power Automate, Logic Apps, Nintex or K2 [src: document-converter.md §1.2].
- On-prem, air-gapped, or US/CA/EU/AU residency required for processing [src: document-converter.md §1.2–1.3].
- Watermark-on-view/download tied to user identity, or PDF security without Acrobat [src: internal-knowledge.md §9].
- Files beyond PA's 100 MB limit, complex Excel, InfoPath, CAD/Visio/email [src: internal-knowledge.md §9; document-converter.md §8.1].
- Backfile OCR with audit reporting or scheduled Term Store tagging [src: document-searchability.md §2, §9].
- High-volume unattended OCR/convert/redact/extract (40k+ pages/month) [src: internal-knowledge.md §9].
- Bans premium Power Platform licensing or requires GCC [src: document-converter.md §3.1].
- Buyer is a SharePoint/M365 admin, records manager, compliance lead, or M365 partner [src: field-knowledge.md §Personas].

## What makes an RFP a BAD fit

- Requires HIPAA BAA, FedRAMP, GCC High/DoD, or any certification the KB cannot confirm [src: internal-knowledge.md §2.2; document-converter.md §3.1].
- Small one-off or lowest-price-wins buys; tier minimums and ~$109/mo Basic draw complaints [src: internal-knowledge.md §9; field-knowledge.md §Objections].
- Non-Microsoft or Linux-only stack: all server products are Windows-only [src: document-automation-server.md §2; document-searchability.md §2].
- Must process IRM/AIP-protected documents [src: document-converter.md §11].
- Searchability where price is primary (3/14 win rate) [src: internal-knowledge.md §4.2].

**Route instead:**
- **Workflow (Nutrient Workflow Automation, fka Integrify — sibling agent Sage)**: BPM, forms, approvals, case management; the "Nutrient Workflow Automation" PA connector is that product, not Converter [src: document-converter.md §3.1; adjacent-integrations.md §(a)].
- **SDK (Nutrient Web SDK / GdPicture)**: embedding a viewer/editor in a custom app, SPFx custom code, Appian/Mendix/OutSystems, Salesforce LWC — low-code connectors for those are not released [src: adjacent-integrations.md §(a), §(e)].
- **DWS (Nutrient Document Web Services)**: hosted document API or eSign outside the Microsoft/Power Automate context; KB covers DWS only as the signing backend for Salesforce and Editor, so scope is [UNVERIFIED] [src: adjacent-integrations.md §(b); internal-knowledge.md §6].
- **Documents for Salesforce / HubSpot / ServiceNow**: CRM-native generation or eSign — adjacent LOB hand-off [src: adjacent-integrations.md §(a)].

## Knowledge gaps in this profile

- Certification status: SOC 2 scope; nothing on ISO 27001, FedRAMP, StateRAMP, 508/VPAT, Cyber Essentials [src: internal-knowledge.md §2.2, §11].
- No named customers, case studies or public-sector references (KB sanitized).
- Deal-level loss reasons: CRM query never ran; only aggregate memos [src: field-knowledge.md §CRM caveat].
- No consolidated price book; DAS, Searchability, DCS, Editor on-prem quote-only [src: internal-knowledge.md §11].
- Searchability hosted SaaS existence, regions and pricing [src: internal-knowledge.md §4.1, §11].
- Competitor depth on Plumsail, OneSpan, Apryse, Foxit, Adobe (beyond a connector listing) [src: internal-knowledge.md §11].
- No published uptime SLA or Online performance benchmarks; DCS performance page not opened [src: internal-knowledge.md §12].
- Public-sector procurement vehicles and regional resellers: not in KB.
- Team continuity: June 2026 handovers and implied SME departure [src: internal-knowledge.md §8, §10].
