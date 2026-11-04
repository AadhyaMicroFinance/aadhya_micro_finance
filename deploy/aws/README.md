# Deploying Finance & Chitti to AWS

Runs the whole stack on one EC2 host with Docker Compose behind Caddy:

```
Internet ──▶ Caddy :80/:443 (HTTPS once you add a domain)
                ├── /api/*, /health, /docs ──▶ backend  (FastAPI, 2 uvicorn workers)
                └── everything else        ──▶ web      (Next.js standalone)
                                                   │
                       postgres ◀── celery_worker / celery_beat ──▶ redis
```

Only ports 80/443 are public. Postgres, Redis, the API and the web server have
no host ports at all — they talk over Docker's private network.

**Cost:** ≈ $37/month in `ap-south-1` — t3.medium $30, 40 GB gp3 $3.2,
Elastic IP $3.6, S3 backups a few cents. A Savings Plan lowers it.

Pick one path:

- **[Path A — AWS Console](#path-a--aws-console-no-terraform)** (no Terraform/AWS CLI needed)
- **[Path B — Terraform](#path-b--terraform-optional)**

---

## Path A — AWS Console (no Terraform)

You create five things; the scripts handle the rest.

| # | What | Why |
|---|------|-----|
| 1 | Key pair | SSH access for deploys |
| 2 | Security group | 22 from your IP, 80/443 from anywhere |
| 3 | EC2 instance (AL2023, t3.medium, 40 GB gp3) | Runs every container |
| 4 | Elastic IP | Stable address, survives restarts |
| 5 | S3 bucket + IAM role *(optional)* | Offsite nightly backups |

### 1. Key pair

EC2 → **Key Pairs** → **Create key pair**
Name `finance-chitti-key`, type **RSA**, format **.pem** → it downloads automatically.
Keep the file; you need it in step 6.

### 2. Security group

EC2 → **Security Groups** → **Create security group**
Name `finance-chitti-sg`, default VPC, then add **inbound** rules:

| Type | Port | Source |
|------|------|--------|
| SSH | 22 | **My IP** |
| HTTP | 80 | Anywhere (0.0.0.0/0) |
| HTTPS | 443 | Anywhere (0.0.0.0/0) |

Leave outbound as-is (all traffic).

### 3. EC2 instance

EC2 → **Launch instance**:

- **Name:** `finance-chitti`
- **AMI:** *Amazon Linux 2023 AMI* (64-bit x86_64)
- **Instance type:** `t3.medium`
- **Key pair:** `finance-chitti-key`
- **Network:** default VPC, **Auto-assign public IP: Enable**
- **Firewall:** *Select an existing security group* → `finance-chitti-sg`
- **Configure storage:** 40 GiB, **gp3**, **Encrypted**
- **Advanced details → User data:** paste the **entire contents** of
  `deploy/aws/user-data.sh` (starts with `#!/usr/bin/env bash`)

That script installs Docker + Compose, sets the IST timezone, adds 2 GB swap for
the Next.js build, creates `/opt/finance-chitti` and installs the nightly backup
cron. Launch and wait ~2 minutes.

### 4. Elastic IP

EC2 → **Elastic IPs** → **Allocate Elastic IP address** → **Associate** it with
the `finance-chitti` instance. This IP is your app URL for now.

### 5. S3 backups (optional)

Without this the nightly `pg_dump` still runs and keeps 7 days **on the instance**
(`/var/backups/finance-chitti`); only offsite copies are skipped.

- S3 → **Create bucket** `finance-chitti-backups-<something unique>`, block all
  public access, default encryption.
- IAM → **Roles** → **Create role** → AWS service → EC2 → attach
  `AmazonSSMManagedInstanceCore`, and an inline policy allowing
  `s3:PutObject`, `s3:GetObject`, `s3:ListBucket` on that bucket.
- EC2 → instance → **Actions → Security → Modify IAM role** → attach it.

### 6. Deploy from your machine (Git Bash)

Put the key where the script expects it:

```bash
cp /c/Users/<you>/Downloads/finance-chitti-key.pem ~/.ssh/finance-chitti-aws
chmod 600 ~/.ssh/finance-chitti-aws
```

Create the production secrets and first admin:

```bash
cd D:/Vayu/Finance/finance-chitti-system/deploy/aws
bash init-env.sh          # generates DB/JWT secrets, asks for admin username/password
```

If you created a bucket, set `BACKUP_BUCKET=finance-chitti-backups-...` in
`deploy/aws/.env`. Then deploy (first run builds images on the instance, 5–8 min):

```bash
bash deploy.sh <elastic-ip>
```

It uploads the code, builds, runs migrations, creates the admin, starts the
stack and waits for `/health`.

### 7. Open it

`http://<elastic-ip>` → log in with the admin credentials from step 6.

Verify:

```bash
curl http://<elastic-ip>/health
curl -I http://<elastic-ip>/login
```

Later redeploys are the same single command: `bash deploy.sh <elastic-ip>`.

---

## Path B — Terraform (optional)

Creates the same resources plus IAM/SSM and the backup bucket, reproducibly.

```bash
winget install --id Amazon.AWSCLI -e
winget install --id HashiCorp.Terraform -e
aws configure                     # region ap-south-1
ssh-keygen -t ed25519 -f ~/.ssh/finance-chitti-aws -N ""

cd deploy/aws/terraform
cp terraform.tfvars.example terraform.tfvars
# set admin_cidr = "<your-ip>/32" so SSH is not world-open
terraform init && terraform apply

cd ..
bash init-env.sh                  # add BACKUP_BUCKET from terraform output
bash deploy.sh                    # host read from terraform output
```

---

## Adding a domain later (no downtime)

1. Point an **A record** (Route 53 or any DNS provider) at the Elastic IP.
2. Edit `deploy/aws/.env`:

   ```
   SITE_ADDRESS=finance.example.com
   ACME_EMAIL=ops@example.com
   CORS_ORIGINS=["https://finance.example.com"]
   ```

3. `bash deploy.sh <elastic-ip>`

Caddy obtains and renews the Let's Encrypt certificate and redirects HTTP to
HTTPS. Nothing else changes: the frontend calls the API same-origin (`/api/v1`).
`CORS_ORIGINS` only matters for other clients such as the mobile app.

---

## Day-2 operations

Run these on the instance (`ssh -i ~/.ssh/finance-chitti-aws ec2-user@<ip>`):

```bash
cd /opt/finance-chitti/deploy/aws
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f backend
docker compose -f docker-compose.prod.yml restart backend
docker compose -f docker-compose.prod.yml run --rm migrate sh -c 'python -m alembic upgrade head'
docker compose -f docker-compose.prod.yml exec postgres psql -U postgres finance_chitti
sudo /opt/finance-chitti/deploy/aws/backup.sh
```

Backups: cron `/etc/cron.d/finance-chitti-backup`, 02:15 IST, 7 days local,
30 days in S3.

Restore:

```bash
cd /opt/finance-chitti/deploy/aws
aws s3 cp s3://$BACKUP_BUCKET/postgres/<file>.sql.gz /tmp/restore.sql.gz
gunzip -c /tmp/restore.sql.gz | docker compose -f docker-compose.prod.yml exec -T postgres \
  psql -U postgres -d finance_chitti
```

Rollback: bump `IMAGE_TAG` in `.env` for known-good builds; to roll back, restore
the previous code (git checkout or previous tarball), set `IMAGE_TAG` back and run
`docker compose -f docker-compose.prod.yml up -d`.

---

## Security notes

- Only 80/443 public; database and Redis are unreachable from the internet.
- Secrets live in `/opt/finance-chitti/deploy/aws/.env` (mode 600) and are never
  baked into images (`.dockerignore` excludes `.env`).
- `DEBUG=false`, so API docs (`/docs`) return 404 in production.
- IMDSv2 enforced by the Terraform path; the console path launches the same AMI
  with IMDSv2 by default.
- The database lives on the encrypted EBS volume. Enable EBS snapshot lifecycle
  policies for volume-level recovery, or rely on the S3 `pg_dump`.

## Known limits

- Single host, no HA. Recovery = re-attach EBS snapshot + latest S3 dump.
- Images are built on the instance (2 GB swap provided). Heavy new dependencies
  may warrant building in CI and pushing to ECR.
- Celery beat must stay at exactly one replica (two would duplicate reminders).
