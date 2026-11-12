# Design: Annual Report Analyst (India)

How the system works, why it is built this way, what it costs, how it fails, and how it would scale. Every number here comes from a recorded run: the eval reports in `evals/reports/`, `deploy/aws.md`, or a measurement named in the text.

## 1. Problem

Answer questions about the FY2025 and FY2026 annual reports of five Indian IT companies (Infosys, TCS, Wipro, HCLTech, Tech Mahindra) with a citation to the exact page for every claim.

The corpus is 10 PDFs, **4,780 pages** and about **5,070 tables**. The hard parts:

- **Numbers live in tables**, and a page often holds several near-identical figures: standalone vs consolidated, current vs previous year, attributable vs total profit. Getting "the" revenue right means picking the right cell.
- **Questions span documents**: "compare attrition at three companies", "how did the margin change from FY25 to FY26".
- **Wrong is worse than silent.** A confident wrong number with a citation is the worst outcome, so the system must refuse when it can't support a claim.

Requirements that shaped the design: every claim cites company, year and page; numbers come from a structured table whenever possible; out-of-scope questions are refused (investment advice, uncovered companies); it is cheap enough to run on free tiers; everything is measured.

## 2. Architecture

```
 Offline (laptop, GPU optional)
   PDF ─► Docling parse ─► text chunks (page-tagged) ─► MiniLM embeddings ─┐
                     └──► tables ─► table rows as text ─────────────────────┼─► Postgres + pgvector
                     └──► normalise ─► financial_metrics (48 rows, source page) ┘

 Online (FastAPI)
   question ─► rule-based router ─┬─ refuse          (advice, uncovered company)
                                  ├─ metrics         SQL ─► computed change / ranking, no LLM
                                  ├─ metrics + text  numbers from SQL, reasons from search
                                  ├─ compare_text    one search per company
                                  └─ text            BM25 + vector ─► RRF ─► rerank ─► LLM
                              ─► combine parts, renumber citations ─► answer + [n] citations
```

One Postgres database holds the vectors (pgvector), the text for keyword search and the metrics table, so there is one service to run, back up and deploy.

**A question's path.** "How did Infosys's operating margin change from FY25 to FY26, and why?" The router finds the metric (`operating_margin`), the company and both years, plus a "why" part, so it routes to `metrics + text`. The metrics tool reads 21.1% and 20.3% with their source pages and computes the change (-0.8 points) in Python. The text tool searches Infosys FY2026 with hybrid retrieval, reranks, and asks the LLM for the reason, with citations. `combine` joins both parts and renumbers citations. The figures need no LLM; only the reason does.

## 3. Key decisions and trade-offs

### Numbers from a table, not from the LLM

The five headline metrics (revenue, net profit, operating margin, headcount, attrition) are extracted once into `financial_metrics`, each with its source page, and spot-checked against page images (20/20, `docs/spot-check-m1.md`). Metric questions are answered by SQL and formatted in Python.

- **Why:** in the M2 baseline the LLM, reading chunks, got 2 of 8 number questions right. Its misses were about *which* figure (attributable vs consolidated profit), not reading errors. With the table, the agent scored 8/8 on the seed set and 12/15 on the blind 50-question run, with p50 latency of 0.01 s and no LLM cost for those questions.
- **Cost of the choice:** coverage is limited to what was extracted. 18 of the 50 golden questions ask for other figures (EPS, PBT, other income, expenses), which go through text search, and that is where most remaining errors are. Tech Mahindra's operating margin isn't stated in any table, so it is left empty and never computed.

### Rule-based router instead of an LLM router

The router is regular expressions over metric names, companies and years.

- **Why:** deterministic, free, unit-tested, and a prompt-injection in the question can't talk it into another route. Every routing bug found in the blind run became a test.
- **Cost:** brittle to phrasing. The blind run exposed misses ("profit before tax" matched `net_profit`; "operating margins" plural was missed), fixed afterwards. An unseen phrasing can still route wrong. An LLM router would generalise better, but would add latency, cost and a new failure mode to every question.

### Hybrid retrieval with a cross-encoder reranker

BM25 and vector search each return 20 candidates, fused with reciprocal rank fusion, then `bge-reranker-base` reorders them and the top 5 go to the LLM. Tables are also indexed as text rows with labelled column groups.

- **Why:** keywords catch exact terms ("attrition", "EBIT"); vectors catch paraphrase. The reranker is what put the right table row first: numbers went from 4/8 (hybrid without rerank) to 7/8 on the seed set. A smaller reranker (`ms-marco-MiniLM-L-6-v2`) scored 3/8 and was dropped.
- **Cost:** the reranker dominates latency on CPU: about 13–15 s per pass on the 2-vCPU demo server, so text answers take 30–40 s there. An 8-bit quantized version was only 20% faster and changed the top 5 for all three test questions, so the evaluated model was kept.

### Citation enforcement after generation

The prompt asks for `[n]` citations and treats excerpts as data. After generation, sentences without a valid citation are dropped, and an answer with nothing left becomes "Not found in the reports." The evals then check that each cited number is printed on its cited page.

- **Why:** a prompt alone doesn't guarantee citations. Checking afterwards makes "no citation, no claim" a property of the code.
- **Cost:** a correct but uncited sentence is lost, which costs some answers on "why" questions.

### LLM: Groq first, Claude as fallback

`openai/gpt-oss-20b` on Groq for answers (cheap and fast), and `claude-haiku-5-5` when Groq's free daily limit is hit. Responses are cached on disk by (model, prompt), so re-running evals is free and repeatable. The faithfulness judge uses a larger model (`gpt-oss-120b`) and never falls back, so judge scores stay comparable.

