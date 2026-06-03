#!/bin/bash
# user_data.sh — runs once on EC2 first boot.
# Idempotent: re-running shouldn't break things.
#
# Templated by Terraform; vars: ${region}, ${db_endpoint}, ${db_name},
# ${db_username}, ${ssm_db_password}, ${ssm_jwt_secret}, ${ssm_anthropic_key},
# ${ssm_admin_password}, ${admin_email}, ${frontend_bucket}, ${tailscale_auth_key}

set -euxo pipefail
exec > >(tee -a /var/log/user-data.log) 2>&1
echo "=== user-data starting at $(date -Iseconds) ==="

# ---- 1. System packages
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
  python3.12 python3.12-venv python3-pip \
  postgresql-client-16 \
  redis-server \
  caddy \
  awscli \
  jq curl unzip git build-essential \
  nodejs npm

# Newer caddy if the apt one is old (caddy repo)
if ! command -v caddy >/dev/null 2>&1; then
  apt-get install -y debian-keyring debian-archive-keyring apt-transport-https
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -qq && apt-get install -y caddy
fi

systemctl enable --now redis-server

# ---- 2. Optional Tailscale (if auth key provided)
TS_AUTH_KEY="${tailscale_auth_key}"
if [ -n "$TS_AUTH_KEY" ] && [ "$TS_AUTH_KEY" != "" ]; then
  curl -fsSL https://tailscale.com/install.sh | sh
  tailscale up --authkey="$TS_AUTH_KEY" --hostname="salesagent-ec2" --ssh || true
fi

# ---- 3. App directory layout
useradd -m -s /bin/bash sales-agent 2>/dev/null || true
APP_DIR=/opt/sales-agent
mkdir -p "$APP_DIR" /var/log/sales-agent /var/lib/sales-agent
chown -R sales-agent:sales-agent "$APP_DIR" /var/log/sales-agent /var/lib/sales-agent

# ---- 4. Fetch app code from S3
# The deploy.sh script on your laptop uploads a tarball to the frontend bucket
# under the key "backend/latest.tar.gz" before triggering bootstrap.
# First boot may not find this yet — that's fine, you'll re-run via deploy.sh.
if aws s3 ls "s3://${frontend_bucket}/backend/latest.tar.gz" >/dev/null 2>&1; then
  aws s3 cp "s3://${frontend_bucket}/backend/latest.tar.gz" /tmp/backend.tar.gz
  tar -xzf /tmp/backend.tar.gz -C "$APP_DIR"
  chown -R sales-agent:sales-agent "$APP_DIR"
else
  echo "No backend tarball yet at s3://${frontend_bucket}/backend/latest.tar.gz"
  echo "Run deploy.sh from your laptop and re-run user_data if needed."
fi

# ---- 5. Python venv + deps
if [ -f "$APP_DIR/backend/requirements.txt" ]; then
  sudo -u sales-agent python3.12 -m venv "$APP_DIR/venv"
  sudo -u sales-agent "$APP_DIR/venv/bin/pip" install --upgrade pip -q
  sudo -u sales-agent "$APP_DIR/venv/bin/pip" install -r "$APP_DIR/backend/requirements.txt" -q
fi

# ---- 6. Fetch secrets from SSM and write .env
DB_PASS=$(aws ssm get-parameter --name "${ssm_db_password}" --with-decryption --region "${region}" --query Parameter.Value --output text)
JWT_SECRET=$(aws ssm get-parameter --name "${ssm_jwt_secret}" --with-decryption --region "${region}" --query Parameter.Value --output text)
ANTHROPIC_KEY=$(aws ssm get-parameter --name "${ssm_anthropic_key}" --with-decryption --region "${region}" --query Parameter.Value --output text)
ADMIN_PASS=$(aws ssm get-parameter --name "${ssm_admin_password}" --with-decryption --region "${region}" --query Parameter.Value --output text)

cat > "$APP_DIR/backend/.env" <<EOF
DATABASE_URL=postgresql://${db_username}:$${DB_PASS}@${db_endpoint}:5432/${db_name}
JWT_SECRET=$${JWT_SECRET}
ANTHROPIC_API_KEY=$${ANTHROPIC_KEY}
BOOTSTRAP_ADMIN_EMAIL=${admin_email}
BOOTSTRAP_ADMIN_PASSWORD=$${ADMIN_PASS}
REDIS_URL=redis://localhost:6379/0
BEDROCK_REGION=${region}

# If you want EC2 inference to call your home Ollama via Tailscale, override:
# OLLAMA_BASE_URL=http://<your-home-tailscale-ip>:11434
# Otherwise local fallbacks just won't work for cheap/standard tiers — set companies
# to use_cloud_api=true and a cloud_provider in the admin panel.
OLLAMA_BASE_URL=http://localhost:11434

CORS_ORIGINS=["https://*","http://*"]
EOF
chmod 640 "$APP_DIR/backend/.env"
chown sales-agent:sales-agent "$APP_DIR/backend/.env"

# ---- 7. Run migrations (only if backend code exists)
if [ -f "$APP_DIR/backend/app/main.py" ]; then
  cd "$APP_DIR/backend"
  for phase in migrate_phase2 migrate_phase3 migrate_phase4 migrate_phase5; do
    sudo -u sales-agent "$APP_DIR/venv/bin/python" -m "app.db.$phase" || echo "$phase failed (may be ok if already run)"
  done
  if [ -f "$APP_DIR/backend/app/db/bootstrap_admin.py" ]; then
    sudo -u sales-agent "$APP_DIR/venv/bin/python" -m app.db.bootstrap_admin || true
  fi
fi

# ---- 8. systemd unit for the app
cat > /etc/systemd/system/sales-agent.service <<'EOF'
[Unit]
Description=Sales Agent FastAPI app
After=network.target

[Service]
Type=simple
User=sales-agent
Group=sales-agent
WorkingDirectory=/opt/sales-agent/backend
EnvironmentFile=/opt/sales-agent/backend/.env
ExecStart=/opt/sales-agent/venv/bin/gunicorn app.main:app \
  --workers 2 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 127.0.0.1:8000 \
  --access-logfile /var/log/sales-agent/access.log \
  --error-logfile /var/log/sales-agent/error.log \
  --timeout 240
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable sales-agent || true
if [ -f "$APP_DIR/backend/app/main.py" ]; then
  systemctl restart sales-agent
fi

# ---- 9. Caddyfile — auto-HTTPS if DOMAIN_NAME env is set, else self-signed for IP
PUBLIC_IP=$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 || echo "")
cat > /etc/caddy/Caddyfile <<EOF
{
  # Use an email for Let's Encrypt registration if you have a real domain
  # email you@example.com
}

# When you point a real domain at this IP, replace ":443" with your hostname
# and Caddy will auto-issue a Let's Encrypt cert.
:443 {
  tls internal
  reverse_proxy 127.0.0.1:8000
}

:80 {
  redir https://{host}{uri}
}
EOF
systemctl reload caddy || systemctl restart caddy

echo "=== user-data finished at $(date -Iseconds) ==="
echo "App public IP: $PUBLIC_IP"
echo "Test: curl -k https://$PUBLIC_IP/api/health"
