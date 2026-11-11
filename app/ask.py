"""Ask one question from the command line.

Usage:
    python -m app.ask "What was TCS's consolidated revenue in FY2025?"
    python -m app.ask --show-excerpts "Why did Infosys's attrition fall in FY2026?"
    python -m app.ask --retrieval vector --no-agent "..."   # M2 baseline
"""

import argparse
import sys

from sqlalchemy.orm import Session

from app.agent.graph import build_agent
from app.agent.router import plan
from app.config import get_settings
from app.db.models import get_engine
from app.llm import LLM
from app.rag import COMPANY_NAMES, answer
from app.retrieval.factory import MODES, make_retriever
from ingest.index import load_embedder


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("question")
    ap.add_argument("--show-excerpts", action="store_true", help="print the retrieved chunks")
    ap.add_argument("--retrieval", choices=sorted(MODES), default="rerank")
    ap.add_argument("--no-agent", action="store_true", help="plain RAG, no router or tools")
    args = ap.parse_args()

    s = get_settings()
    embed = load_embedder(s.embedding_model)
    with Session(get_engine()) as session:
        retrieve = make_retriever(args.retrieval, session, embed)
        if args.no_agent:
            a = answer(args.question, retrieve=retrieve, llm=LLM(), k=s.retrieval_k)
        else:
            print(f"route: {plan(args.question).route}")
            a = build_agent(session, retrieve, LLM(), s.retrieval_k)(args.question)

    print(f"\n{a.text}\n")
    for c in a.citations:
        print(f"  {c}")
    if a.completion:
        cached = " (cached)" if a.completion.cached else ""
        print(
            f"\n{a.completion.model}: {a.completion.input_tokens} in / "
            f"{a.completion.output_tokens} out tokens, {a.completion.latency_s}s{cached}"
        )
    if args.show_excerpts:
        for i, h in enumerate(a.hits, 1):
            name = COMPANY_NAMES.get(h.company, h.company)
            print(f"\n--- [{i}] {name} FY{h.fiscal_year} p.{h.page} (distance {h.distance:.3f})")
            print(h.text[:600])
    print("\nAnswers come only from the companies' annual reports. Not investment advice.")


if __name__ == "__main__":
    main()
