#!/usr/bin/env bash
# Nightly Postgres dump -> local archive -> S3 (if configured).
# Runs on the EC2 host from /etc/cron.d/finance-chitti-backup.
set -euo pipefail

APP_DIR="/opt/finance-chitti/deploy/aws"
ENV_FILE="$APP_DIR/.env"
[ -f "$ENV_FILE" ] || { echo "missing $ENV_FILE"; exit 1; }

get() { grep -E "^$1=" "$ENV_FILE" | tail -1 | cut -d= -f2-; }
DB_USER="$(get POSTGRES_USER)"
DB_NAME="$(get POSTGRES_DB)"
BUCKET="$(get BACKUP_BUCKET)"
REGION="$(get AWS_REGION)"
DB_USER="${DB_USER:-postgres}"
DB_NAME="${DB_NAME:-finance_chitti}"
REGION="${REGION:-ap-south-1}"

STAMP="$(date +%Y%m%d-%H%M%S)"
DIR="/var/backups/finance-chitti"
OUT="$DIR/${DB_NAME}-${STAMP}.sql.gz"
mkdir -p "$DIR"

cd "$APP_DIR"
docker compose -f docker-compose.prod.yml exec -T postgres \
  pg_dump -U "$DB_USER" -d "$DB_NAME" --no-owner --clean --if-exists \
  | gzip -9 > "$OUT"

echo "$(date -Is) wrote $OUT ($(du -h "$OUT" | cut -f1))"

if [ -n "$BUCKET" ] && command -v aws >/dev/null 2>&1; then
  aws s3 cp "$OUT" "s3://$BUCKET/postgres/$(basename "$OUT")" \
    --region "$REGION" --only-show-errors
  echo "$(date -Is) uploaded to s3://$BUCKET/postgres/"
else
  echo "$(date -Is) WARNING: BACKUP_BUCKET/aws CLI unavailable - local copy only"
fi

find "$DIR" -name '*.sql.gz' -mtime +7 -delete
