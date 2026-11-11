"""Hybrid retrieval: BM25 + vector search, fused with reciprocal rank fusion, then reranked.

Why both: keyword search catches exact terms and figures ("attrition", "EBIT", "2,55,324")
that embeddings blur; vectors catch paraphrases ("staff turnover" ~ "attrition").
A cross-encoder then reads each (question, chunk) pair and reorders the fused candidates.

Retrievers are callables `retrieve(question, k) -> list[Hit]` so the RAG pipeline and the
evals can switch between them (vector / hybrid / hybrid + rerank).
"""

import re
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Chunk
from app.retrieval.vector import Hit, parse_filters, search

Retriever = Callable[[str, int], list[Hit]]
STOPWORDS = set(
    "a an and are as at be by did do does for from had has have how in is it its of on or "
    "the to was were what when which who why with during year fy fiscal company companys "
    "report annual s".split()
)


def tokenize(text: str) -> list[str]:
    """Lowercase word/number tokens. Digit groups are joined, so '2,55,324' -> '255324'."""
    t = re.sub(r"(?<=\d),(?=\d)", "", text.lower())
    return [w for w in re.findall(r"[a-z0-9]+(?:\.[0-9]+)?", t) if w not in STOPWORDS]


def rrf(rankings: list[list[int]], k: int = 60) -> list[int]:
    """Reciprocal rank fusion: score(id) = sum of 1 / (k + rank) over the rankings."""
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, 1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    return sorted(scores, key=lambda i: (-scores[i], i))


class BM25Scope:
    """BM25 over the chunks of the companies/years a question names (built once, cached)."""

    def __init__(self, hits: list[Hit]):
        from rank_bm25 import BM25Okapi

        self.hits = hits
        self.bm25 = BM25Okapi([tokenize(f"{h.section or ''} {h.text}") or ["_"] for h in hits])

    def top(self, question: str, n: int) -> list[Hit]:
        q = tokenize(question)
        if not q or not self.hits:
            return []
        scores = self.bm25.get_scores(q)
        order = sorted(range(len(self.hits)), key=lambda i: -scores[i])[:n]
        return [self.hits[i] for i in order if scores[i] > 0]


class Reranker:
    def __init__(self, model_name: str | None = None):
        from sentence_transformers import CrossEncoder  # heavy import, only when reranking

        self.model_name = model_name or get_settings().reranker_model
        self.model = CrossEncoder(self.model_name, max_length=512)

    def scores(self, question: str, texts: list[str]) -> list[float]:
        return [float(s) for s in self.model.predict([(question, t) for t in texts])]


class VectorRetriever:
    def __init__(self, session: Session, embed):
        self.session, self.embed = session, embed

    def __call__(self, question: str, k: int = 5, companies=None, years=None) -> list[Hit]:
        parsed = parse_filters(question)
        companies = parsed[0] if companies is None else companies
        years = parsed[1] if years is None else years
        return search(self.session, self.embed([question])[0], k, companies, years)


class HybridRetriever:
    def __init__(self, session: Session, embed, reranker: Reranker | None = None, n: int = 20):
        self.session, self.embed, self.reranker, self.n = session, embed, reranker, n
        self._scopes: dict[tuple, BM25Scope] = {}

    def _scope(self, companies: list[str], years: list[int]) -> BM25Scope:
        key = (tuple(companies), tuple(years))
        if key not in self._scopes:
            stmt = select(
                Chunk.id, Chunk.company, Chunk.fiscal_year, Chunk.page, Chunk.section, Chunk.text
            )
            if companies:
                stmt = stmt.where(Chunk.company.in_(companies))
            if years:
                stmt = stmt.where(Chunk.fiscal_year.in_(years))
            rows = self.session.execute(stmt).all()
            self._scopes[key] = BM25Scope([Hit(*r, distance=0.0) for r in rows])
        return self._scopes[key]

    def __call__(self, question: str, k: int = 5, companies=None, years=None) -> list[Hit]:
        """Filters default to the companies/years named in the question; pass them to override."""
        parsed = parse_filters(question)
        companies = parsed[0] if companies is None else companies
        years = parsed[1] if years is None else years
        vec = search(self.session, self.embed([question])[0], self.n, companies, years)
        kw = self._scope(companies, years).top(question, self.n)
        by_id = {h.chunk_id: h for h in kw} | {h.chunk_id: h for h in vec}
        fused = [by_id[i] for i in rrf([[h.chunk_id for h in vec], [h.chunk_id for h in kw]])]
        if not self.reranker or not fused:
            return fused[:k]
        scores = self.reranker.scores(question, [f"{h.section or ''}\n{h.text}" for h in fused])
        ranked = sorted(zip(scores, fused, strict=True), key=lambda p: -p[0])[:k]
        # Hit.distance is "lower is better", so store the negated rerank score.
        return [Hit(**{**h.__dict__, "distance": -s}) for s, h in ranked]
