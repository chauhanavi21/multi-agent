#!/usr/bin/env bash
# backup.sh — pg_dump the Postgres DB and upload to the backups S3 bucket.
# Designed to run as a cron job on the EC2 box.
#
# Install on EC2:
#   sudo cp backup.sh /opt/sales-agent/backup.sh
#   sudo chmod +x /opt/sales-agent/backup.sh
#   sudo crontab -e
#   # add line:  0 3 * * *  /opt/sales-agent/backup.sh >> /var/log/sales-agent/backup.log 2>&1
#
# Lifecycle on the S3 bucket (set up by Terraform) deletes objects older than 30 days.

set -euo pipefail

# Read .env to get DATABASE_URL
set -a
source /opt/sales-agent/backend/.env
set +a

# Find backups bucket via terraform tags (simpler: hardcode in cron call by sed-ing into the env)
# For first-pass clarity, derive it from a known prefix:
REGION="${BEDROCK_REGION:-us-east-1}"
BUCKET=$(aws s3 ls --region "$REGION" | awk '{print $3}' | grep '^sales-agent-backups-' | head -1)

if [ -z "$BUCKET" ]; then
  echo "ERROR: backups bucket not found"
  exit 1
fi

STAMP=$(date +%Y%m%d-%H%M%S)
TMP=/tmp/salesagent-$STAMP.sql.gz

PGPASSWORD=$(echo "$DATABASE_URL" | sed -E 's|.*://[^:]+:([^@]+)@.*|\1|')
PGHOST=$(echo "$DATABASE_URL" | sed -E 's|.*@([^:/]+).*|\1|')
PGUSER=$(echo "$DATABASE_URL" | sed -E 's|.*://([^:]+):.*|\1|')
PGDB=$(echo "$DATABASE_URL" | sed -E 's|.*/([^?]+).*|\1|')

export PGPASSWORD
pg_dump -h "$PGHOST" -U "$PGUSER" -d "$PGDB" --no-owner --no-acl | gzip > "$TMP"

SIZE=$(stat -c%s "$TMP")
echo "dump size: $SIZE bytes"

aws s3 cp "$TMP" "s3://$BUCKET/pg/$STAMP.sql.gz" --quiet
rm -f "$TMP"

echo "backup ok: s3://$BUCKET/pg/$STAMP.sql.gz"
