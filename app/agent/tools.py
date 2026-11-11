"""Agent tools.

query_metrics  read verified numbers from financial_metrics and phrase them deterministically
               (no LLM: the number in the answer is the number in the table, with its page)
compare        rank companies or compute year-over-year changes from those rows
search_text    the M3 RAG pipeline (hybrid retrieval + LLM), optionally pinned to one company
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import FinancialMetric
from app.rag import COMPANY_NAMES, Answer, Citation, answer

LABELS = {
    "revenue": "consolidated revenue from operations",
    "net_profit": "consolidated profit for the year",
    "operating_margin": "operating margin",
    "headcount": "number of permanent employees",
    "attrition": "attrition (turnover rate for permanent employees)",
}
PERCENT = {"operating_margin", "attrition"}


@dataclass
class MetricValue:
    company: str
    fiscal_year: int
    metric: str
    value: float
    unit: str
    currency: str | None
    source_page: int

    @property
    def in_crore(self) -> float:
        """Money in ₹ crore so companies reporting in ₹ million can be ranked together."""
        if self.currency == "INR" and self.unit == "million":
            return self.value / 10
        return self.value


def indian(n: float) -> str:
    """Indian digit grouping: 255324 -> '2,55,324'."""
    neg, n = n < 0, abs(n)
    whole, frac = f"{n:.2f}".split(".")
    head, tail = whole[:-3], whole[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    s = ",".join([*groups, tail]) if groups else tail
    if frac.strip("0"):
        s += "." + frac.rstrip("0")
    return ("-" if neg else "") + s


def fmt(v: MetricValue) -> str:
    if v.metric in PERCENT:
        return f"{v.value:g}%"
    if v.unit == "count":
        return indian(v.value)
    if v.currency == "INR" and v.unit == "crore":
        return f"₹{indian(v.value)} crore"
    if v.currency == "INR" and v.unit == "million":
        # Reported in millions with western grouping (as the report prints it).
        return f"₹{v.value:,.0f} million (≈ ₹{indian(round(v.in_crore))} crore)"
    return f"{v.value:g} {v.currency or ''} {v.unit}".strip()


def query_metrics(
    session: Session, metric: str, companies: list[str], years: list[int]
) -> list[MetricValue]:
    stmt = select(FinancialMetric).where(
        FinancialMetric.metric == metric,
        FinancialMetric.company.in_(companies),
        FinancialMetric.fiscal_year.in_(years),
    )
    return [
        MetricValue(m.company, m.fiscal_year, m.metric, m.value, m.unit, m.currency, m.source_page)
        for m in session.scalars(stmt)
    ]


class _Cites:
    """Collects citations and hands out [n] markers, one per distinct page."""

    def __init__(self):
        self.items: list[Citation] = []

    def mark(self, v: MetricValue) -> str:
        for c in self.items:
            if (c.company, c.fiscal_year, c.page) == (v.company, v.fiscal_year, v.source_page):
                return f"[{c.n}]"
        c = Citation(len(self.items) + 1, v.company, v.fiscal_year, v.source_page)
        self.items.append(c)
        return f"[{c.n}]"


def _name(company: str) -> str:
    return COMPANY_NAMES.get(company, company)


def compare(
    question: str,
    values: list[MetricValue],
    metric: str,
    companies: list[str],
    years: list[int],
    change: bool,
    rank: bool,
) -> Answer:
    """Turn metric rows into a cited answer: single values, year-over-year changes, rankings."""
    cites = _Cites()
    got = {(v.company, v.fiscal_year): v for v in values}
    label = LABELS[metric]
    sentences, missing = [], []

    if change and len(years) > 1:
        first, last = years[0], years[-1]
        deltas = []
        for c in companies:
            a, b = got.get((c, first)), got.get((c, last))
            if not (a and b):
                missing.append(c)
                continue
            if metric in PERCENT:
                d = b.value - a.value
                how = f"a change of {d:+.1f} percentage points"
            else:
                d = (b.value - a.value) / a.value * 100
                how = f"a change of {d:+.1f}%"
            deltas.append((d, c))
            sentences.append(
                f"{_name(c)}'s {label} went from {fmt(a)} in FY{first} {cites.mark(a)} to "
                f"{fmt(b)} in FY{last} {cites.mark(b)}, {how}."
            )
        if rank and len(deltas) > 1:
            best = max(deltas)
            sentences.append(f"{_name(best[1])} had the largest increase.")
    else:
        rows = []
        for y in years:
            for c in companies:
                v = got.get((c, y))
                if v:
                    rows.append(v)
                else:
                    missing.append(c)
        if rank and len(rows) > 1:
            rows.sort(key=lambda v: (v.fiscal_year, -v.in_crore))
        for v in rows:
            sentences.append(
                f"{_name(v.company)}'s {label} in FY{v.fiscal_year} was {fmt(v)} {cites.mark(v)}."
            )
        if rank and len(rows) > 1:
            for y in years:
                year_rows = [v for v in rows if v.fiscal_year == y]
                if len(year_rows) > 1:
                    hi, lo = year_rows[0], year_rows[-1]
                    sentences.append(
                        f"In FY{y}, highest: {_name(hi.company)} ({fmt(hi)}); "
                        f"lowest: {_name(lo.company)} ({fmt(lo)})."
                    )

    if missing:
        names = ", ".join(_name(c) for c in dict.fromkeys(missing))
        sentences.append(f"No {label} figure is stated in a table for: {names}.")
    if not cites.items:
        return Answer(question, "", [], True)
    return Answer(question, " ".join(sentences), cites.items, False)


def search_text(question: str, retrieve, llm, k: int = 5, companies=None, years=None) -> Answer:
    if companies is None and years is None:
        return answer(question, retrieve=retrieve, llm=llm, k=k)

    def pinned(q, kk):
        return retrieve(q, kk, companies=companies, years=years)

    return answer(question, retrieve=pinned, llm=llm, k=k)


CHANGE_HINT = (
    "\n\n(For a change between years: state each year's value with its citation, then the "
    "percentage change.)"
)


def search_text_change(question: str, retrieve, llm, k: int, companies, years) -> Answer:
    """Text answer about a change: retrieve each year separately so both years' pages are in
    the context, then ask once. A single search tends to return pages from only one year."""
    per_year = max(2, k // len(years) + 1)

    def both_years(q, kk):
        hits, seen = [], set()
        for y in years:
            for h in retrieve(q, per_year, companies=companies or None, years=[y]):
                if h.chunk_id not in seen:
                    seen.add(h.chunk_id)
                    hits.append(h)
        return hits

    a = answer(question + CHANGE_HINT, retrieve=both_years, llm=llm, k=k)
    a.question = question
    return a
