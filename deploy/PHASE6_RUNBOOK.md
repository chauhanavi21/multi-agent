# Phase 6 deploy runbook

## What's new in the deploy

1. The FastAPI process now runs APScheduler in-process. **Run a single uvicorn
   worker** for the API (not multiple) so scheduled jobs don't fan out N times.
   If you want >1 worker for HTTP, put the scheduler in a separate process
   (set `SCHEDULER_MODE=disabled` on the HTTP workers and run one extra worker
   with `SCHEDULER_MODE=in_process` and no HTTP exposure).

2. New env vars (all optional):
   ```
   TWILIO_ACCOUNT_SID=
   TWILIO_AUTH_TOKEN=
   TWILIO_FROM_NUMBER=
   APIFY_TOKEN=
   APIFY_INSTAGRAM_ACTOR=apify/instagram-scraper
   SCHEDULER_MODE=in_process
   SCHEDULER_ENABLED=true
   ```

3. New Python deps (in `backend/requirements.txt`):
   - apscheduler==3.10.4
   - apify-client==1.8.1
   - twilio==9.3.5

4. New migration: `python -m app.db.migrate_phase6` (idempotent; safe to re-run).

## Bedrock + pgvector on AWS

Amazon RDS for Postgres ships pgvector. To enable on an existing RDS cluster:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

This requires the RDS Postgres major version to be 15.2+ (most are). Once
enabled, `migrate_phase6` detects it and uses the indexed vector column. No
config change needed in the app.

## SSM Parameter Store keys (Phase 6)

If you store secrets in SSM (Phase 5 pattern), the keys to add:
```
/sales-agent/prod/twilio_account_sid
/sales-agent/prod/twilio_auth_token
/sales-agent/prod/twilio_from_number
/sales-agent/prod/apify_token
```

EC2 user_data already grants `ssm:GetParameter` (Phase 5). Add a small read
block in `bootstrap.sh` to populate the env file. Or just edit `/etc/sales-agent.env`
manually for the first deploy.

## Health check additions

`GET /api/health` now returns:
```json
{
  "ok": true,
  "phase": 6,
  "twilio_configured": true,
  "apify_configured": false,
  "scheduler_mode": "in_process"
}
```

Use this in your monitor to detect missing creds without leaking values.

## Watching scheduled jobs

`GET /api/scheduler/active` shows the runtime-loaded jobs for the current company:
```json
[{"id": "c2:ceo_daily", "next_run_time": "2026-06-04T06:00:00+00:00"}]
```

Manual one-off: `POST /api/scheduler/jobs/ceo_daily/run_now`.

The reconcile loop runs every minute, so changing a cron in the Admin panel
takes effect within ~60s without restart.

## Backup additions

Phase 5's `backup.sh` already backs up the whole DB. New tables are included
automatically; no script change needed.

## Cost guardrails

The new daily cycle adds roughly (per company, per day, at Sonnet/Bedrock cloud rates):
- CEO daily plan: ~$0.005-0.01
- CMO competitor + scripts: ~$0.01-0.02
- Insights pattern mining: ~$0.002-0.005
- Outreach daily (per 10 leads): ~$0.01-0.03
- Memory compression on each write: ~$0.00005 each

**Per company**: ~$0.03-0.05 per day if you run all 4 jobs. Set
`MONTHLY_BUDGET_USD=5` per company to be safe; the cost router already enforces
this from Phase 4.

## Disabling the scheduler in dev

Set `SCHEDULER_MODE=disabled` to skip APScheduler startup entirely. Manual
"Run now" still works via the API.
