"""Run the golden questions through the RAG pipeline and write evals/report.md.

Usage:
    python -m evals.run_evals                  # all questions
    python -m evals.run_evals --label baseline # name shown in the report

LLM responses are cached (.cache/llm), so re-running unchanged questions is free.
Scores (see README "Evaluation"):
  number     correct if the answer states the expected value within 0.5%
  citation   numeric answers: at least one cited page contains the expected value
  retrieval  the source page, or a page with the expected value, is in the top-k
  refusal    'should refuse' questions answered with a refusal
  narrative  faithfulness is not scored until M5 (RAGAS + judge); keyword coverage is
             reported only as a rough proxy
"""

import argparse
import json
import sys
import time
from functools import lru_cache

from sqlalchemy.orm import Session

from app.config import ROOT, get_settings
from app.db.models import get_engine
from app.llm import LLM
from app.rag import answer
from evals.metrics import (
    citation_supports,
    contains_number,
    keyword_coverage,
    matches_number,
    percentile,
)
from ingest.index import load_embedder

GOLDEN = ROOT / "evals" / "golden.jsonl"
REPORT = ROOT / "evals" / "report.md"
# USD per 1M tokens (input, output). Groq list prices as last known; check console.groq.com.
PRICES = {"openai/gpt-oss-20b": (0.075, 0.30), "llama-3.1-8b-instant": (0.05, 0.08)}


@lru_cache
def page_text(company: str, fiscal_year: int, page: int) -> str:
    """Everything known to be printed on a page: parsed chunks, table cells and the PDF text."""
    stem = f"{company}_FY{fiscal_year}"
    s = get_settings()
    doc = json.loads((s.processed_dir / f"{stem}.json").read_text(encoding="utf-8"))
    parts = [c["text"] for c in doc["chunks"] if c["page"] == page]
    for t in doc["tables"]:
        if t["page"] == page:
            parts += [" ".join(row) for row in t["rows"]]
    try:
        import pypdfium2 as pdfium

        parts.append(
            pdfium.PdfDocument(str(s.raw_dir / f"{stem}.pdf"))[page - 1]
            .get_textpage()
            .get_text_range()
        )
    except Exception:  # noqa: BLE001 - the PDF text layer is a bonus, not required
        pass
    return "\n".join(parts)


def score(q: dict, a) -> dict:
    row = {
        "id": q["id"],
        "type": q["type"],
        "refused": a.refused,
        "answer": a.text,
        "citations": [str(c) for c in a.citations],
        "retrieved": [f"{h.company} FY{h.fiscal_year} p.{h.page}" for h in a.hits],
    }
    same_doc = [h for h in a.hits if (h.company, h.fiscal_year) == (q["company"], q["fiscal_year"])]
    if q["type"] == "number":
        row["correct"] = not a.refused and matches_number(a.text, q["expected"])
        row["retrieval_hit"] = any(
            h.page == q["source_page"] or contains_number(h.text, q["expected"]) for h in same_doc
        )
        # "Does the cited page contain the claim?" - the numbers the answer states,
        # whether or not they are the expected value (that is what `correct` scores).
        row["citation_ok"] = (
            None
            if a.refused
            else citation_supports(
                a.text, [page_text(c.company, c.fiscal_year, c.page) for c in a.citations]
            )
        )
    elif q["type"] == "narrative":
        row["answered"] = not a.refused
        row["retrieval_hit"] = any(h.page == q["source_page"] for h in same_doc)
        row["keyword_coverage"] = keyword_coverage(a.text, q["key_points"]) if not a.refused else 0
    else:
        row["correct"] = a.refused
    return row


