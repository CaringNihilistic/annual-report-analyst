"""Embed parsed chunks and load chunks + financial_metrics into Postgres.

Usage:
    python -m ingest.index                 # load every parsed report in data/processed
    python -m ingest.index --only infosys_FY2025

Re-running is safe: a report's existing rows are deleted before its new rows are inserted.
"""

import argparse
import json
from collections.abc import Callable
from dataclasses import asdict

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Chunk, FinancialMetric, get_engine, init_db
from ingest.tables import extract_metrics

EmbedFn = Callable[[list[str]], list[list[float]]]


def load_embedder(model_name: str) -> EmbedFn:
    from sentence_transformers import SentenceTransformer  # heavy import, only when indexing

    model = SentenceTransformer(model_name)
    return lambda texts: model.encode(
        texts, batch_size=64, normalize_embeddings=True, show_progress_bar=True
    ).tolist()


def build_rows(doc: dict, embed: EmbedFn) -> tuple[list[Chunk], list[FinancialMetric]]:
    """ORM rows for one parsed report. Pure apart from the embed call, so it is unit-testable."""
    company, fy = doc["company"], doc["fiscal_year"]
    texts = [c["text"] for c in doc["chunks"]]
    vectors = embed(texts) if texts else []
    chunks = [
        Chunk(
            company=company,
            fiscal_year=fy,
            page=c["page"],
            section=c["section"],
            text=c["text"],
            embedding=v,
        )
        for c, v in zip(doc["chunks"], vectors, strict=True)
    ]
    metrics = [FinancialMetric(**asdict(m)) for m in extract_metrics(doc)]
    return chunks, metrics


def load_report(session: Session, doc: dict, embed: EmbedFn) -> tuple[int, int]:
    company, fy = doc["company"], doc["fiscal_year"]
    chunks, metrics = build_rows(doc, embed)
    for model in (Chunk, FinancialMetric):
        session.execute(delete(model).where(model.company == company, model.fiscal_year == fy))
    session.add_all(chunks + metrics)
    return len(chunks), len(metrics)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--only", help="load just this report, e.g. infosys_FY2025")
    args = ap.parse_args()

    s = get_settings()
    files = sorted(s.processed_dir.glob("*.json"))
    if args.only:
        files = [f for f in files if f.stem == args.only]
    if not files:
        raise SystemExit(f"No parsed reports in {s.processed_dir}. Run python -m ingest.parse")

    engine = get_engine()
    init_db(engine)
    embed = load_embedder(s.embedding_model)
    for f in files:
        doc = json.loads(f.read_text(encoding="utf-8"))
        with Session(engine) as session, session.begin():
            n_chunks, n_metrics = load_report(session, doc, embed)
        print(f"{f.stem}: {n_chunks} chunks, {n_metrics} metrics loaded")


if __name__ == "__main__":
    main()
