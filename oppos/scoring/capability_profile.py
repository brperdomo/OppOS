"""Nutrient Workflow capability profile for AI-powered RFP qualification.

This is the context the Claude qualifier uses to score RFPs. It encodes
everything we know about what Workflow does, who it serves, what it wins,
and how to differentiate against competitors.
"""

CAPABILITY_PROFILE = """
# Nutrient Workflow — Capability Profile for RFP Qualification

## What Nutrient Workflow Is
Nutrient Workflow is a configurable, enterprise-ready process automation and case management
platform purpose-built for document-heavy, compliance-driven operations. It combines intelligent
process orchestration with embedded document capabilities (viewing, editing, generation, signing,
redaction), audit-ready compliance, agentic AI, and flexible deployment options.

## Core Capabilities

### Process Automation
- Visual drag-and-drop process builder (no-code/low-code)
- Conditional routing, parallel approvals, SLA tracking
- Task assignment, escalation, automated notifications
- Configurable business rules, decision logic, milestones

### Form Designer
- 18+ field types: text, number, email, calendar, file attachment, signature, grids, AI boxes, RESTful elements
- Data validation, auto-population, conditional logic, progressive disclosure
- Form scripting (JavaScript/CSS customization)
- Guided intake / interview-style experiences

### Document Management (Native — Not Bolted On)
- In-browser document viewing/preview (no downloads)
- PDF and DOCX generation from dynamic templates
- Document editing, redaction, markup, annotations
- Electronic/digital signatures with external signer support
- Version tracking, archival, collaboration

### Case Management
- Centralized intake → review → approval → reporting lifecycle
- Role-based access (internal/external portals)
- Full audit trails (timestamps + user actions)
- Status tracking, notifications, escalations
- Multi-channel submissions

### AI Capabilities
- AI Form Builder: generate structured forms from natural language
- AI Data Extraction: classify documents, extract structured data, auto-populate fields
- Agentic Approvals: autonomous recommendations based on rules/policies with human-in-the-loop
- LLM-Guided Decision Support: interview-style intake with configurable rationale depth
- Supports Anthropic Claude and OpenAI as LLM providers
- Workflow Copilot: Chrome extension for natural language admin operations

### Reporting & Analytics
- Real-time dashboards, SLA monitoring, bottleneck identification
- Custom report builder with filters, aggregation, SQL stored procedures
- PDF/Excel/CSV export, compliance-ready reporting
- Power BI integration via direct SQL access
- Tableau integration via custom stored procedures

### Integrations
- CRM: Salesforce, HubSpot
- ERP: SAP, Deltek, Costpoint
- Microsoft: SharePoint, Exchange, Power Automate, M365
- Databases: SQL Server, MongoDB (custom tables, direct SQL access)
- API: REST API (508+ endpoints), RESTful Elements in forms
- File Transfer: SFTP, email (monitored inbox automation)
- Automation: Zapier, AWS Lambda, Power Automate
- Identity: Active Directory, SAML 2.0 SSO (Okta, Ping, Microsoft Entra ID), OIDC, SCIM, MFA
- Other: Slack, Stripe (via REST client)

## Deployment Options

### Standard Cloud
Multi-tenant SaaS on AWS. Fastest time to value. Nightly backups, baseline storage.

### Enhanced Cloud
Single-tenant SaaS on AWS. Regional pinning, private database, optional VPN/private links, optional sandbox.
For data residency, private networking, or isolation needs.

### Self-Managed
Customer-hosted Kubernetes deployment. Customer-scheduled updates. Full infrastructure control.
For hard residency, agency constraints, or private-network-only access.

### Private Cluster
Dedicated AWS infrastructure managed by Nutrient. Used by Booz Allen, AbbVie, NJ Transit, Widelity, Yellowstone.

### TBS Partner Hosting
FedRAMP-capable hosting via partner. For GovCon deployments requiring FedRAMP-aligned infrastructure.

### AWS GovCloud
In progress for government customers with strict compliance needs.

## Security & Compliance
- SOC 2 Type II certified (reports available under NDA)
- HIPAA BAA available on request
- FERPA, FISMA, GovCon ready
- RBAC with object-level permissions
- MFA, SSO (SAML 2.0 / OIDC), SCIM provisioning
- Encryption in transit (TLS) and at rest
- Immutable audit logs with timestamps and user attribution
- Exportable logs for compliance reviews
- FedRAMP: NOT yet certified as a product, but achievable via TBS partner hosting
- WCAG 2.0 AA / Section 508 accessibility (VPAT being finalized)

## Licensing
- Annual subscription per deployment model
- Concurrent user licensing for admins/power users
- Guests/requesters included without per-seat fees
- Add-ons: eSignature, Document Generation, Document Editing, Document Collaboration/Markup, AI-powered form filling, AI Data Extraction

## Proven Verticals (with real customer evidence)

### Tier 1 — Strongest Verticals
- **Government/GovCon**: City of Baltimore, Nevada BEN, Tennessee DOHR, Oakland USD, State of WV, Booz Allen, Deloitte GovCon, Cognosante, DHS-IG, ECS Federal, NTT Data Federal, Guidehouse, Peraton, LANL
- **Healthcare/Pharma**: GSK (78K+ users, 60+ countries), PCI Pharma, Holyoke Medical, Abbott, Caregility, Prevention Point, Medcor, KP
- **Energy/Oil & Gas**: BP, ExxonMobil, Targa Resources
- **Defense/Aerospace**: Northrop Grumman, Airbus US, Rolls-Royce, Burns & McDonnell, LANL

### Tier 2 — Strong Verticals
- **Financial Services**: FCMB, PFCU, Lewis Management, EY, Benenden
- **Education**: UT Health San Antonio, Baylor University, RVU, WestEd
- **Logistics/Transport**: Cardinal Logistics, NJ Transit, MSC Cruises, BC Ferries, Mastec
- **Manufacturing**: U.S. Pipe, Versatex, Sternberg, Masterlock, Terex, Four Roses

### Tier 3 — Proven but Smaller
- Nonprofits, Construction, Legal, Entertainment, Senior Living, Automotive, Hospitality

## RFP Pattern Matches (Past Wins)

### Pattern: Case Management
Match: BEN (Nevada) — external portal, role-based access, submissions, approvals, equipment tracking, reporting
Indicators: intake forms, case lifecycle, multi-role access, audit trails, program management

### Pattern: Leave/HR Compliance
Match: Tennessee DOHR — FMLA case management, leave lifecycle, ERP integration, compliance timelines
Indicators: leave management, HR automation, compliance deadlines, ERP integration, dashboards

### Pattern: Guided Decision Support
Match: ExxonMobil — LLM-powered project execution planning, interview-style UX, plan generation
Indicators: knowledge capture, decision trees, recommendations engine, document generation

### Pattern: Financial Approvals
Match: BP — CapEx, delegation of authority, SAP integration, SOX compliance
Indicators: capital expenditure, purchase approvals, financial controls, ERP companion

### Pattern: IT Request Management
Match: GSK — service catalog, request routing, multi-department, high user volume
Indicators: IT service management, request routing, self-service portal, large user base

### Pattern: AP/Invoice Processing
Match: Prevention Point — receipt capture, approval routing, mobile, document generation
Indicators: accounts payable, invoice approval, receipt processing, mobile workflows

## Competitive Positioning
- vs **Nintex/K2**: Nintex is cloud-first with limited on-prem. Routes documents but relies on third-party viewers and external signing. Nutrient embeds the full document lifecycle natively.
- vs **Power Automate**: Tied to Microsoft ecosystem. No native document rendering, annotation, or generation. Documents require external tools.
- vs **Appian**: Moving to mandatory K8s for self-managed (Nutrient already there). More expensive. Less document-centric.
- vs **ServiceNow**: Enterprise ITSM platform — overkill for workflow automation. High cost, long implementation.
- Key differentiator: "Workflow-first with optional AI" — validated at TechEx conference where buyers were tired of AI-first messaging.

## Scoring Priority — State/Local Over Federal
State and local government RFPs are HIGHER PRIORITY than federal:
- State agencies typically require SOC 2, HIPAA, or FERPA — Nutrient has these.
- Federal agencies often require FedRAMP ATO — Nutrient does NOT have this yet (TBS path exists but is not certified).
- State procurement cycles are shorter and less bureaucratic.
- Score state/local opportunities 10-15 points higher than equivalent federal ones when compliance is a factor.
- If an RFP explicitly requires FedRAMP ATO (not just "FedRAMP preferred" or "cloud security"), reduce the score significantly — this is a hard blocker today.
- FIPS 140-2 compliance is similarly not yet certified — flag as a risk if required.

## What Makes an RFP a GOOD FIT
1. Requires intake forms → routing → approvals → reporting (case management pattern)
2. Document-heavy (PDFs, document generation, signatures, redaction)
3. Needs audit trails / compliance (SOX, HIPAA, FERPA, Section 508)
4. Integrates with systems Nutrient connects to (SAP, Salesforce, SharePoint, AD)
5. Deployment model compatible (cloud, on-prem/K8s, hybrid)
6. Industry vertical match (state/local gov, healthcare, energy, pharma, finance, education, defense)
7. Replacing legacy BPM (Nintex, K2, Ultimus) or paper/email processes
8. Capital expenditure / financial approval workflows
9. HR compliance (leave management, onboarding, performance reviews)
10. Contract management / legal review workflows
11. Permit / licensing management for government agencies

## What Makes an RFP a BAD FIT
1. Pure software development / custom coding project
2. Staffing augmentation (bodies, not platform)
3. ERP/CRM replacement (Nutrient complements, doesn't replace SAP/Salesforce/ServiceNow)
4. Pure BI/analytics platform
5. Infrastructure / networking / cybersecurity only
6. Mobile app development (standalone)
7. Requires Oracle database (SQL Server + MongoDB only)
8. Requires full FedRAMP ATO on the product itself (not yet achieved — TBS path exists)
9. Requires FIPS 140-2 certified cryptography (not yet certified)
"""
