#!/usr/bin/env bash
# Create deploy/aws/.env with generated secrets and the first admin account.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

if [ -f .env ]; then
  echo ".env already exists here - delete it first if you really want to regenerate." >&2
  exit 1
fi

cp .env.prod.example .env

set_key() {
  awk -v k="$1" -v v="$2" 'BEGIN{FS=OFS="="} $1==k{print k"="v; next} {print}' .env > .env.tmp
  mv .env.tmp .env
}

set_key POSTGRES_PASSWORD "$(openssl rand -hex 24)"
set_key JWT_SECRET "$(openssl rand -hex 48)"

printf "Admin username [admin]: "
read -r ADMIN_USERNAME
ADMIN_USERNAME="${ADMIN_USERNAME:-admin}"

printf "Admin email [admin@example.com]: "
read -r ADMIN_EMAIL
ADMIN_EMAIL="${ADMIN_EMAIL:-admin@example.com}"

while :; do
  printf "Admin password (min 8 chars, not echoed): "
  read -rs ADMIN_PASSWORD
  echo
  if [ "${#ADMIN_PASSWORD}" -ge 8 ]; then break; fi
  echo "Too short - try again."
done

set_key ADMIN_USERNAME "$ADMIN_USERNAME"
set_key ADMIN_EMAIL "$ADMIN_EMAIL"
set_key ADMIN_PASSWORD "$ADMIN_PASSWORD"

chmod 600 .env
echo
echo "Created $PWD/.env"
echo "Set BACKUP_BUCKET (terraform output backup_bucket) before the first deploy."
