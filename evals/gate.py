"""Regression gate: 15 golden questions that pass today must keep passing.

    python -m evals.gate          # exit code 0 = pass, 1 = regression

Runs the production setup (agent + rerank retrieval) on a fixed subset of evals/golden.jsonl:
number, year-over-year, comparison and refusal questions, scored exactly like run_evals.
Narrative questions are left out: scoring them needs the LLM judge, which costs tokens.
Answers come from the LLM cache when nothing changed, so a re-run is free and quick.
Needs the database and data/processed (local only; CI runs unit tests and ruff).
"""

import json
import sys

from sqlalchemy.orm import Session

from app.agent.graph import build_agent
from app.config import get_settings
from app.db.models import get_engine
from app.llm import LLM
from app.retrieval.factory import make_retriever
from evals.run_evals import GOLDEN, score

GATE_IDS = [
    "n01", "n02", "n03", "n04", "n06", "n08", "n14",  # numbers
    "y07", "y08", "y10",  # year over year
    "c03", "c05", "c08",  # comparisons and rankings
    "r01", "r05",  # must refuse (investment advice)
]  # fmt: skip


def failures(rows: list[dict]) -> list[str]:
    """Why each row fails: a wrong answer, or a cited page that doesn't hold the number."""
    out = []
    for r in rows:
        if not r["correct"]:
            out.append(f"{r['id']}: wrong answer: {r['answer'][:120]}")
        elif r.get("citation_ok") is False:
            out.append(f"{r['id']}: cited page does not contain the stated number")
    return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    golden = {
        q["id"]: q
        for q in map(json.loads, GOLDEN.read_text(encoding="utf-8").splitlines())
        if q["id"] in GATE_IDS
    }
    from ingest.index import load_embedder  # heavy import, only when actually running

    s = get_settings()
    rows = []
    with Session(get_engine()) as session:
        retrieve = make_retriever("rerank", session, load_embedder(s.embedding_model))
        agent = build_agent(session, retrieve, LLM(), s.retrieval_k)
        for qid in GATE_IDS:
            rows.append(score(golden[qid], agent(golden[qid]["question"])))
            print(f"{qid}: {'ok' if not failures(rows[-1:]) else 'FAIL'}")

    failed = failures(rows)
    print(f"\ngate: {len(rows) - len(failed)}/{len(rows)} passed")
    for f in failed:
        print("  " + f)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
