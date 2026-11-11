"""Validate the LLM judge against human grades.

    python -m evals.judge_validation build   # write docs/judge-validation.md (answers to grade)
    python -m evals.judge_validation score   # after grading: judge vs human agreement

The sheet shows each question, answer and the cited source text, but not the judge's verdict,
so grading isn't anchored on it. Verdicts are kept in evals/reports/judge-validation.jsonl.
"""

import json
import re
import sys

from app.config import ROOT

REPORTS = ROOT / "evals" / "reports"
SHEET = ROOT / "docs" / "judge-validation.md"
ITEMS = REPORTS / "judge-validation.jsonl"
N = 15  # upper bound; fewer if there are not enough distinct answers
SOURCE_PREVIEW = 1800


def load(name: str) -> list[dict]:
    path = REPORTS / f"{name}.judge.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def build() -> None:
    # Blind agent answers first, then distinct answers from plain RAG and the post-fix agent.
    items, seen = [], set()
    for name, system in [("agent-blind", "agent"), ("rerank", "rerank"), ("agent", "agent")]:
        for j in load(name):
            if j["answer"] not in seen:
                seen.add(j["answer"])
                items.append({**j, "system": system})
    items = items[:N]
    ITEMS.write_text("".join(json.dumps(i, ensure_ascii=False) + "\n" for i in items), "utf-8")

    out = [
        f"# Judge validation: grade {len(items)} answers",
        "",
        "For each answer, read the sources and decide: **is every factual claim in the answer "
        "supported by the sources?** Paraphrase is fine; a claim that is missing from the sources, "
        "or has a wrong number, year or direction, is not supported.",
        "",
        "Replace `?` after **Your verdict:** with `yes` (all claims supported) or `no`. Then run "
        "`python -m evals.judge_validation score`. The judge's own verdicts are hidden until then.",
        "",
    ]
    for i, it in enumerate(items, 1):
        out += [f"## {i}. {it['question']}", "", f"**Answer:** {it['answer']}", ""]
        for n, src in enumerate(it["sources"], 1):
            text = " ".join(src.split())
            more = " …" if len(text) > SOURCE_PREVIEW else ""
            out += [
                f"<details><summary>Source [{n}]</summary>",
                "",
                text[:SOURCE_PREVIEW] + more,
                "",
                "</details>",
                "",
            ]
        out += ["**Your verdict:** ?", ""]
    SHEET.write_text("\n".join(out), encoding="utf-8")
    print(f"wrote {SHEET} ({len(items)} answers) and {ITEMS}")


def parse_verdicts(sheet: str) -> list[str]:
    """One verdict per item: only lines that *start* with the marker (not the instructions)."""
    return [v.lower() for v in re.findall(r"^\*\*Your verdict:\*\*[ \t]*(\S+)", sheet, re.M)]


def score() -> None:
    items = [json.loads(line) for line in ITEMS.read_text(encoding="utf-8").splitlines() if line]
    human = parse_verdicts(SHEET.read_text("utf-8"))
    graded = [(it, h == "yes") for it, h in zip(items, human, strict=False) if h in ("yes", "no")]
    if not graded:
        print("No grades yet: fill in 'Your verdict:' in docs/judge-validation.md.")
        return
    agree = sum(it["faithful"] == h for it, h in graded)
    tp = sum(it["faithful"] and h for it, h in graded)
    tn = sum(not it["faithful"] and not h for it, h in graded)
    fp = sum(it["faithful"] and not h for it, h in graded)  # judge says faithful, human no
    fn = sum(not it["faithful"] and h for it, h in graded)
    n = len(graded)
    # Cohen's kappa: agreement beyond what two raters with these yes-rates would reach by chance.
    pe = ((tp + fp) * (tp + fn) + (tn + fn) * (tn + fp)) / (n * n)
    kappa = (agree / n - pe) / (1 - pe) if pe < 1 else 1.0
    print(f"graded {n}/{len(items)}: agreement {agree}/{n} = {100 * agree / n:.0f}%")
    print(f"Cohen's kappa {kappa:.2f}")
    print(f"both faithful {tp}, both unfaithful {tn}")
    print(f"judge faithful but human no {fp}, judge unfaithful but human yes {fn}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    {"build": build, "score": score}[sys.argv[1] if len(sys.argv) > 1 else "build"]()
