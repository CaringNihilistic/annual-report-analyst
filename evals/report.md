# Eval report: baseline (vector only)

Model `openai/gpt-oss-20b`, k=5, embeddings `sentence-transformers/all-MiniLM-L6-v2`, 15 questions (8 number, 4 narrative, 3 refusal), 0 fresh LLM calls.

| Metric | Value |
|---|---|
| Numeric exact match (within 0.5%) | 25% (2/8) |
| Citation accuracy (numeric answers) | 100% (3/3) |
| Retrieval hit rate, top-k (number + narrative) | 42% (5/12) |
| Narrative answered (not refused) | 25% (1/4) |
| Narrative keyword coverage (proxy, not faithfulness) | 20% |
| Faithfulness (narrative) | not measured yet (M5: RAGAS + judge) |
| Refusal rate (should-refuse questions) | 100% (3/3) |
| p50 / p95 latency | 0.63s / 4.50s |
| Cost per query (est.) | $0.00007 |
| Tokens (in / out, all questions) | 11301 / 577 |

Cost uses Groq list prices in `PRICES` (an assumption; check the Groq console).

## Per question

| id | type | result | answer | citations | retrieved (top-k) |
|---|---|---|---|---|---|
| n01 | number | wrong, retrieval miss | Not found in the reports. |  | tcs FY2025 p.22; tcs FY2025 p.81; tcs FY2025 p.58; tcs FY2025 p.234; tcs FY2025 p.240 |
| n02 | number | wrong, retrieval miss | Not found in the reports. |  | infosys FY2025 p.8; infosys FY2025 p.317; infosys FY2025 p.242; infosys FY2025 p.238; infosys FY2025 p.346 |
| n03 | number | wrong, citation ok, retrieval hit | Wipro’s consolidated net profit for FY2025 was H131.4 billion. [1] | [1] Wipro FY2025, p.16 | wipro FY2025 p.16; wipro FY2025 p.100; wipro FY2025 p.84; wipro FY2025 p.374; wipro FY2025 p.376 |
| n04 | number | correct, citation ok, retrieval hit | HCLTech’s operating profit ratio (EBIT margin) for FY2025 was 18.3%[2] | [2] HCLTech FY2025, p.79 | hcltech FY2025 p.91; hcltech FY2025 p.79; hcltech FY2025 p.123; hcltech FY2025 p.120; hcltech FY2025 p.11 |
| n05 | number | wrong, retrieval hit | Not found in the reports. |  | infosys FY2026 p.145; infosys FY2026 p.33; infosys FY2026 p.13; infosys FY2026 p.357; infosys FY2026 p.144 |
| n06 | number | wrong, retrieval miss | Not found in the reports. |  | tcs FY2026 p.5; tcs FY2026 p.25; tcs FY2026 p.36; tcs FY2026 p.109; tcs FY2026 p.109 |
| n07 | number | wrong, retrieval miss | Not found in the reports. |  | techmahindra FY2026 p.319; techmahindra FY2026 p.280; techmahindra FY2026 p.315; techmahindra FY2026 p.543; techmahindra FY2026 p.440 |
| n08 | number | correct, citation ok, retrieval hit | HCLTech’s consolidated profit (net income) for FY2026 was ₹16,642 crores. [1] | [1] HCLTech FY2026, p.83 | hcltech FY2026 p.83; hcltech FY2026 p.371; hcltech FY2026 p.129; hcltech FY2026 p.7; hcltech FY2026 p.132 |
| w01 | narrative | answered, retrieval hit, keywords 80% | TCS’s operating margin expanded in FY 2026 because a combination of factors improved profitability: a stronger business mix, higher productivity and revenue realisation, and a favourable rebalancing of the pyramid, all of which were offset by investments in talent, capability building and ecosystem partnerships, yet still led to a 70‑basis‑point improvement to 25.0%[5]. Additionally, the positive impact of currency exchange rates contributed 7.0% to reported revenue, supporting margin growth, while the company reinvested most operating gains back into the business to strengthen capabilities and support growth[2]. | [2] TCS FY2026, p.59; [5] TCS FY2026, p.25 | tcs FY2026 p.25; tcs FY2026 p.59; tcs FY2026 p.5; tcs FY2026 p.55; tcs FY2026 p.25 |
| w02 | narrative | refused, retrieval miss, keywords 0% | Not found in the reports. |  | wipro FY2026 p.16; wipro FY2026 p.23; wipro FY2026 p.15; wipro FY2026 p.124; wipro FY2026 p.111 |
| w03 | narrative | refused, retrieval miss, keywords 0% | Not found in the reports. |  | wipro FY2026 p.16; wipro FY2026 p.23; wipro FY2026 p.15; wipro FY2026 p.111; wipro FY2026 p.44 |
| w04 | narrative | refused, retrieval miss, keywords 0% | Not found in the reports. |  | infosys FY2026 p.33; infosys FY2026 p.277; infosys FY2026 p.196; infosys FY2026 p.9; infosys FY2026 p.16 |
| r01 | refusal | refused (correct) | Not found in the reports. |  | wipro FY2025 p.4; wipro FY2026 p.33; wipro FY2025 p.374; wipro FY2025 p.376; wipro FY2026 p.403 |
| r02 | refusal | refused (correct) | Not found in the reports. |  | wipro FY2025 p.329; wipro FY2025 p.227; wipro FY2025 p.440; hcltech FY2025 p.107; hcltech FY2025 p.297 |
| r03 | refusal | refused (correct) | Not found in the reports. |  | infosys FY2026 p.120; infosys FY2025 p.110; infosys FY2026 p.357; infosys FY2025 p.231; infosys FY2026 p.245 |
