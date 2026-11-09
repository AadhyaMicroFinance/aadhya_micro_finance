#!/usr/bin/env bash
# EC2 user-data: one-time host preparation. Safe to re-run.
set -euxo pipefail
exec > >(tee -a /var/log/finance-chitti-bootstrap.log) 2>&1

timedatectl set-timezone Asia/Kolkata || true

# --- Docker Engine + Compose plugin ---------------------------------------
dnf -y install docker git tar gzip || true
systemctl enable --now docker
usermod -aG docker ec2-user || true

if ! docker compose version >/dev/null 2>&1; then
  mkdir -p /usr/libexec/docker/cli-plugins
  curl -fsSL "https://github.com/docker/compose/releases/download/v2.29.7/docker-compose-linux-x86_64" \
    -o /usr/libexec/docker/cli-plugins/docker-compose
  chmod +x /usr/libexec/docker/cli-plugins/docker-compose
fi

# --- 2 GB swap: gives the Next.js build headroom on a 4 GB host -----------
if [ ! -f /swapfile ]; then
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
fi
grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab

# --- AWS CLI for off-host backups (optional; backup.sh degrades safely) ---
dnf -y install awscli || dnf -y install awscli2 || true

# --- App + backup directories ---------------------------------------------
install -d -o ec2-user -g ec2-user /opt/finance-chitti
install -d -m 700 /var/backups/finance-chitti

# --- Nightly Postgres backup at 02:15 IST ----------------------------------
# Amazon Linux 2023 ships without cron; install it before writing the schedule.
dnf -y install cronie || true
systemctl enable --now crond || true
install -d -m 755 /etc/cron.d

cat > /etc/cron.d/finance-chitti-backup <<'CRON'
SHELL=/bin/bash
PATH=/usr/local/bin:/usr/bin:/bin
15 2 * * * root /opt/finance-chitti/deploy/aws/backup.sh >> /var/log/finance-chitti-backup.log 2>&1
CRON
chmod 644 /etc/cron.d/finance-chitti-backup

echo "bootstrap complete"
