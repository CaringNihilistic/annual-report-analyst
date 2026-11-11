"""Embed parsed chunks and load chunks + financial_metrics into Postgres.

Usage:
    python -m ingest.index                 # load every parsed report in data/processed
    python -m ingest.index --only infosys_FY2025

Re-running is safe: a report's existing rows are deleted before its new rows are inserted.

What gets indexed (built here from the parsed JSON, so changing it needs no re-parse):
- text chunks, minus heading-only ones ("TCS' Business"), which carry no content;
- tables, one or more chunks each, as "label | value | value" rows under their header, so
  figures like "Revenue from operations | 2,55,324" are searchable.
The section heading is prepended to the text that is embedded (not the stored text).
"""

import argparse
import json
import re
from collections.abc import Callable
from dataclasses import asdict

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Chunk, FinancialMetric, get_engine, init_db
from ingest.parse import MAX_CHUNK_CHARS
from ingest.tables import column_groups, extract_metrics, header_texts

EmbedFn = Callable[[list[str]], list[list[float]]]


def _norm(s: str | None) -> str:
    return re.sub(r"\s+", " ", s or "").strip().lower()


def table_chunks(table: dict, max_chars: int = MAX_CHUNK_CHARS) -> list[dict]:
    """Serialise a table as text, split into chunks that each repeat the title and header."""
    rows = table["rows"]
    if len(rows) < 2:
        return []
    header = header_texts(rows)
    # Spanning headers name "Standalone" / "Consolidated" only on a group's first column;
    # label every column so the LLM can't take a standalone figure for a consolidated one.
    header = [
        f"{g.title()} {h}".strip() if g and g not in h.lower() else h
        for g, h in zip(column_groups(header), header, strict=True)
    ]
    title = table.get("caption") or table.get("section") or "Table"
    context = table.get("context") or ""
    lines = [f"Table: {title}"]
    if context and len(context) < 150:  # short context is usually the unit, e.g. "(₹ crore)"
        lines.append(context)
    lines.append(" | ".join(h for h in header))
    head = "\n".join(lines)

    body = []
    for row in rows[1:]:
        cells = [c.strip() for c in row]
        if any(cells) and cells != header:
            body.append(" | ".join(cells))

    chunks, cur = [], []
    for line in body:
        if cur and len(head) + sum(len(x) + 1 for x in cur) + len(line) > max_chars:
            chunks.append(cur)
            cur = []
        cur.append(line[:max_chars])
    if cur:
        chunks.append(cur)
    return [
        {"page": table["page"], "section": table.get("section"), "text": f"{head}\n" + "\n".join(c)}
        for c in chunks
    ]


def index_chunks(doc: dict) -> list[dict]:
    """Chunks to index for one report: text chunks (minus heading-only ones) plus tables."""
    out = [c for c in doc["chunks"] if _norm(c["text"]) and _norm(c["text"]) != _norm(c["section"])]
    for table in doc["tables"]:
        out += table_chunks(table)
    return out


def embed_text(chunk: dict) -> str:
    section = chunk.get("section")
    if section and not _norm(chunk["text"]).startswith(_norm(section)):
        return f"{section}\n{chunk['text']}"
    return chunk["text"]


def load_embedder(model_name: str) -> EmbedFn:
    from sentence_transformers import SentenceTransformer  # heavy import, only when indexing

    model = SentenceTransformer(model_name)
    return lambda texts: model.encode(
        texts, batch_size=64, normalize_embeddings=True, show_progress_bar=True
    ).tolist()


def build_rows(doc: dict, embed: EmbedFn) -> tuple[list[Chunk], list[FinancialMetric]]:
    """ORM rows for one parsed report. Pure apart from the embed call, so it is unit-testable."""
    company, fy = doc["company"], doc["fiscal_year"]
    items = index_chunks(doc)
    vectors = embed([embed_text(c) for c in items]) if items else []
    chunks = [
        Chunk(
            company=company,
            fiscal_year=fy,
            page=c["page"],
            section=c["section"],
            text=c["text"],
            embedding=v,
        )
        for c, v in zip(items, vectors, strict=True)
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
