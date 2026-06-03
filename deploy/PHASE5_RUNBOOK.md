# Phase 5 Runbook

The operational guide for running Sales Agent on AWS. Read this before you run `terraform apply`.

---

## Architecture

```
              Internet
                │
                ▼
    ┌────────────────────┐
    │  EC2 t3.micro       │   ← runs:
    │  Ubuntu 24.04       │     • Caddy (HTTPS reverse proxy, port 443)
    │  10.0.1.x           │     • gunicorn + uvicorn (FastAPI, 127.0.0.1:8000)
    └─────────┬──────────┘     • Redis (semantic cache, localhost:6379)
              │                • optional Tailscale (if you set tailscale_auth_key)
              │
              │ SG: db-only-from-app
              ▼
    ┌────────────────────┐
    │  RDS db.t3.micro    │   ← Postgres 16
    │  publicly_accessible│
    │       = false       │
    └────────────────────┘

    ┌────────────────────┐
    │  S3: frontend       │   ← React build, public read
    │  S3: backups        │   ← pg_dump tarballs, 30d retention
    └────────────────────┘

    ┌────────────────────┐
    │  SSM Parameter Store│   ← db_password, jwt_secret, anthropic_api_key
    └────────────────────┘     fetched by EC2 user_data at boot
```

**What pays the bill**

| Resource             | Free tier (12mo) | After free tier |
|----------------------|------------------|-----------------|
| EC2 t3.micro         | 750 hrs/mo       | ~$7.50/mo       |
| RDS db.t3.micro      | 750 hrs/mo       | ~$15/mo         |
| RDS 20GB storage     | 20GB             | ~$2.30/mo       |
| S3 5GB + requests    | free             | ~$0.50/mo       |
| EBS 20GB             | 30GB free        | ~$1.60/mo       |
| Data transfer out    | 100GB free       | $0.09/GB        |
| Bedrock (inference)  | not in free tier | per-token       |
| Anthropic (inference)| not AWS          | per-token       |

Sub-$30/mo after the free tier, before inference.

---

## First-time setup

### 0. Prereqs

- AWS account with admin or equivalent IAM
- `aws configure` — set up your CLI creds
- Terraform 1.6+
- Node 20+, Python 3.12+
- An SSH key at `~/.ssh/id_ed25519.pub` (or override `public_key_path`)

### 1. Enable Bedrock model access

Bedrock requires you to explicitly opt in to each foundation model.

1. Open https://console.aws.amazon.com/bedrock/home (your region)
2. Click **Model access** → **Manage model access**
3. Enable `anthropic.claude-haiku-4-5` and `anthropic.claude-sonnet-4-5`
4. Submit. Approval is usually instant for Anthropic models.

If you skip this, companies with `cloud_provider = bedrock` will get `AccessDeniedException` from the router. Anthropic-direct companies still work.

### 2. Apply infrastructure

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars: at minimum, set ssh_cidr to your IP/32
terraform init
terraform plan       # review
terraform apply
```

Expect 5–8 minutes (RDS takes a while). Outputs include `app_public_ip`, `frontend_bucket`, `db_endpoint`.

### 3. First deploy

```bash
cd ../..
chmod +x deploy/deploy.sh
deploy/deploy.sh
```

This builds the frontend, syncs to S3, uploads the backend tarball, and SSHes to EC2 to install + start.

### 4. Verify

```bash
APP_IP=$(terraform -chdir=infra/terraform output -raw app_public_ip)
curl -k https://$APP_IP/api/health
```

Should print:

```json
{"ok":true,"model":"llama3.1:8b","phase":5,"anthropic_configured":true,"bedrock_region":"us-east-1","ollama_url":"http://localhost:11434"}
```

### 5. Log in

Frontend URL: `https://$APP_IP/` (browser will warn about self-signed cert — accept it for now; see "Custom domain" below for the fix).

Log in with the bootstrap admin email + password you set in `terraform.tfvars`.

---

## How inference works on EC2

EC2 t3.micro has 1GB RAM. It **cannot** run llama3.1:8b. So:

- **Cheap and standard tiers** (which want local Ollama) will **fail** unless:
  - You set `OLLAMA_BASE_URL` in `/opt/sales-agent/backend/.env` to a remote Ollama (e.g., Tailscale tunnel to your home machine), OR
  - You toggle each company to `use_cloud_api=true` in the admin panel, so the router redirects to cloud for the quality/premium tiers, and the cheap/standard tiers get accepted as "best effort" downgraded with errors logged.

### Option 1: All cloud (simplest)

In Admin panel:
- Set every company's **Cloud API** to **On**
- Set **Provider** to **Anthropic** or **Bedrock**

