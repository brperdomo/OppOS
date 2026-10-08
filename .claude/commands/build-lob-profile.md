---
description: Regenerate the RFP-qualification positioning profile for one Nutrient line of business (workflow | low_code | sdk | dws) from its knowledge sources, with a citation on every claim, then re-run the scoring eval.
argument-hint: <lob> [--sources extra,urls]
---

Rebuild `oppos/scoring/lobs/profiles/$ARGUMENTS.md` — the system-prompt context the Stage 2 scorer uses for that LOB. Treat `$ARGUMENTS` as `<lob> [notes]`; the LOB key must be one of `workflow`, `low_code`, `sdk`, `dws`.

## 1. Gather sources (read, don't guess)

| LOB | Primary sources | Use the agent |
|---|---|---|
| `low_code` | `~/.claude/catalyst-data/*.md` (internal-knowledge.md win/loss + competitors, field-knowledge.md personas + objections, product files for capabilities) | `catalyst:catalyst` |
| `workflow` | `~/.claude/sage-data/*.md`, the existing profile, past-win notes Bryan provides | `sage` |
| `sdk` | nutrient.io customer stories (`/blog/categories/customer-stories/`, append `.md` for markdown), `/sdk/` product pages and guides, G2 themes, `gh repo list PSPDFKit` for platform coverage | `general-purpose` with WebFetch/WebSearch |
| `dws` | nutrient.io `/api/` and DWS guides, customer stories mentioning the API | `general-purpose` |

If HubSpot is connected, add closed-won deals by LOB (industry, use case, size) — that is the strongest win evidence. Never use the Trust Center. Never invent pricing, certifications, or customers.

## 2. Write the profile

Keep the existing frontmatter shape (`lob`, `depth`, `version` +1, `generated_at`, `generated_by`, `sources`) and these H2 sections in order: What it is · Core capabilities · Deployment options · Security & compliance · Licensing & pricing posture · Proven verticals (with evidence) · RFP pattern matches (each with `key: snake_case`, signals, products, evidence) · Competitive positioning · What makes an RFP a GOOD fit · What makes an RFP a BAD fit (with routing to other LOBs) · Knowledge gaps in this profile.

Rules: every factual claim gets `[src: …]`; general knowledge is `[UNVERIFIED]`; 1,200–2,000 words; dense bullets; no images or wide tables (it is injected into a prompt). Set `depth: full` only when verticals, patterns, and competitive sections are evidence-backed — otherwise leave `depth: thin` so the scorer keeps capping scores.

## 3. Wire pattern keys

If the pattern keys changed, update `extras_schema` in `oppos/scoring/lobs/<lob>.py` so `pattern_match` enumerates them.

## 4. Verify

```bash
python -c "import oppos.config; from oppos.scoring.lobs import LOBS; l=LOBS['<lob>']; print(l.depth, len(l.profile))"
python scripts/eval_scoring.py --n 20
```

Report: depth, word count, pattern keys, the eval summary vs. the previous run in `eval/results/`, and the top 3 reliability caveats. Do not commit; show the diff summary and let the user decide.
