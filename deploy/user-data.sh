#!/bin/bash
# EC2 first-boot script (Amazon Linux 2023). Passed as user data by deploy/aws.ps1.
# Installs Docker, reads the API keys from Parameter Store, restores the database dump from
# S3 (first boot only) and starts Postgres + the app on port 80. Containers restart on their
# own after every stop/start, so this script only needs to run once.
# Log: /var/log/ragg-setup.log (read it through Session Manager).
set -euo pipefail
exec > >(tee -a /var/log/ragg-setup.log) 2>&1
echo "== ragg setup $(date -Is)"

REGION=ap-southeast-2
IMAGE=ghcr.io/caringnihilistic/annual-report-analyst:latest
DUMP=s3://ragg-deploy-885879439469/annual_reports.dump
APP=/opt/ragg

# 2 GB swap: the app keeps ~0.85 GB of models in memory on a 2 GB instance.
if [ ! -f /swapfile ]; then
  dd if=/dev/zero of=/swapfile bs=1M count=2048 status=none
  chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  echo '/swapfile swap swap defaults 0 0' >> /etc/fstab
fi

dnf install -y -q docker
systemctl enable --now docker
mkdir -p /usr/local/lib/docker/cli-plugins
curl -fsSL -o /usr/local/lib/docker/cli-plugins/docker-compose \
  https://github.com/docker/compose/releases/download/v2.29.7/docker-compose-linux-x86_64
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

mkdir -p "$APP" && cd "$APP"

# Secrets: read from Parameter Store with the instance role; stored only in this root-only file.
if [ ! -f .env ]; then
  umask 077
  param() { aws ssm get-parameter --region "$REGION" --name "$1" --with-decryption \
              --query Parameter.Value --output text 2>/dev/null || true; }
  {
    echo "GROQ_API_KEY=$(param /ragg/groq_api_key)"
    echo "ANTHROPIC_API_KEY=$(param /ragg/anthropic_api_key)"
    echo "DB_PASSWORD=$(openssl rand -hex 16)"
    echo "IMAGE=$IMAGE"
  } > .env
fi

cat > compose.yml <<'EOF'
services:
  db:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: rag
      POSTGRES_PASSWORD: ${DB_PASSWORD}
      POSTGRES_DB: annual_reports
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U rag -d annual_reports"]
      interval: 5s
      retries: 20
    restart: unless-stopped
    # No ports: Postgres is reachable only from the app container.

  api:
    image: ${IMAGE}
    environment:
      GROQ_API_KEY: ${GROQ_API_KEY}
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY}
      DATABASE_URL: postgresql+psycopg://rag:${DB_PASSWORD}@db:5432/annual_reports
    ports:
      - "80:8000"
    depends_on:
      db:
        condition: service_healthy
    restart: unless-stopped

volumes:
  pgdata:
EOF

docker compose pull -q
docker compose up -d db
until docker compose exec -T db pg_isready -U rag -d annual_reports >/dev/null 2>&1; do sleep 2; done

# First boot only: load the chunks and financial_metrics prepared on the laptop.
if [ ! -f .restored ]; then
  aws s3 cp "$DUMP" /tmp/annual_reports.dump --region "$REGION" --only-show-errors
  docker compose exec -T db pg_restore -U rag -d annual_reports --no-owner --clean --if-exists \
    < /tmp/annual_reports.dump || true  # warnings about missing objects on --clean are expected
  rm -f /tmp/annual_reports.dump
  docker compose exec -T db psql -U rag -d annual_reports -tAc "SELECT count(*) FROM chunks" \
    | grep -qv '^0$' && touch .restored
fi

docker compose up -d api
echo "== ragg setup done $(date -Is)"
