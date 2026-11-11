import pytest

import app.agent.graph as graph_mod
from app.agent.graph import build_agent, combine_parts
from app.agent.router import ALL_COMPANIES, plan
from app.agent.tools import MetricValue, compare, fmt, indian
from app.rag import Answer, Citation


@pytest.mark.parametrize(
    "question, route, metric",
    [
        ("What was TCS's consolidated revenue from operations in FY2025?", "metrics", "revenue"),
        ("What was HCLTech's operating profit ratio in FY2025?", "metrics", "operating_margin"),
        ("How many permanent employees did TCS have at the end of FY2026?", "metrics", "headcount"),
        ("What was the turnover rate for permanent employees at Infosys?", "metrics", "attrition"),
        ("Why did TCS's operating margin expand in FY2026?", "metrics+text", "operating_margin"),
        ("What drove Wipro's revenue growth in fiscal year 2026?", "metrics+text", "revenue"),
        ("What exceptional item did Infosys report in FY2026?", "text", None),
        ("How do TCS and Wipro describe their AI strategy?", "compare_text", None),
        ("Should I buy Wipro shares now?", "refuse", None),
        ("What will Infosys's share price be at the end of 2027?", "refuse", None),
        ("What was Accenture's revenue in FY2025?", "refuse", "revenue"),
    ],
)
def test_router(question, route, metric):
    p = plan(question)
    assert p.route == route
    assert p.metric == metric


def test_router_scope_years_and_ranking():
    p = plan("Which company had the highest operating margin in FY2026?")
    assert (p.companies, p.years, p.rank, p.change) == (ALL_COMPANIES, [2026], True, False)
    p = plan("How did Infosys's consolidated revenue change from FY2025 to FY2026?")
    assert (p.companies, p.years, p.change) == (["infosys"], [2025, 2026], True)
    assert plan("TCS revenue").years == [2026]  # no year -> latest


def test_indian_grouping_and_formatting():
    assert indian(255324) == "2,55,324"
    assert indian(584519) == "5,84,519"
    assert indian(999) == "999"
    assert indian(12.5) == "12.5"
    v = MetricValue("wipro", 2025, "net_profit", 132180, "million", "INR", 100)
    assert fmt(v) == "₹132,180 million (≈ ₹13,218 crore)"
    assert fmt(MetricValue("tcs", 2026, "operating_margin", 25.0, "percent", None, 71)) == "25%"


def mv(company, year, value, metric="revenue", unit="crore", currency="INR", page=1):
    return MetricValue(company, year, metric, value, unit, currency, page)


def test_single_value_with_citation():
    a = compare("q", [mv("tcs", 2025, 255324, page=69)], "revenue", ["tcs"], [2025], False, False)
    assert a.text == "TCS's consolidated revenue from operations in FY2025 was ₹2,55,324 crore [1]."
    assert [(c.company, c.fiscal_year, c.page) for c in a.citations] == [("tcs", 2025, 69)]


def test_year_over_year_change():
    vals = [mv("infosys", 2025, 162990, page=30), mv("infosys", 2026, 178650, page=34)]
    a = compare("q", vals, "revenue", ["infosys"], [2025, 2026], True, False)
    assert "from ₹1,62,990 crore in FY2025 [1] to ₹1,78,650 crore in FY2026 [2]" in a.text
    assert "+9.6%" in a.text


def test_percent_change_is_in_points():
    vals = [
        mv("tcs", 2025, 24.3, "operating_margin", "percent", None),
        mv("tcs", 2026, 25.0, "operating_margin", "percent", None, page=2),
    ]
    a = compare("q", vals, "operating_margin", ["tcs"], [2025, 2026], True, False)
    assert "+0.7 percentage points" in a.text


def test_ranking_converts_million_to_crore():
    vals = [
        mv("tcs", 2025, 255324),
        mv("wipro", 2025, 890884, unit="million", page=2),  # ≈ 89,088 crore
        mv("hcltech", 2025, 117055, page=3),
    ]
    a = compare("q", vals, "revenue", ["tcs", "wipro", "hcltech"], [2025], False, True)
    assert a.text.index("TCS") < a.text.index("HCLTech") < a.text.index("Wipro")
    assert "highest: TCS" in a.text and "lowest: Wipro" in a.text


