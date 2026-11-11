"""Build a retriever by name, for the CLI and the evals."""

from sqlalchemy.orm import Session

from app.retrieval.hybrid import HybridRetriever, Reranker, Retriever, VectorRetriever

MODES = {
    "vector": "vector search only (M2 baseline)",
    "hybrid": "BM25 + vector, reciprocal rank fusion",
    "rerank": "BM25 + vector, fused, then cross-encoder rerank (default)",
}


def make_retriever(mode: str, session: Session, embed) -> Retriever:
    if mode == "vector":
        return VectorRetriever(session, embed)
    if mode == "hybrid":
        return HybridRetriever(session, embed)
    if mode == "rerank":
        return HybridRetriever(session, embed, reranker=Reranker())
    raise ValueError(f"unknown retrieval mode {mode!r}; choose from {sorted(MODES)}")
