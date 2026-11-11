# AWS deployment

The demo runs on one small EC2 server in Sydney (`ap-southeast-2`), paid from the AWS Free plan credits. Postgres and the app run as two Docker containers on it. The server is **stopped when not demoing**.

```
 browser ──HTTP :80──► EC2 t3.small (Amazon Linux 2023, Docker)
                         ├─ api  container  (ghcr.io image, FastAPI + UI, models baked in)
                         └─ db   container  (pgvector/pg16, no public port)
                         │
                         ├─ reads API keys ──► SSM Parameter Store (/ragg/*, SecureString)
                         └─ first boot only ─► S3 (database dump)
 GitHub Actions ──builds──► ghcr.io/caringnihilistic/annual-report-analyst:latest
```

## Day-to-day

```powershell
powershell -ExecutionPolicy Bypass -File deploy\aws.ps1 status     # state + URL
powershell -ExecutionPolicy Bypass -File deploy\aws.ps1 start      # new public IP each time
powershell -ExecutionPolicy Bypass -File deploy\aws.ps1 stop       # do this after every demo
powershell -ExecutionPolicy Bypass -File deploy\aws.ps1 logs       # first-boot log + container status
```

After `start`, the app needs about a minute, and the first question loads the models (about 30 s more).

**Ship a new version:** push to `master`. The Image workflow publishes a new `:latest`. Then run on the server through Session Manager (or `aws ssm send-command`):

```bash
cd /opt/ragg && docker compose pull -q api && docker compose up -d api && docker image prune -f
```

## Resources

| Resource | Name | Purpose |
|---|---|---|
| AWS Budget | `ragg-monthly-1usd` | Emails an alert when spend (credits excluded) passes $1/month |
| SSM parameters | `/ragg/groq_api_key`, `/ragg/anthropic_api_key` | API keys, SecureString, written by `deploy/put-secrets.ps1` |
| S3 bucket | `ragg-deploy-885879439469` | Holds `annual_reports.dump` (46.5 MiB, `pg_dump -Fc` of the local DB), private |
| IAM role + instance profile | `ragg-ec2-role`, `ragg-ec2-profile` | `AmazonSSMManagedInstanceCore` (Session Manager) + read `/ragg/*` and that one S3 object, nothing else |
| Security group | `ragg-web` | Inbound TCP 80 only. No SSH port |
| EC2 instance | `ragg-app` | t3.small, 2 vCPU / 2 GB + 2 GB swap, 20 GB encrypted gp3, unlimited CPU credits |

The image lives on GitHub Container Registry (public, free), not ECR, so there is no registry cost and the server needs no registry credentials.

## What it costs

Sydney list prices, paid from the $100 Free plan credits (they expire 2027-05-11). The Free plan never bills a card; when credits run out, the account is paused, not charged.

| State | Cost |
|---|---|
| Running | t3.small $0.0264/h + public IPv4 $0.005/h + disk ≈ **$0.034/h (~$0.80/day)** |
| Stopped | 20 GB gp3 ≈ **$1.92/month**; S3 and parameters ≈ $0 |
| Unlimited CPU credits | Surplus credits $0.05 per vCPU-hour, only when the 24 h average CPU exceeds 20%. A 30 s text answer, even with both vCPUs flat out, uses under $0.001 |
| Always on (for comparison) | ≈ $24.5/month |

## Security choices

- **No SSH at all.** Admin access is Session Manager through the instance role, so there is no key pair to leak and no port 22 open.
- **Secrets never touch git, the image or user data.** The server reads them from Parameter Store at first boot into a root-only file (`/opt/ragg/.env`, mode 600). The Postgres password is random, generated on the server.
- **Least privilege.** The role can read only `/ragg/*` and one S3 object.
- **IMDSv2 required** (hop limit 2, so containers could use it if needed): this blocks SSRF-style credential theft.
- **Postgres has no published port.** Only the api container can reach it.
- **Encrypted disk**, deleted with the instance.
- **Not done:** HTTPS. There is no domain, so the demo is plain HTTP. The app has no logins or personal data. Adding a domain + Caddy (Let's Encrypt) or CloudFront would fix it.

## Why this design

- **EC2 + Docker Postgres instead of App Runner/ECS + RDS.** It is Free plan eligible, costs about $0.80 a running day, and can be stopped to near zero. RDS would add a second always-billed resource, and App Runner can't be stopped in the same way. The trade-off is no managed backups or automatic failover, which a demo does not need; the data can be rebuilt from the dump.
- **t3.small.** The smallest Free-plan type with enough memory: the models take about 0.85 GB.
- **Unlimited CPU credits.** In standard mode the server spent its credits during first boot and was then throttled to 20% CPU (112 s per text answer). Unlimited mode bills surplus usage instead: under $0.001 per question.
- **Pull a prebuilt image.** Building the image (CPU torch + two models) on a 2 GB server takes about 15 minutes; pulling it takes about 1.

## Latency on this server

Measured on the deployed t3.small:

- Figures, comparisons and refusals: **under 1 s** (answered from `financial_metrics`, no reranker, often no LLM).
- Questions about the report text: **30–40 s**. Almost all of it is the `bge-reranker-base` cross-encoder (278M parameters) scoring candidates on 2 slow vCPUs: about 13–15 s per pass, and comparison or year-over-year text questions run more than one pass.
- **Tried and rejected:** an 8-bit quantized reranker was only about 20% faster (12 s vs 15 s) and changed the top 5 passages for all 3 test questions, so the evaluated fp32 model was kept.
- **Options not taken:** a bigger instance (c7i-flex.large, $0.11/h, about 4× the price), or fewer rerank candidates / a smaller reranker. Both change cost or quality; the smaller reranker scored worse in M3.

## First launch (already done) and teardown

One-time setup, in order: create the budget; run `deploy\put-secrets.ps1`; create the bucket and upload the dump; create the role, instance profile and security group; then `aws.ps1 launch`. `deploy/user-data.sh` does the rest on first boot (swap, Docker, keys, restore, start) and logs to `/var/log/ragg-setup.log`.

To make the dump from the local database (Git Bash needs `MSYS_NO_PATHCONV=1`):

```bash
docker exec ragg-db-1 pg_dump -U rag -d annual_reports -Fc -f /tmp/annual_reports.dump
docker cp ragg-db-1:/tmp/annual_reports.dump . && aws s3 cp annual_reports.dump s3://ragg-deploy-885879439469/
```

`aws.ps1 teardown` deletes the instance (and its disk), security group, IAM role and profile, bucket and parameters. The budget is kept, since it is free and keeps watching the account.
