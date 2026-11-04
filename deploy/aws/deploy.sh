#!/usr/bin/env bash
# Build and (re)deploy the production stack on the EC2 host.
#
#   bash deploy/aws/deploy.sh              # ip from terraform output
#   bash deploy/aws/deploy.sh 1.2.3.4      # explicit Elastic IP
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
TF_DIR="$HERE/terraform"
KEY="${SSH_KEY:-$HOME/.ssh/finance-chitti-aws}"
REMOTE_USER="${REMOTE_USER:-ec2-user}"
REMOTE_DIR="/opt/finance-chitti"

if [ ! -f "$HERE/.env" ]; then
  echo "Missing $HERE/.env - run: bash $HERE/init-env.sh" >&2
  exit 1
fi

HOST="${1:-}"
if [ -z "$HOST" ]; then
  HOST="$(terraform -chdir="$TF_DIR" output -raw public_ip 2>/dev/null || true)"
fi
if [ -z "$HOST" ]; then
  echo "Usage: deploy.sh <elastic-ip>  (or run 'terraform apply' first)" >&2
  exit 1
fi

echo "==> Packaging application"
ARCHIVE="$(mktemp -t finance-chitti.XXXXXX).tar.gz"
tar -czf "$ARCHIVE" -C "$ROOT" \
  --exclude='__pycache__' --exclude='*.pyc' --exclude='.pytest_cache' \
  --exclude='node_modules' --exclude='.next' --exclude='out' \
  --exclude='*.log' --exclude='.env' --exclude='.venv' --exclude='venv' \
  --exclude='.terraform' --exclude='*.tfstate' --exclude='*.tfstate.*' \
  backend web docker/postgres deploy/aws

SSH_OPTS=(-i "$KEY" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15)
export MSYS_NO_PATHCONV=1

echo "==> Uploading to $REMOTE_USER@$HOST"
scp "${SSH_OPTS[@]}" "$ARCHIVE" "$REMOTE_USER@$HOST:/tmp/finance-chitti.tar.gz"
scp "${SSH_OPTS[@]}" "$HERE/.env" "$REMOTE_USER@$HOST:/tmp/finance-chitti.env"

echo "==> Building and starting containers (first build takes several minutes)"
ssh "${SSH_OPTS[@]}" "$REMOTE_USER@$HOST" "REMOTE_DIR='$REMOTE_DIR' bash -s" <<'REMOTE'
set -euo pipefail
sudo install -d -o "$(id -un)" -g "$(id -gn)" "$REMOTE_DIR"
tar -xzf /tmp/finance-chitti.tar.gz -C "$REMOTE_DIR"
install -m 600 /tmp/finance-chitti.env "$REMOTE_DIR/deploy/aws/.env"
rm -f /tmp/finance-chitti.tar.gz /tmp/finance-chitti.env
chmod +x "$REMOTE_DIR"/deploy/aws/*.sh
cd "$REMOTE_DIR/deploy/aws"
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d --remove-orphans
docker compose -f docker-compose.prod.yml ps
REMOTE

echo "==> Waiting for the app to become healthy"
for _ in $(seq 1 60); do
  if curl -fsS "http://$HOST/health" >/dev/null 2>&1; then
    echo "Deployed: http://$HOST"
    exit 0
  fi
  sleep 5
done

echo "App did not answer /health within 5 minutes." >&2
echo "Inspect: ssh -i $KEY $REMOTE_USER@$HOST 'cd $REMOTE_DIR/deploy/aws && docker compose -f docker-compose.prod.yml ps && docker compose -f docker-compose.prod.yml logs --tail=100'" >&2
exit 1