### Deployment: one EC2 server, stopped when idle

The app and Postgres run as two containers on one t3.small in Sydney, paid from AWS Free plan credits (details in `deploy/aws.md`).

- **Why:** about $0.80 per running day, $1.92/month stopped, and no second always-billed service. RDS or App Runner would add standing costs this project can't carry. Secrets come from Parameter Store, admin access is Session Manager (no SSH), and the IAM role can read only its own parameters and one S3 object.
- **Cost:** no managed backups, failover or HTTPS, and the demo link only works while the server is started. A free always-on mirror on Hugging Face Spaces was built and tested, but Docker Spaces now need a paid plan, so it wasn't published.

## 4. Results

From `evals/reports/agent-blind.md`: the first run of the agent on the 50-question golden set, with no changes after seeing the questions.

| Metric | Result |
|---|---|
| Numbers (within 0.5%) | 12/15 (80%) |
| Year-over-year | 4/10 (40%) |
| Comparisons and rankings | 8/10 (80%) |
| Citation accuracy (cited number on cited page) | 28/32 (88%) |
| Faithfulness of "why" answers (LLM judge) | 91% |
| Refusals when the answer isn't in the reports | 5/5 |
| Latency p50 / p95 (laptop, GPU reranker) | 0.01 s / 16.2 s |
| Cost per question (Groq list prices) | ~$0.00006 |

After router fixes (optimistic, since the fixes were made after seeing the set): numbers 13/15, year-over-year 5/10, comparisons 9/10. The judge agreed with an independent grader on 13 of 15 answers (κ 0.42). That grader was Claude, not a human, so the faithfulness figures are indicative. The README has the full tables and the M2→M5 progression.

## 5. Cost

| Item | Cost |
|---|---|
| Question answered from the table | $0 (no LLM call) |
| Question answered from text | ~$0.00015 (Groq list price, ~70-token answers) |
| Average over the golden set | ~$0.00006 per question |
| Embeddings and reranking | $0 (local models) |
| Demo server running | ~$0.034/h (~$0.80/day) |
| Demo server stopped | ~$1.92/month (20 GB disk) |
| Always-on equivalent | ~$24.5/month |
| CI, image registry | $0 (GitHub Actions, ghcr.io) |

Ingestion ran once on a laptop. Its time and electricity weren't measured.

## 6. Failure modes

| Failure | What happens | Mitigation |
|---|---|---|
| Wrong figure picked from a busy page | Wrong number with a citation | Headline metrics come from the spot-checked table; evals check each cited number is on its page |
| Router misreads a phrasing | Wrong tool, e.g. a different metric | Unit tests per phrasing; the CI gate runs 13 golden questions on every PR |
| Retrieval misses the right page | "Not found" (seen on TCS other income, Wipro employee costs) | Refuses rather than guesses; hybrid search + rerank; known misses listed in the README |
| "Why" question gets only numbers, or a change question goes "Not found" (w03/w05) | Partial answer | Known regression from the M5 router fix, documented, not fixed yet |
| Broken PDF text layer (TCS FY2025) | Split numbers ("2, 4, 53") | Parsed with OCR instead; the rupee-glyph quirks are handled in `ingest/tables.py` |
| Groq rate limit (free daily cap) | Slow or failed text answers | Waits and retries short limits; falls back to Claude Haiku when a key is set (not on a public demo) |
| LLM or database down | No answer | API returns 503 "could not answer right now" without leaking details; `/health` reports DB status |
| Prompt injection in a PDF | Excerpt text tries to instruct the model | Excerpts are wrapped as data with a rule never to follow them; routing is rule-based; uncited sentences are dropped |
| Investment-advice questions | Should refuse | Router refuses known patterns; the LLM prompt refuses the rest (r05 is refused by the LLM) |
| Langfuse unreachable | Traces lost | Tracing errors are logged, never raised; answers are unaffected |

## 7. How it would scale

**10× documents (50 companies, ~50,000 pages).** About 230,000 chunks. Vector search is an exact scan today, fine at 23,000 rows; add an HNSW index in pgvector. BM25 is built in memory per company/year scope on each request (about 0.3 s on the demo server); move keyword search into Postgres full-text search, or cache the scopes. Ingestion becomes a batch job (GPU for Docling), and table extraction needs per-company rules or an LLM-assisted extractor with the same spot-check discipline. The router's company list becomes data, not code.

**10× metrics.** The metric layer is the biggest quality lever. Extending `financial_metrics` to EPS, PBT, other income and segment revenue would move the 18 text-only golden questions onto the deterministic path.

**More users.** Table-answered questions are cheap; the reranker is the bottleneck. Options in order of cost: cache answers by normalised question; run the API as several stateless containers behind a load balancer (the app keeps no session state); move reranking to a GPU instance or a hosted reranker; managed Postgres (RDS) with read replicas. The app already runs from one image, so ECS Fargate or App Runner would be the next step on AWS.

**Ops at scale.** Langfuse traces already record route, retrieved pages and LLM tokens per question. Add HTTPS (a domain + ALB or CloudFront), rate limiting per client (the public demo has none), and alerting on error rate and latency.

## 8. What I would do next

1. Fix the w03/w05 regression: let change-type "why" questions fall back to a single combined search when per-year search finds nothing.
2. Extend `financial_metrics` (EPS, PBT, other income, expenses), with spot-checks.
3. Replace the Claude-graded judge validation with human grades.
4. Run the CI gate's text questions with recorded LLM responses, so all 15 run on every PR.
5. Add rate limiting before sharing the public link widely.
