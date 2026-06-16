# Phase 6 — Shared memory, scheduler, autonomous agents

This phase implements the "6 agents, 1 shared memory" pattern from the brief:
**CEO** (daily plan), **CMO/social_analyst** (competitor reels + scripts),
**Lead pipeline** (sales agent w/ ICP scoring + stages), **Outreach** (daily
sequences), **Insights** (pattern miner), **Manager** (orchestrator).

Every agent reads and writes to a single shared memory store. APScheduler
runs the daily cycle automatically per company.

## What's new vs Phase 5

### Backend
- **`memories` table** with auto-detected pgvector OR numpy fallback. Every
  write goes through an LLM "compression" step that turns raw observations
  into 1-3 sentence reusable memories. Without that step memory is a graveyard.
- **3 new agents**: `ceo`, `insights`, `outreach` (see `app/agents/`).
- **Sales agent upgraded**: new actions `qualify_lead`, `transition_stage`,
  `follow_up_now`. ICP scoring against `companies.icp_profile`; auto-transitions
  to `qualified` at score >=70.
- **Social analyst upgraded**: new actions `competitor_reels` (Apify integration
  with mock fallback) and `script_reels` (writes 3 fresh scripts using shared memory).
- **Scheduler**: in-process APScheduler, per-company `scheduler_enabled` toggle,
  per-company per-job DB-driven cron config. Default jobs: ceo 06:00 UTC,
  cmo 07:00, insights 07:30, outreach 09:00.
- **Twilio interface** for SMS — real if `TWILIO_*` env vars set, mock otherwise.
  All sends go to `sms_outbox`.
- **Apify interface** for Instagram reels — real if `APIFY_TOKEN` set, mock otherwise.
- **Lead pipeline tables**: `lead_stage_history`, plus new columns on `leads`
  (`icp_score`, `current_stage`, `last_contacted_at`, `next_followup_at`).
- **New endpoints**: `/api/memory/*`, `/api/scheduler/*`, `/api/daily_plan`,
  `/api/reel_scripts`, `/api/sms`, `/api/leads/{id}/stage_history`,
  `/api/agents/sales/qualify_lead/{id}`, `/api/agents/sales/transition_stage/{id}`,
  admin `/icp_profile` and `/scheduler` toggles.

### Frontend
- **Dashboard tab**: today's CEO plan, scheduler config (edit cron / run-now /
  enable-disable), recent reel scripts, SMS outbox.
- **Memory tab**: browse + semantic search the shared memory, see backend
  (`pgvector` vs `numpy`), stats by kind, delete entries.
- **Workspace**: lead detail shows ICP score, stage history, transition
  buttons, qualify button.
- **Admin**: ICP profile editor + scheduler toggle per company.

## Configuration

Add to `.env` if you want real integrations:

```env
# SMS via Twilio (otherwise mocked into sms_outbox)
TWILIO_ACCOUNT_SID=ACxxxx
TWILIO_AUTH_TOKEN=xxxx
TWILIO_FROM_NUMBER=+1xxxxxxxxxx

# Instagram/Facebook reel scraping via Apify
APIFY_TOKEN=apify_api_xxxx
APIFY_INSTAGRAM_ACTOR=apify/instagram-scraper

# Scheduler — set to 'disabled' to suppress all scheduled runs in this process
SCHEDULER_MODE=in_process
```

If those aren't set, everything still works in mock mode. The CEO daily plan
agent doesn't need any of these to run.

## Bootstrapping

1. Apply migration (creates 7 new tables, adds 6 columns, auto-detects pgvector):
   ```bash
   python -m app.db.migrate_phase6
   ```
2. Set the company's ICP profile in the Admin panel (or via API). Without it,
   `qualify_lead` falls back to a generic heuristic.
3. Toggle "Scheduler" on for the company in Admin. The reconcile loop will
   seed default daily jobs and start them at the configured times (UTC).
4. To kick off the daily cycle manually, go to Dashboard → Scheduled jobs →
   "Run now" on each of `ceo_daily`, `cmo_daily`, `insights_daily`,
   `outreach_daily`.

## How "gets smarter every cycle" actually works

There's no magic — but the loop is real:

1. The **sales** agent writes a memory after each `qualify_lead`,
   `transition_stage(won|lost)`, and `draft_email`.
2. The **outreach** agent writes a summary memory after each daily batch.
3. The **insights** agent runs daily, scans recent stage history + drafts,
   identifies 3-5 patterns in converting messages, and writes each as a
   `kind=pattern` memory.
4. Next time **outreach** runs, it retrieves the top patterns relevant to each
   lead (semantic search by industry + role + company), injects them into the
   prompt, drafts with them.
5. Wins/losses get `importance=0.8` memories that bias future retrieval.

Concretely: if "mentioning compliance ROI" correlated with reply within 48h
for 3 fintech leads this week, insights writes that as a memory, and next
week's drafts to fintech leads pull it back automatically.

## Memory backend modes

- **pgvector** (preferred): if `CREATE EXTENSION vector` succeeds, the
  migration adds an `embedding_vec vector(768)` column with an IVFFlat index.
  Retrieval uses native `<=>` cosine ordering.
- **numpy** (fallback): the `embedding_bytes` column stores raw float32 bytes.
  Retrieval pulls up to 2000 candidates per company and ranks in Python. Fine
  to ~10k memories per company; switch to pgvector beyond that.

Either way the embeddings are *always* stored as bytes for portability; the
vector column is an additive optimization.

Check which mode is active at `/api/memory/stats`:
```json
{ "backend": "pgvector", "total": 247, "by_kind": {...} }
```

## Honest limits

- **Instagram/Facebook scraping**: without `APIFY_TOKEN`, the `competitor_reels`
  action only reads what's already in the table. You can seed mock rows via the
  `seed_mock_reel()` helper in `app/tools/competitor_reels.py`.
- **SMS**: without Twilio creds, messages go to `sms_outbox` with
  `status='mock'`. The agent and UI still work.
- **Cost**: the CEO and CMO daily jobs use `quality` tier (Sonnet/Opus when
  cloud is on). Three companies on scheduler = three Sonnet calls per morning.
  Insights and outreach use `standard` tier. Memory compression uses `cheap`
  tier on every write (~$0.0001 per memory write at most).

## Phase 7 — Subscription plans & rate limits

Plans (`free`, `pro`, `team`) gate cloud AI tiers and monthly budgets. See
`backend/app/billing/plans.py` and `docs/PRODUCTION_SIZING.md`.

```bash
python -m app.db.migrate_phase7
```

- **Free**: local Ollama only, 40 chat messages/hour (Redis).
- **Pro**: `quality` tier, $8 cloud budget cap, 300 chats/hour.
- **Team**: `premium` tier, $20 cap, 2000 chats/hour.

Admin can set a company's plan manually. The Cost card shows plan + usage.
Scheduled jobs are capped to local AI on free plans.

## Phase 8 — Stripe billing & legal

```bash
python -m app.db.migrate_phase8
```

- Stripe checkout/portal/webhooks: `backend/app/routes/billing_routes.py`
- Signup requires `accept_terms: true`
- Legal banners on login, chat, email send, scheduler
- Configure Stripe via `backend/.env` — copy from `backend/.env.example`, see
  `docs/STRIPE_SETUP.md`

`docker compose up -d` starts Postgres + Redis (required for rate limits).