def pct(xs: list) -> str:
    xs = [x for x in xs if x is not None]
    return f"{100 * sum(xs) / len(xs):.0f}% ({sum(xs)}/{len(xs)})" if xs else "n/a"


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--label", default="baseline (vector only)")
    args = ap.parse_args()

    s = get_settings()
    questions = [
        json.loads(line) for line in GOLDEN.read_text(encoding="utf-8").splitlines() if line
    ]
    embed, llm = load_embedder(s.embedding_model), LLM()
    rows, latencies, in_tok, out_tok, fresh = [], [], 0, 0, 0
    with Session(get_engine()) as session:
        for q in questions:
            t0 = time.perf_counter()
            a = answer(q["question"], session=session, embed=embed, llm=llm, k=s.retrieval_k)
            wall_s = time.perf_counter() - t0
            c = a.completion
            if c:
                in_tok, out_tok = in_tok + c.input_tokens, out_tok + c.output_tokens
                fresh += not c.cached
                # Latency of a fresh run: wall time, plus the original LLM latency when the
                # call came from the cache (wall time then covers retrieval only).
                latencies.append(wall_s + (c.latency_s if c.cached else 0))
            rows.append(score(q, a))
            print(f"{q['id']}: {'refused' if a.refused else a.text[:100]}")

    by = lambda t: [r for r in rows if r["type"] == t]  # noqa: E731
    num, nar, ref = by("number"), by("narrative"), by("refusal")
    price = PRICES.get(llm.model)
    n = len(rows)
    cost = (
        f"${(in_tok * price[0] + out_tok * price[1]) / 1e6 / n:.5f}"
        if price
        else "unknown model price"
    )
    summary = [
        ("Numeric exact match (within 0.5%)", pct([r["correct"] for r in num])),
        ("Citation accuracy (numeric answers)", pct([r["citation_ok"] for r in num])),
        (
            "Retrieval hit rate, top-k (number + narrative)",
            pct([r["retrieval_hit"] for r in num + nar]),
        ),
        ("Narrative answered (not refused)", pct([r["answered"] for r in nar])),
        (
            "Narrative keyword coverage (proxy, not faithfulness)",
            f"{100 * sum(r['keyword_coverage'] for r in nar) / max(1, len(nar)):.0f}%",
        ),
        ("Faithfulness (narrative)", "not measured yet (M5: RAGAS + judge)"),
        ("Refusal rate (should-refuse questions)", pct([r["correct"] for r in ref])),
        (
            "p50 / p95 latency",
            f"{percentile(latencies, 50):.2f}s / {percentile(latencies, 95):.2f}s",
        ),
        ("Cost per query (est.)", cost),
        ("Tokens (in / out, all questions)", f"{in_tok} / {out_tok}"),
    ]
    lines = [
        f"# Eval report: {args.label}",
        "",
        f"Model `{llm.model}`, k={s.retrieval_k}, embeddings `{s.embedding_model}`, "
        f"{n} questions ({len(num)} number, {len(nar)} narrative, {len(ref)} refusal), "
        f"{fresh} fresh LLM calls.",
        "",
        "| Metric | Value |",
        "|---|---|",
        *[f"| {k} | {v} |" for k, v in summary],
        "",
        "Cost uses Groq list prices in `PRICES` (an assumption; check the Groq console).",
        "",
        "## Per question",
        "",
        "| id | type | result | answer | citations | retrieved (top-k) |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        if r["type"] == "number":
            res = (
                ("correct" if r["correct"] else "wrong")
                + (
                    ""
                    if r["citation_ok"] is None
                    else f", citation {'ok' if r['citation_ok'] else 'bad'}"
                )
                + f", retrieval {'hit' if r['retrieval_hit'] else 'miss'}"
            )
        elif r["type"] == "narrative":
            res = (
                f"{'answered' if r['answered'] else 'refused'}, "
                f"retrieval {'hit' if r['retrieval_hit'] else 'miss'}, "
                f"keywords {100 * r['keyword_coverage']:.0f}%"
            )
        else:
            res = "refused (correct)" if r["correct"] else "answered (should refuse)"
        ans = r["answer"].replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| {r['id']} | {r['type']} | {res} | {ans} | {'; '.join(r['citations'])} | "
            f"{'; '.join(r['retrieved'])} |"
        )
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n" + "\n".join(f"{k}: {v}" for k, v in summary))
    print(f"\nwrote {REPORT}")


if __name__ == "__main__":
    main()
