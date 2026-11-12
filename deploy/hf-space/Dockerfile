# Hugging Face Space (Docker SDK): the published app image plus Postgres in the same
# container, because a free Space runs a single container. Built by Hugging Face on push.
ARG BASE=ghcr.io/caringnihilistic/annual-report-analyst:latest
FROM ${BASE}

USER root
RUN apt-get update \
 && apt-get install -y --no-install-recommends postgresql-17 postgresql-17-pgvector \
 && rm -rf /var/lib/apt/lists/*
# Spaces run the container as uid 1000; give it a home and the start script.
RUN useradd --create-home --uid 1000 user
COPY --chmod=755 start.sh /srv/start.sh
USER user

# Postgres data and the LLM cache live in /tmp: a free Space has no persistent disk,
# so the database is restored from the dump on every start (about a minute).
ENV PATH=/usr/lib/postgresql/17/bin:$PATH \
    PGDATA=/tmp/pgdata \
    LLM_CACHE_DIR=/tmp/llm-cache \
    DATABASE_URL=postgresql+psycopg://rag@127.0.0.1:5432/annual_reports
EXPOSE 7860
HEALTHCHECK NONE
CMD ["/srv/start.sh"]