def test_missing_value_is_stated_and_all_missing_refuses():
    vals = [mv("tcs", 2026, 25.0, "operating_margin", "percent", None)]
    a = compare("q", vals, "operating_margin", ["tcs", "techmahindra"], [2026], False, True)
    assert "No operating margin figure is stated in a table for: Tech Mahindra." in a.text
    assert compare("q", [], "operating_margin", ["techmahindra"], [2026], False, False).refused


def test_combine_renumbers_citations():
    p1 = Answer("q", "A [1].", [Citation(1, "tcs", 2025, 69)], False)
    p2 = Answer("q", "B [1][2].", [Citation(1, "tcs", 2025, 5), Citation(2, "tcs", 2025, 6)], False)
    a = combine_parts("q", [p1, p2])
    assert a.text == "A [1]. B [2][3]."
    assert [c.n for c in a.citations] == [1, 2, 3]
    assert combine_parts("q", [Answer("q", "x", [], True)]).refused


class FakeRow:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class FakeSession:
    """Returns metric rows like session.scalars(select(FinancialMetric)...)."""

    rows = [
        FakeRow(
            company="tcs",
            fiscal_year=2026,
            metric="operating_margin",
            value=25.0,
            unit="percent",
            currency=None,
            source_page=71,
        ),
    ]

    def scalars(self, stmt):
        return iter(self.rows)


def test_agent_end_to_end_without_network(monkeypatch):
    text_calls = []

    def fake_search_text(question, retrieve, llm, k=5, companies=None, years=None):
        text_calls.append((question, companies))
        return Answer(
            question, "Pyramid restructuring helped [1].", [Citation(1, "tcs", 2026, 59)], False
        )

    monkeypatch.setattr(graph_mod, "search_text", fake_search_text)
    ask = build_agent(FakeSession(), retrieve=None, llm=None)

    a = ask("Why did TCS's operating margin expand in FY2026?")  # metrics + text
    assert a.text == (
        "TCS's operating margin in FY2026 was 25% [1]. Pyramid restructuring helped [2]."
    )
    assert [c.page for c in a.citations] == [71, 59]

    assert ask("Should I buy TCS shares?").refused
    assert ask("What was Accenture's revenue in FY2025?").refused
    assert not text_calls[1:]  # refusals never search

    ask("How do TCS and Wipro describe their AI strategy?")
    assert [c for _, c in text_calls[1:]] == [["tcs"], ["wipro"]]  # one search per company


def test_profit_and_loss_is_not_a_profit_question():
    q = "Tech Mahindra's consolidated revenue recognised in the statement of profit and loss?"
    assert plan(q).metric == "revenue"


@pytest.mark.parametrize(
    "question, route",
    [
        ("What was Infosys's consolidated profit before tax for fiscal 2025?", "text"),
        ("Why did Wipro's cost of revenues increase in fiscal year 2026?", "text"),
        ("How did TCS's EPS change from FY2025 to FY2026?", "text"),
        ("What does Tech Mahindra's FY2026 turnover rate for permanent employees cover?", "text"),
        ("Compare the operating margins of Infosys, Wipro and HCLTech in FY2025.", "metrics"),
    ],
)
def test_router_line_items_definitions_and_plurals(question, route):
    assert plan(question).route == route


def test_text_change_question_searches_each_year():
    from app.agent.tools import search_text_change
    from app.retrieval.vector import Hit

    calls = []

    def retrieve(q, k, companies=None, years=None):
        calls.append(years)
        y = years[0]
        return [Hit(y, "tcs", y, 1, None, f"EPS {y}", 0.0)]

    class LLMStub:
        def complete(self, system, user):
            from app.llm import Completion

            assert "EPS 2025" in user and "EPS 2026" in user and "percentage change" in user
            return Completion("EPS rose from 134.19 [1] to 145.99 [2], +8.8%.", "m", 1, 1, 0.1)

    p = plan("How did TCS's EPS change from FY2025 to FY2026?")
    a = search_text_change("q", retrieve, LLMStub(), 5, p.companies, p.years)
    assert calls == [[2025], [2026]]
    assert [c.fiscal_year for c in a.citations] == [2025, 2026]
