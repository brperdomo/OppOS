# OppOS — RFP sourcing, qualification, and pursuit tracking

OppOS scans public procurement portals, routes each RFP to the Nutrient line of business that could
address it, scores fit with evidence quoted from the RFP, and gives SDRs a workspace to pursue the
ones worth working — owner, deadlines, vendor-registration status, checklist, a Slack channel, a
Notion page, and automatic reminders.

```
GitHub Actions (weekdays 07:00 ET)            Streamlit dashboard (nutrient-opp-os.streamlit.app)
  sources → prefilter → LOB router →            Google sign-in → Pipeline · Qualified · Expiring ·
  per-LOB scorer → Turso → Slack digest         Pursuits (mine / team) · Submitted · Archive · Expired
GitHub Actions (daily 09:00 ET)
  deadline + inactivity reminders → Slack
```

## Running locally

```bash
pip install -r requirements.txt
cp .env.example .env            # fill in keys (see "Configuration")
streamlit run oppos/dashboard/app.py
```

Without `[auth]` secrets the app runs as a single local admin user. Set `OPPOS_DEV_USER="Your Name <you@nutrient.io>"`
to pursue RFPs under your own identity while developing.

## Configuration

### Environment / GitHub secrets

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Router (Haiku) and scorer (Sonnet) |
| `SAM_GOV_API_KEY` | Federal listings |
| `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN` | Shared SQLite (cloud). Unset → local `data/oppos.db` |
| `NOTION_TOKEN`, `NOTION_DATABASE_ID` | RFP Pipeline database in Notion |
| `SLACK_WEBHOOK_URL` | Fallback alerts when no bot token |
| `SLACK_BOT_TOKEN` | Enables channel-per-pursuit, invites, pins, digest, reminders (see Slack app below) |
| `NUTRIENT_API_KEY` | OCR / document processing for attachments |

### GitHub repository variables (`vars`)

| Variable | Purpose |
|---|---|
| `ENABLED_SOURCES` | Comma-separated source keys (`python scripts/run_pipeline.py --list-sources`) |
| `SLACK_DIGEST_CHANNEL` | Channel id (or `#name` the bot is in) for the daily digest and team notices |
| `SLACK_ALERT_MODE` | `digest` (one summary per scan) or `individual` (one alert per opp). Default: digest when bot + channel are set |
| `LOB_OWNER_WORKFLOW`, `LOB_OWNER_LOW_CODE`, `LOB_OWNER_SDK`, `LOB_OWNER_DWS` | Optional owner name per LOB for the Salesforce-opp message. Unset = omitted |
| `OPPOS_ADMINS` | Comma-separated admin emails: can edit portal registrations and change anyone's pursuit. **Set this before SDR rollout** — when empty, every user is an admin |

### Google sign-in (Streamlit native auth)

1. Google Cloud Console → APIs & Services → Credentials → **OAuth client ID** (Web application).
2. Authorized redirect URIs: `http://localhost:8501/oauth2callback` and `https://nutrient-opp-os.streamlit.app/oauth2callback`.
3. Copy `.streamlit/secrets.toml.example` → `.streamlit/secrets.toml` locally, or paste the `[auth]` block into
   Streamlit Cloud → App settings → Secrets. Generate `cookie_secret` with `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
4. Restrict the OAuth consent screen to the Nutrient Workspace (Internal) so only company accounts can sign in.

### Slack app (for pursuit channels)

Create an app at api.slack.com → OAuth & Permissions → Bot Token Scopes:
`chat:write`, `channels:manage`, `channels:read`, `pins:write`, `users:read`, `users:read.email`.
Install to the workspace, copy the `xoxb-…` token into `SLACK_BOT_TOKEN`, and invite the bot to the digest channel.
Pursuit channels are created as `#rfp-<agency-title>` (prefix via `SLACK_PURSUIT_CHANNEL_PREFIX`) and archived
when a pursuit is won/lost/abandoned (`SLACK_ARCHIVE_ON_CLOSE=false` to keep them).

## How SDRs use it

1. **Pipeline** — new, routed and scored RFPs. The chip shows the LOB; a badge shows whether we are registered on that portal.
   Open a card → *Load Attachments* → *Scan & Score* for a deep, evidence-backed assessment; it moves to **Qualified**.
2. **Qualified / Expiring Soon** — *Pursue* makes you the owner, creates the Notion page and Slack channel, and starts reminders.
   *Skip* records why (this trains the eval set).
3. **Pursuits** — your active pursuits (toggle to *Team*). Each has a status strip (owner · due · registration · checklist),
   editable details (deadlines, Q&A date, submission method), a go/no-go checklist, actions
   (Push to Notion · Salesforce Opp message · Submitted · Won/Lost · Abandon), and an activity log.
4. Reminders post to the pursuit channel at T-14/7/3/1, due, overdue, Q&A T-3/T-1, and after 7 idle days.
5. **Portal registrations** (admins) — keep status / vendor ID / who holds the login / lead time per portal. Never store passwords.

## Scoring model

- **Prefilter** (`oppos/scoring/prefilter.py`) — rules: expired, non-software NAICS, no software signal.
- **Stage 1 router** (Haiku) — which LOBs could address it, inclusive; `none` only for clearly unrelated work.
- **Stage 2 scorer** (Sonnet) — per-LOB profile in `oppos/scoring/lobs/`. Every strength/risk cites RFP text or says
  `inferred`; unknowns go to `knowledge_gaps`. Thin-profile LOBs (Low-Code, SDK, DWS) are capped at 59 and never `pursue`
  until a vetted profile replaces the description.

## Maintenance scripts

```bash
python scripts/run_pipeline.py --dry-run --days 3          # scan + score without Notion/Slack
python scripts/source_yield.py                             # which sources actually produce fits
python scripts/build_golden_set.py                         # labels from human decisions → eval/golden_set.jsonl
python scripts/eval_scoring.py --n 30                      # run after any prompt/profile change
python scripts/send_reminders.py --dry-run                 # preview today's reminders
```
