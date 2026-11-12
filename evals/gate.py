"""Regression gate: golden questions that pass today must keep passing.

    python -m evals.gate                  # local: 15 questions, full production setup
    python -m evals.gate --build-fixture  # local: refresh evals/fixtures/ci_gate.json
    python -m evals.gate --ci             # CI: 13 questions against the fixture, no keys

Local mode runs the production setup (agent + rerank retrieval) on a fixed subset of
evals/golden.jsonl: number, year-over-year, comparison and refusal questions, scored exactly
like run_evals. Narrative questions are left out: scoring them needs the LLM judge, which
costs tokens. Answers come from the LLM cache when nothing changed, so a re-run is free.

CI mode needs only an empty Postgres. It loads financial_metrics from the fixture and runs the
13 questions that are answered from that table with no LLM and no text search. Both are
stubbed to raise, so a router change that sends one of them down the LLM path also fails.
Citations are checked against the numbers printed on each cited page, stored in the fixture
as bare number lists (no report text is committed).
"""

import argparse
import json
import re
import sys
from pathlib import Path

from sqlalchemy.orm import Session

from app.agent.graph import build_agent
from app.config import get_settings
from app.db.models import FinancialMetric, get_engine, init_db
from evals import run_evals
from evals.run_evals import GOLDEN, score

GATE_IDS = [
    "n01", "n02", "n03", "n04", "n06", "n08", "n14",  # numbers
    "y07", "y08", "y10",  # year over year
    "c03", "c05", "c08",  # comparisons and rankings
    "r01", "r05",  # must refuse (investment advice)
]  # fmt: skip
# n14 (EPS) is not in financial_metrics and r05 is refused by the LLM, so both need a key.
CI_IDS = [q for q in GATE_IDS if q not in ("n14", "r05")]
FIXTURE = Path(__file__).parent / "fixtures" / "ci_gate.json"
METRIC_FIELDS = ("company", "fiscal_year", "metric", "value", "unit", "currency", "source_page")


def failures(rows: list[dict]) -> list[str]:
    """Why each row fails: a wrong answer, or a cited page that doesn't hold the number."""
    out = []
    for r in rows:
        if not r["correct"]:
            out.append(f"{r['id']}: wrong answer: {r['answer'][:120]}")
        elif r.get("citation_ok") is False:
            out.append(f"{r['id']}: cited page does not contain the stated number")
    return out


def page_numbers(text: str) -> list[str]:
    """The numbers printed on a page, in both digit groupings: enough for the citation check."""
    joined = re.sub(r"(?<=\d),\s?(?=\d)", "", text)
    found = set(re.findall(r"\d+(?:\.\d+)?", joined)) | set(re.findall(r"\d+(?:\.\d+)?", text))
    return sorted(found)


class _Forbidden:
    """Stand-in for the LLM and the retriever in CI: any use is a regression."""

    def __init__(self, what: str):
        self.what = what

    def __call__(self, *args, **kwargs):
        raise RuntimeError(f"{self.what} was used; this question should be answered from the table")

    def __getattr__(self, name):
        return self


def load_golden(ids: list[str]) -> dict[str, dict]:
    lines = GOLDEN.read_text(encoding="utf-8").splitlines()
    return {q["id"]: q for q in map(json.loads, lines) if q["id"] in ids}


def run(ids: list[str], agent) -> list[dict]:
    golden, rows = load_golden(ids), []
    for qid in ids:
        try:
            rows.append(score(golden[qid], agent(golden[qid]["question"])))
        except RuntimeError as e:
            rows.append({"id": qid, "correct": False, "answer": str(e)})
        print(f"{qid}: {'ok' if not failures(rows[-1:]) else 'FAIL'}")
    return rows


def local_agent(session: Session):
    from app.llm import LLM
    from app.retrieval.factory import make_retriever
    from ingest.index import load_embedder  # heavy import, only when actually running

    s = get_settings()
    retrieve = make_retriever("rerank", session, load_embedder(s.embedding_model))
    return build_agent(session, retrieve, LLM(), s.retrieval_k)


def build_fixture() -> None:
    """Snapshot financial_metrics and the numbers on every page the CI answers cite."""
    with Session(get_engine()) as session:
        metrics = [
            {f: getattr(m, f) for f in METRIC_FIELDS}
            for m in session.query(FinancialMetric).order_by(
                FinancialMetric.company, FinancialMetric.fiscal_year, FinancialMetric.metric
            )
        ]
        agent = build_agent(session, _Forbidden("text search"), _Forbidden("the LLM"))
        golden, pages = load_golden(CI_IDS), {}
        for qid in CI_IDS:
            for c in agent(golden[qid]["question"]).citations:
                key = f"{c.company}|{c.fiscal_year}|{c.page}"
                pages[key] = page_numbers(run_evals.page_text(c.company, c.fiscal_year, c.page))
    FIXTURE.parent.mkdir(exist_ok=True)
    FIXTURE.write_text(
        json.dumps({"metrics": metrics, "page_numbers": dict(sorted(pages.items()))}, indent=1),
        encoding="utf-8",
    )
    print(f"wrote {FIXTURE}: {len(metrics)} metrics, {len(pages)} pages")


def ci_rows() -> list[dict]:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    engine = get_engine()
    init_db(engine)
    with Session(engine) as session:
        if session.query(FinancialMetric).count():
            sys.exit("--ci loads its own data and expects an empty database (see DATABASE_URL)")
        session.add_all(FinancialMetric(**m) for m in fixture["metrics"])
        session.commit()
        pages = fixture["page_numbers"]
        # The scorer looks pages up through this function; serve the stored numbers instead.
        run_evals.page_text = lambda co, fy, pg: " ".join(pages.get(f"{co}|{fy}|{pg}", []))
        agent = build_agent(session, _Forbidden("text search"), _Forbidden("the LLM"))
        return run(CI_IDS, agent)


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--ci", action="store_true", help="fixture-only run, no keys or PDFs")
    mode.add_argument("--build-fixture", action="store_true", help="refresh the CI fixture")
    args = p.parse_args(argv)

    if args.build_fixture:
        build_fixture()
        return 0
    if args.ci:
        rows = ci_rows()
    else:
        with Session(get_engine()) as session:
            rows = run(GATE_IDS, local_agent(session))

    failed = failures(rows)
    print(f"\ngate: {len(rows) - len(failed)}/{len(rows)} passed")
    for f in failed:
        print("  " + f)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
