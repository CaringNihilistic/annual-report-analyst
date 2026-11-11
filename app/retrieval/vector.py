"""Vector search over chunks (pgvector cosine distance), filtered by company and year.

Filters come from the question itself ("TCS", "FY25", "2024-25"), so a question about
Infosys never retrieves Wipro pages. No filter is applied for a company or year the
question doesn't name.
"""

import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Chunk

COMPANY_ALIASES = {
    "infosys": [r"\binfosys\b", r"\binfy\b"],
    "tcs": [r"\btcs\b", r"\btata consultancy\b"],
    "wipro": [r"\bwipro\b"],
    "hcltech": [r"\bhcl\s*tech\b", r"\bhcl\b", r"\bhcl technologies\b"],
    "techmahindra": [r"\btech\s*mahindra\b", r"\btechm\b"],
}
YEARS = (2025, 2026)


@dataclass
class Hit:
    chunk_id: int
    company: str
    fiscal_year: int
    page: int
    section: str | None
    text: str
    distance: float


def parse_filters(question: str) -> tuple[list[str], list[int]]:
    """Companies and fiscal years named in a question. FY25, FY2025, 2024-25 all mean 2025."""
    q = question.lower()
    companies = [c for c, pats in COMPANY_ALIASES.items() if any(re.search(p, q) for p in pats)]
    years = set()
    for fy in YEARS:
        short, prev = fy % 100, fy - 1
        patterns = [
            rf"\bfy\s*'?{short}\b",
            rf"\bfy\s*{fy}\b",
            rf"\bfiscal\s*(year\s*)?{fy}\b",
            rf"\b{prev}\s*[-–/]\s*({short}|{fy})\b",
        ]
        if any(re.search(p, q) for p in patterns):
            years.add(fy)
    return companies, sorted(years)


def search(
    session: Session,
    query_vec: list[float],
    k: int = 5,
    companies: list[str] | None = None,
    years: list[int] | None = None,
) -> list[Hit]:
    distance = Chunk.embedding.cosine_distance(query_vec)
    stmt = select(Chunk, distance.label("distance")).order_by(distance).limit(k)
    if companies:
        stmt = stmt.where(Chunk.company.in_(companies))
    if years:
        stmt = stmt.where(Chunk.fiscal_year.in_(years))
    return [
        Hit(c.id, c.company, c.fiscal_year, c.page, c.section, c.text, float(d))
        for c, d in session.execute(stmt).all()
    ]