The cheap/standard agent actions (lead generation, draft emails) will then still try Ollama and fail — agents that depend on these will error. Two fixes:
- Bump those actions to `quality` tier in the agent code (small edit per agent file)
- Or use Option 2 or 3 below to make local inference work

### Option 2: Tailscale to home Ollama (free inference)

If your home machine runs Ollama and has llama3.1:8b + phi3:mini pulled:

1. Generate a Tailscale auth key at https://login.tailscale.com/admin/settings/keys (reusable, 90 days)
2. Put it in `terraform.tfvars` as `tailscale_auth_key = "..."` and re-apply
3. SSH to EC2 and check `tailscale status` to see your home machine's IP (e.g. 100.x.y.z)
4. Edit `/opt/sales-agent/backend/.env`:
   ```
   OLLAMA_BASE_URL=http://100.x.y.z:11434
   ```
5. `sudo systemctl restart sales-agent`

Now cheap/standard tiers route to your laptop's Ollama via the encrypted tailnet. Inference is free; you pay nothing for cheap/standard tiers.

**Tradeoff**: if your laptop sleeps, agents break. Fine for personal use, dicey for paying users.

### Option 3: Bedrock for everything

In the admin panel, set Cloud API=On + Provider=Bedrock for every company. The EC2 IAM role already has Bedrock invoke permission, so no API key needed. You will need to manually bump the cheap/standard agent tiers in code to `quality` if you want them to route to cloud — that's a one-line change per agent file (sales_agent.py et al.).

---

## Custom domain (recommended)

You're using IP-only HTTPS with a self-signed cert by default. Browsers will warn. Fix:

1. Point a DNS A record at the EC2 IP (e.g. `sales.yourdomain.com` → `1.2.3.4`)
2. SSH to EC2: `ssh ubuntu@$APP_IP`
3. Edit `/etc/caddy/Caddyfile`:
   ```
   sales.yourdomain.com {
     reverse_proxy 127.0.0.1:8000
   }
   ```
4. `sudo systemctl reload caddy`

Caddy fetches a real Let's Encrypt cert automatically on the first HTTPS request. Done.

---

## Routine deploys

After changing code locally:

```bash
deploy/deploy.sh
```

Migrations are idempotent so they re-run on every deploy without harm.

---

## Backups

The `backup.sh` script does a `pg_dump` to S3. Install it as a cron on EC2:

```bash
ssh ubuntu@$APP_IP
sudo cp /tmp/backup.sh /opt/sales-agent/backup.sh
sudo chmod +x /opt/sales-agent/backup.sh
sudo crontab -e
# add:
0 3 * * *  /opt/sales-agent/backup.sh >> /var/log/sales-agent/backup.log 2>&1
```

(Upload `backup.sh` first via `scp deploy/backup.sh ubuntu@$APP_IP:/tmp/`.)

Restore one backup:

```bash
aws s3 cp s3://sales-agent-backups-xxxx/pg/20260601-030000.sql.gz - | gunzip | \
  PGPASSWORD=... psql -h <RDS endpoint> -U agent -d salesagent
```

---

## Debugging

```bash
ssh ubuntu@$APP_IP

# App logs
sudo journalctl -u sales-agent -f
sudo tail -f /var/log/sales-agent/error.log

# Caddy
sudo journalctl -u caddy -f

# Postgres connectivity from EC2
PGPASSWORD=$(aws ssm get-parameter --name /sales-agent/db_password \
  --with-decryption --query Parameter.Value --output text) \
  psql -h <db endpoint> -U agent -d salesagent -c "SELECT 1"

# Bedrock smoke test
aws bedrock-runtime converse \
  --model-id anthropic.claude-haiku-4-5-20251001-v1:0 \
  --messages '[{"role":"user","content":[{"text":"hi"}]}]'

# Restart everything
sudo systemctl restart sales-agent caddy redis-server
```

---

## Tearing down

```bash
terraform -chdir=infra/terraform destroy
```

Deletes the EC2, RDS (skip_final_snapshot=true), S3 buckets (force_destroy=true), all SSM params, VPC, and IAM roles. Run any final backups first.

---

## What this build does NOT include

These are deliberate Phase 5 omissions, each a candidate for Phase 6:

- **CloudFront in front of S3** — would give global edge caching + nicer cert story
- **CI/CD pipeline** — GitHub Actions equivalent of `deploy/deploy.sh`
- **WAF/rate limiting** — currently anyone on the internet can hit your API
- **CloudWatch alarms** — agent installed, but no alarms configured
- **Multi-AZ RDS** — single AZ for free tier; one outage = downtime
- **Cognito** — you chose to keep JWT, so this stays. Migration path: replace `app/auth/*` with Cognito JWT verification
- **VPC endpoints** — SSM/S3/Bedrock traffic from EC2 currently goes over the IGW. Adding endpoints would route privately (small cost)
