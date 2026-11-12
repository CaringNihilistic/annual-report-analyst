#!/bin/bash
# Space start-up: Postgres inside this container (localhost only), restore the database
# from the private dataset $DATA_REPO (needs the HF_TOKEN secret), then the app on :7860.
set -euo pipefail
export PGHOST=127.0.0.1 PGUSER=rag
DUMP=/tmp/annual_reports.dump

if [ ! -s "$PGDATA/PG_VERSION" ]; then
  # trust auth is safe here: Postgres listens on 127.0.0.1 inside the container only.
  initdb -D "$PGDATA" -U rag --auth=trust >/dev/null
fi
pg_ctl -D "$PGDATA" -l /tmp/postgres.log -w -o "-c listen_addresses=127.0.0.1 -k /tmp" start

if ! psql -d annual_reports -tAc "SELECT 1 FROM chunks LIMIT 1" >/dev/null 2>&1; then
  createdb annual_reports
  if [ -f /data/annual_reports.dump ]; then  # local testing: docker run -v <dir>:/data
    cp /data/annual_reports.dump "$DUMP"
  else
    echo "downloading the database dump from $DATA_REPO"
    HF_HUB_OFFLINE=0 python - <<'PY'
import os
from huggingface_hub import hf_hub_download

hf_hub_download(os.environ["DATA_REPO"], "annual_reports.dump", repo_type="dataset",
                token=os.environ.get("HF_TOKEN"), local_dir="/tmp")
PY
  fi
  # Warnings about ownership are expected (--no-owner); the row count below is the real check.
  pg_restore -d annual_reports --no-owner --no-privileges "$DUMP" || true
  rm -f "$DUMP"
  n=$(psql -d annual_reports -tAc "SELECT count(*) FROM chunks")
  echo "restored $n chunks"
  [ "$n" -gt 0 ] || { echo "restore failed"; exit 1; }
fi

exec uvicorn app.api:app --host 0.0.0.0 --port 7860
