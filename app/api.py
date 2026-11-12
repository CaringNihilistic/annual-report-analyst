"""HTTP API: POST /ask answers one question with citations, GET /health checks the database.
GET / serves the chat page (app/static: plain HTML, CSS and JavaScript, no build step).

    uvicorn app.api:app --port 8000

The embedder and reranker load once, on the first question, and are shared by all requests.
Each request gets its own database session. Tests swap the answerer and the database check
for fakes (FastAPI dependency overrides), so they need no models, database or API keys.
"""

import logging
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import tracing
from app.agent.graph import build_agent
from app.config import get_settings
from app.db.models import get_engine
from app.llm import LLM
from app.rag import COMPANY_NAMES, Answer

STATIC = Path(__file__).parent / "static"
DISCLAIMER = "Answers come only from the companies' annual reports. Not investment advice."
log = logging.getLogger(__name__)
tracing.enable()  # sends traces only if LANGFUSE_* keys are set

app = FastAPI(
    title="Annual Report Analyst (India)",
    description="Questions over FY2025-FY2026 annual reports of five Indian IT companies, "
    "answered with page citations.",
    version="0.6.0",
)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)


class CitationOut(BaseModel):
    n: int
    company: str
    company_name: str
    fiscal_year: int
    page: int


class AskResponse(BaseModel):
    question: str
    answer: str
    citations: list[CitationOut]
    refused: bool
    model: str | None  # which LLM wrote the answer; None when no LLM was needed
    cached: bool
    disclaimer: str = DISCLAIMER


@lru_cache
def _engine():
    return get_engine()


@lru_cache
def _models():
    # Heavy imports (torch) only when the first question arrives, not at startup.
    from app.retrieval.hybrid import Reranker
    from ingest.index import load_embedder

    return load_embedder(get_settings().embedding_model), Reranker()


def get_answerer() -> Callable[[str], Answer]:
    from app.retrieval.hybrid import HybridRetriever

    embed, reranker = _models()

    def run(question: str) -> Answer:
        with Session(_engine()) as session:
            retrieve = HybridRetriever(session, embed, reranker=reranker)
            agent = build_agent(session, retrieve, LLM(), get_settings().retrieval_k)
            return tracing.traced_answer(agent, question)

    return run


def get_db_check() -> Callable[[], None]:
    def check() -> None:
        with _engine().connect() as conn:
            conn.execute(text("SELECT 1"))

    return check


@app.get("/health")
def health(check: Annotated[Callable[[], None], Depends(get_db_check)]) -> dict:
    try:
        check()
    except Exception as e:  # noqa: BLE001 - any failure means "not healthy"
        log.warning("health check failed: %s", e)
        raise HTTPException(status_code=503, detail="database unavailable") from e
    return {"status": "ok", "db": "ok"}


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest, answerer: Annotated[Callable[[str], Answer], Depends(get_answerer)]):
    try:
        a = answerer(req.question.strip())
    except Exception as e:  # noqa: BLE001 - don't leak internals (keys, SQL) to the client
        log.exception("answering failed")
        raise HTTPException(status_code=503, detail="could not answer right now") from e
    return AskResponse(
        question=a.question,
        answer=a.text,
        citations=[
            CitationOut(
                n=c.n,
                company=c.company,
                company_name=COMPANY_NAMES.get(c.company, c.company),
                fiscal_year=c.fiscal_year,
                page=c.page,
            )
            for c in a.citations
        ],
        refused=a.refused,
        model=a.completion.model if a.completion else None,
        cached=bool(a.completion and a.completion.cached),
    )
