"""Decide how to answer a question: from the metrics table, from text search, both, or not at all.

Rule-based on purpose: it is deterministic, free, unit-testable, and text injected into a
question can't talk it into a different route. Routes:

  refuse        investment advice / share prices, or a metric for a company we don't cover
  metrics       a covered metric (one or more companies/years, including changes and rankings)
  metrics+text  a metric plus a "why/what drove" part: numbers from the table, reasons from text
  compare_text  a non-metric question about several companies: search each one separately
  text          everything else: hybrid search + LLM answer with citations
"""

import re
from dataclasses import dataclass, field

from app.retrieval.vector import COMPANY_ALIASES, parse_filters

ALL_COMPANIES = list(COMPANY_ALIASES)
YEARS = [2025, 2026]

# Checked in order; the first metric that matches wins.
METRIC_KEYWORDS: dict[str, list[str]] = {
    "attrition": [r"\battrition\b", r"\bturnover rate\b", r"\bemployee turnover\b"],
    "operating_margin": [
        r"\boperating (profit )?margin\b",
        r"\bebit margin\b",
        r"\boperating profit ratio\b",
    ],
    "net_profit": [
        r"\bnet profit\b",
        r"\bprofit after tax\b",
        r"\bpat\b",
        r"\bnet income\b",
        r"\bprofit for the year\b",
        r"\bprofit\b(?! and loss)(?!.*\bratio\b)",  # not "statement of profit and loss"
    ],
    "revenue": [r"\brevenues?\b", r"\bsales\b", r"\bturnover\b(?! rate)"],
    "headcount": [
        r"\bheadcount\b",
        r"\bhow many (permanent )?employees\b",
        r"\bnumber of (permanent )?employees\b",
        r"\bpermanent employees\b",
        r"\bworkforce\b",
    ],
}
ADVICE = re.compile(
    r"\b(should i|buy|sell|invest(ment)? advice|share price|stock price|target price|"
    r"price target|undervalued|overvalued|good investment)\b",
    re.I,
)
WHY = re.compile(r"\b(why|reasons?|what drove|drivers?|explain|because|due to)\b", re.I)
CHANGE = re.compile(
    r"\b(change|changed|grow|grew|growth|increase|increased|decrease|decreased|decline|"
    r"declined|fall|fell|rise|rose|year[- ]over[- ]year|yoy|trend|from fy)\b",
    re.I,
)
ALL_SCOPE = re.compile(
    r"\b(which compan(y|ies)|all (five |the )?compan|across compan|highest|lowest|rank|"
    r"largest|smallest|most|least|best|worst)\b",
    re.I,
)


@dataclass
class Plan:
    route: str
    companies: list[str] = field(default_factory=list)
    years: list[int] = field(default_factory=list)
    metric: str | None = None
    change: bool = False  # compare the same company across years
    rank: bool = False  # rank companies
    reason: str = ""


def find_metric(question: str) -> str | None:
    q = question.lower()
    for metric, patterns in METRIC_KEYWORDS.items():
        if any(re.search(p, q) for p in patterns):
            return metric
    return None


def plan(question: str) -> Plan:
    companies, years = parse_filters(question)
    metric = find_metric(question)
    wants_all = bool(ALL_SCOPE.search(question))

    if ADVICE.search(question):
        return Plan("refuse", reason="investment advice or share prices are out of scope")

    if metric and not companies and not wants_all:
        # e.g. "Accenture's revenue": a metric for a company outside the five covered.
        return Plan("refuse", metric=metric, reason="the question names no covered company")

    if metric:
        change = bool(CHANGE.search(question)) or len(years) > 1
        companies = companies or ALL_COMPANIES
        years = YEARS if change else (years or [YEARS[-1]])
        return Plan(
            "metrics+text" if WHY.search(question) else "metrics",
            companies=companies,
            years=years,
            metric=metric,
            change=change,
            rank=wants_all or len(companies) > 1,
        )

    if len(companies) > 1:
        return Plan("compare_text", companies=companies, years=years)
    return Plan("text", companies=companies, years=years)
