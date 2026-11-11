# App image: FastAPI + agent + retrieval, CPU only. Build: docker build -t ragg-api .
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/models \
    HF_HUB_DISABLE_TELEMETRY=1

WORKDIR /srv

# CPU-only torch first: the default Linux wheel pulls ~2.5 GB of CUDA libraries.
RUN pip install torch==2.14.1 --index-url https://download.pytorch.org/whl/cpu
COPY requirements-app.txt .
RUN pip install -r requirements-app.txt

# Unprivileged user. Created before the model download: chown-ing files after they are
# written would store a second copy of them (~1.2 GB) in a new layer.
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /models /srv/.cache && chown appuser /models /srv/.cache
USER appuser

# Bake the embedding model (~90 MB) and reranker (~1.1 GB) into the image so containers start
# without downloads.
RUN python -c "from sentence_transformers import SentenceTransformer, CrossEncoder; \
SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2'); CrossEncoder('BAAI/bge-reranker-base')"
ENV HF_HUB_OFFLINE=1

COPY app ./app
COPY ingest ./ingest

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"
CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000"]
