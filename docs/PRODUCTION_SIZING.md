# Production sizing & economics

How to host this app for paying customers with **local Ollama in the cloud**
(not your laptop) and **premium Claude only on paid plans**.

## Architecture (production)

```text
Internet → Caddy (HTTPS) → FastAPI on EC2
                ├── RDS Postgres
                ├── Redis (cache)
                ├── Ollama on same or separate EC2 (OLLAMA_BASE_URL)
                └── Bedrock / Anthropic (premium tier only)
```

Set in `backend/.env` on the server:

```env
OLLAMA_BASE_URL=http://127.0.0.1:11434
# or http://<inference-private-ip>:11434 if Ollama is on a second box
```

---

## Sizing by user count

Assumptions: moderate use — ~20 chat turns/user/day, scheduler on for ~30% of companies,
most calls hit **cheap/standard** (Ollama). Premium (Haiku) only on **Pro/Team** plans.

### ~10 active companies (~30 users)

| Component | Recommendation | Est. $/mo |
|-----------|----------------|-----------|
| App EC2 | `t3.small` (2 vCPU, 2 GB) — API + Redis + Caddy | ~$15 |
| Ollama | Same box or `t3.medium` (4 GB) for llama3.1:8b | +$0–15 |
| RDS | `db.t3.micro` Postgres 16 | ~$15 (free tier yr 1) |
| S3 + misc | Artifacts, backups | ~$3 |
| **API (Claude)** | ~10 Pro × ~$2 avg cloud usage | ~$20 |
| **Total** | | **~$50–70/mo** |

**Revenue target:** 5 Pro ($39) + 5 Free = **~$195/mo** → healthy margin if Free stays local-only.

### ~100 active companies (~300 users)

| Component | Recommendation | Est. $/mo |
|-----------|----------------|-----------|
| App EC2 | `t3.medium` or `t3.large` | ~$30–60 |
| Ollama | **Dedicated `g4dn.xlarge`** (GPU) OR `r6i.large` (CPU, slower) | ~$120–380 |
| RDS | `db.t3.small` | ~$25–35 |
| Redis | ElastiCache `cache.t3.micro` (optional) | ~$12 |
| **API (Claude)** | ~40 Pro + 10 Team × ~$4 avg | ~$200 |
| **Total** | | **~$400–700/mo** |

**Revenue target:** 40 Pro ($39) + 10 Team ($99) + 50 Free = **~$2,550/mo** before overages.

### When to add GPU

- **CPU-only Ollama** (`t3.medium`+): OK for demos and &lt;20 concurrent chats.
- **GPU** (`g4dn.xlarge`, ~$380/mo on-demand): when p95 chat latency matters or &gt;50 concurrent local requests.

---

## Plan → cost control (built into code)

| Plan | Cloud budget | Premium AI | Suggested price |
|------|--------------|------------|-----------------|
| **free** | $0 | Local only | $0 |
| **pro** | $8/mo cap | Haiku (quality tier) | $39/mo |
| **team** | $20/mo cap | Haiku + Sonnet (premium) | $99/mo |

### Rate limits (per company, per hour)

| Plan | Chat messages/hour |
|------|-------------------|
| free | 40 |
| pro | 300 |
| team | 2000 |

Scheduled jobs (CEO, outreach, etc.) always use **local** models so cron does not burn cloud budget.

Router rules:

1. `cheap` / `standard` → always Ollama (no API bill).
2. `quality` / `premium` → cloud only if plan allows **and** budget not exhausted.
3. 80% budget → downgrade to local Llama.
4. 100% budget → block cloud.

Apply migration after deploy:

```bash
python -m app.db.migrate_phase7
```

Admin → Companies → **Plan** dropdown sets plan + syncs budget and cloud toggle.

---

## Margin checklist

1. New signups → **free** plan (local only) automatically.
2. Never sell unlimited cloud at a flat fee.
3. Run Ollama **in AWS**, not on your home PC.
4. Keep scheduler jobs on **cheap** tier (already default).
5. Add Stripe later to flip `plan` on payment webhooks.

---

## Tear-down

```bash
cd infra/terraform && terraform destroy
```
