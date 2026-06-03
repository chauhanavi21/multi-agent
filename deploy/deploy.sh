#!/usr/bin/env bash
# deploy.sh — run from the repo root after `terraform apply` succeeded once.
#
# What it does:
#   1. Builds the React frontend (npm run build).
#   2. Syncs dist/ to the S3 frontend bucket.
#   3. Packs the backend dir into a tarball.
#   4. Uploads tarball to s3://$FRONTEND_BUCKET/backend/latest.tar.gz.
#   5. SSHes to EC2, extracts the new code, pip-installs, runs migrations,
#      and restarts the systemd service.

set -euo pipefail

cd "$(dirname "$0")/.."

TF_DIR=infra/terraform
APP_IP=$(terraform -chdir=$TF_DIR output -raw app_public_ip)
BUCKET=$(terraform -chdir=$TF_DIR output -raw frontend_bucket)

echo "==> Target IP: $APP_IP"
echo "==> Bucket:    $BUCKET"

echo
echo "==> Building frontend"
(cd frontend && npm ci && npm run build)

echo "==> Syncing frontend to S3"
aws s3 sync frontend/dist "s3://$BUCKET/" \
    --delete \
    --cache-control "public,max-age=300" \
    --exclude "backend/*"

echo
echo "==> Packing backend"
TARBALL=$(mktemp -t sa-backend-XXXX.tar.gz)
tar --exclude='backend/venv' --exclude='backend/__pycache__' \
    --exclude='backend/*.pyc' --exclude='backend/.env' \
    -czf "$TARBALL" backend

echo "==> Uploading backend tarball"
aws s3 cp "$TARBALL" "s3://$BUCKET/backend/latest.tar.gz"

echo
echo "==> Refreshing on EC2 ($APP_IP)"
ssh -o StrictHostKeyChecking=accept-new ubuntu@"$APP_IP" "BUCKET='$BUCKET' bash -s" <<'REMOTE'
set -euxo pipefail
APP_DIR=/opt/sales-agent

sudo aws s3 cp "s3://$BUCKET/backend/latest.tar.gz" /tmp/backend.tar.gz
sudo tar -xzf /tmp/backend.tar.gz -C "$APP_DIR"
sudo chown -R sales-agent:sales-agent "$APP_DIR"

sudo -u sales-agent "$APP_DIR/venv/bin/pip" install -r "$APP_DIR/backend/requirements.txt" -q

cd "$APP_DIR/backend"
for phase in migrate_phase2 migrate_phase3 migrate_phase4 migrate_phase5; do
  sudo -u sales-agent "$APP_DIR/venv/bin/python" -m "app.db.$phase" || true
done

sudo systemctl restart sales-agent
sleep 2
sudo systemctl status sales-agent --no-pager | head -15
REMOTE

rm -f "$TARBALL"

echo
echo "==> Done."
echo "Health check: curl -k https://$APP_IP/api/health"
