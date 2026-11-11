"""The agent: a LangGraph state machine that routes each question to the right tool(s).

    START -> route -> refuse ---------------------------------> END
                   -> metrics ---------------------> combine -> END
                   -> metrics -> text (reasons) ---> combine -> END
                   -> compare_text (one search per company) -> combine -> END
                   -> text ------------------------> combine -> END

Every part is an Answer with its own [n] citations; `combine` renumbers them into one answer.
A metric with no table value (e.g. Tech Mahindra's operating margin) falls back to text search.
"""

import re
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from app.agent.router import Plan, plan
from app.agent.tools import compare, query_metrics, search_text
from app.rag import COMPANY_NAMES, REFUSAL, Answer, Citation

ADVICE_REFUSAL = (
    "This assistant only answers from the companies' annual reports and does not give "
    "investment advice or share price views."
)
SCOPE_REFUSAL = (
    "Not found in the reports. This assistant covers Infosys, TCS, Wipro, HCLTech and "
    "Tech Mahindra (FY2025 and FY2026 annual reports)."
)


class State(TypedDict, total=False):
    question: str
    plan: Plan
    parts: list[Answer]
    answer: Answer


def combine_parts(question: str, parts: list[Answer]) -> Answer:
    """Join answers, renumbering each part's [n] citations so they stay unique."""
    kept = [p for p in parts if not p.refused]
    if not kept:
        return Answer(question, REFUSAL, [], True)
    texts, citations, hits = [], [], []
    for p in kept:
        offset = len(citations)
        mapping = {c.n: c.n + offset for c in p.citations}

        def renumber(m: re.Match, mapping=mapping) -> str:
            nums = [mapping.get(int(n), int(n)) for n in m[1].split(",")]
            return "[" + ", ".join(str(n) for n in nums) + "]"

        texts.append(re.sub(r"\[(\d+(?:\s*,\s*\d+)*)\]", renumber, p.text))
        citations += [Citation(mapping[c.n], c.company, c.fiscal_year, c.page) for c in p.citations]
        hits += p.hits
    return Answer(question, " ".join(texts), citations, False, hits, kept[-1].completion)


def build_agent(session: Session, retrieve, llm, k: int = 5):
    def route(state: State) -> State:
        return {"plan": plan(state["question"]), "parts": []}

    def refuse(state: State) -> State:
        p = state["plan"]
        text = ADVICE_REFUSAL if "advice" in p.reason else SCOPE_REFUSAL
        return {"answer": Answer(state["question"], text, [], True)}

    def metrics(state: State) -> State:
        p, q = state["plan"], state["question"]
        values = query_metrics(session, p.metric, p.companies, p.years)
        part = compare(q, values, p.metric, p.companies, p.years, p.change, p.rank)
        if part.refused and p.route == "metrics":
            # Nothing in the table (e.g. TechM margin): try the text instead. For
            # metrics+text the text node runs next anyway.
            part = search_text(q, retrieve, llm, k)
        return {"parts": state["parts"] + [part]}

    def text(state: State) -> State:
        return {"parts": state["parts"] + [search_text(state["question"], retrieve, llm, k)]}

    def compare_text(state: State) -> State:
        p, q, parts = state["plan"], state["question"], list(state["parts"])
        for c in p.companies:
            sub = f"{q} (answer for {COMPANY_NAMES.get(c, c)} only)"
            parts.append(search_text(sub, retrieve, llm, k, companies=[c], years=p.years))
        return {"parts": parts}

    def combine(state: State) -> State:
        return {"answer": combine_parts(state["question"], state["parts"])}

    g = StateGraph(State)
    for name, fn in [
        ("route", route),
        ("refuse", refuse),
        ("metrics", metrics),
        ("text", text),
        ("compare_text", compare_text),
        ("combine", combine),
    ]:
        g.add_node(name, fn)
    g.add_edge(START, "route")
    g.add_conditional_edges(
        "route",
        lambda s: {"metrics+text": "metrics"}.get(s["plan"].route, s["plan"].route),
        ["refuse", "metrics", "text", "compare_text"],
    )
    g.add_conditional_edges(
        "metrics",
        lambda s: "text" if s["plan"].route == "metrics+text" else "combine",
        ["text", "combine"],
    )
    g.add_edge("text", "combine")
    g.add_edge("compare_text", "combine")
    g.add_edge("refuse", END)
    g.add_edge("combine", END)
    graph = g.compile()

    def ask(question: str) -> Answer:
        return graph.invoke({"question": question})["answer"]

    ask.graph = graph
    return ask
