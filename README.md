# Phase 5 — AWS deployment + Bedrock support

Builds on Phase 1+2+3+4. Adds:

- **Bedrock provider** in the model router (alongside Anthropic direct + Ollama)
- **Per-company `cloud_provider`** setting (`anthropic` | `bedrock`), toggled in the admin panel
- **Configurable Ollama URL** — so `OLLAMA_BASE_URL` can point at localhost OR a Tailscale tunnel back to your home machine
- **Terraform module** for full AWS stack: VPC, EC2 t3.micro, RDS db.t3.micro, two S3 buckets, IAM role, SSM params, security groups
- **EC2 user-data** that bootstraps the box on first boot: installs Python/Redis/Caddy, fetches secrets from SSM, pulls app code from S3, runs migrations, starts systemd service
- **Deploy script** that builds the frontend, packs the backend, and refreshes EC2 in one command
- **Caddy** reverse proxy with auto-HTTPS (self-signed for IP-only mode; Let's Encrypt the moment you point a domain at it)
- **Backup script** for nightly pg_dump to S3 with 30-day retention
- **Runbook** with operational procedures, debugging, and the genuinely awkward bits (like "t3.micro can't run llama3.1:8b")

## Install on top of Phase 1+2+3+4

```bash
cd ~/path/to/phase1
unzip -o ~/Downloads/phase5-aws-deployment.zip
cp -r phase5/* . && rm -rf phase5
```

## Local setup (verify Phase 5 backend changes work before deploying)

```bash
cd backend && source venv/bin/activate
pip install -r requirements.txt          # adds boto3, gunicorn
python -m app.db.migrate_phase5          # adds cloud_provider column to companies
uvicorn app.main:app --reload --port 8000
```

Visit the admin panel — companies tab now has a **Provider** dropdown.

## AWS deployment

See `deploy/PHASE5_RUNBOOK.md` for the full walkthrough. Short version:

```bash
# 1. Enable Bedrock model access for anthropic.claude-haiku-4-5 and claude-sonnet-4-5
#    in the AWS console (free, but required)
# 2. Apply infra
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
# edit terraform.tfvars (set ssh_cidr to your IP/32 at minimum)
terraform init && terraform apply
# 3. Deploy code
cd ../.. && deploy/deploy.sh
# 4. Verify
curl -k https://$(terraform -chdir=infra/terraform output -raw app_public_ip)/api/health
```

## What's in this zip

```
phase5/
├── backend/
│   ├── requirements.txt            # adds boto3, gunicorn
│   └── app/
│       ├── config.py               # adds bedrock_* + ollama_base_url is now meaningful
│       ├── main.py                 # imports model_extensions_p5
│       ├── cost/
│       │   ├── pricing.py          # adds bedrock model IDs
│       │   └── router.py           # adds _call_bedrock(), per-company provider selection
│       ├── db/
│       │   ├── migrate_phase5.py   # adds companies.cloud_provider
│       │   └── model_extensions_p5.py
│       └── routes/
│           └── admin_routes.py     # adds PUT /admin/companies/{id}/cloud_provider
├── frontend/src/
│   ├── api/client.js               # adds adminSetProvider
│   └── components/
│       └── AdminPanel.jsx          # adds Provider dropdown column
├── infra/terraform/
│   ├── versions.tf
│   ├── variables.tf
│   ├── terraform.tfvars.example    # COPY THIS to terraform.tfvars
│   ├── vpc.tf
│   ├── ec2.tf
│   ├── rds.tf
│   ├── s3.tf
│   ├── iam.tf
│   ├── ssm.tf
│   ├── outputs.tf
│   └── user_data.sh
└── deploy/
    ├── deploy.sh
    ├── backup.sh
    ├── Caddyfile
    └── PHASE5_RUNBOOK.md           # READ THIS BEFORE terraform apply
```

## Key tradeoffs documented in the runbook

- t3.micro can't run llama3.1:8b → three workarounds (all cloud / Tailscale to home / Bedrock for everything)
- RDS in public subnets without NAT gateway saves $32/mo vs the "textbook" private-subnet design
- S3 static hosting with public read for the frontend (no CloudFront yet)
- Self-signed cert until you point a domain (then Caddy auto-issues Let's Encrypt)
