# Eval report: hybrid (BM25 + vector, reciprocal rank fusion)

Model `openai/gpt-oss-20b`, k=5, embeddings `sentence-transformers/all-MiniLM-L6-v2`, 15 questions (8 number, 4 narrative, 3 refusal), 0 fresh LLM calls.

| Metric | Value |
|---|---|
| Numeric exact match (within 0.5%) | 50% (4/8) |
| Citation accuracy (numeric answers) | 86% (6/7) |
| Retrieval hit rate, top-k (number + narrative) | 75% (9/12) |
| Narrative answered (not refused) | 100% (4/4) |
| Narrative keyword coverage (proxy, not faithfulness) | 38% |
| Faithfulness (narrative) | not measured yet (M5: RAGAS + judge) |
| Refusal rate (should-refuse questions) | 100% (3/3) |
| p50 / p95 latency | 7.12s / 15.19s |
| Cost per query (est.) | $0.00011 |
| Tokens (in / out, all questions) | 18588 / 1060 |

Cost uses Groq list prices in `PRICES` (an assumption; check the Groq console).

## Per question

| id | type | result | answer | citations | retrieved (top-k) |
|---|---|---|---|---|---|
| n01 | number | correct, citation ok, retrieval hit | TCS’s consolidated revenue from operations for FY 2025 was ₹2,55,324 crore[1][2] | [1] TCS FY2025, p.70; [2] TCS FY2025, p.88 | tcs FY2025 p.70; tcs FY2025 p.88; tcs FY2025 p.180; tcs FY2025 p.58; tcs FY2025 p.184 |
| n02 | number | wrong, citation ok, retrieval hit | Infosys’s consolidated revenue from operations for fiscal 2025 was ₹136,592 crore. [3] | [3] Infosys FY2025, p.242 | infosys FY2025 p.30; infosys FY2025 p.8; infosys FY2025 p.242; infosys FY2025 p.242; infosys FY2025 p.321 |
| n03 | number | wrong, citation bad, retrieval hit | Wipro’s consolidated net profit for FY2025 was ₹131,354 million (₹131.354 billion) [5]. | [5] Wipro FY2025, p.273 | wipro FY2025 p.365; wipro FY2025 p.365; wipro FY2025 p.366; wipro FY2025 p.16; wipro FY2025 p.273 |
| n04 | number | correct, citation ok, retrieval hit | HCLTech’s operating profit ratio for FY2025 was 18.3 %[4] | [4] HCLTech FY2025, p.114 | hcltech FY2025 p.120; hcltech FY2025 p.91; hcltech FY2025 p.79; hcltech FY2025 p.114; hcltech FY2025 p.119 |
| n05 | number | correct, citation ok, retrieval hit | The turnover rate for permanent employees at Infosys in fiscal 2026 was 12.6 %[2] | [2] Infosys FY2026, p.145 | infosys FY2026 p.145; infosys FY2026 p.145; infosys FY2026 p.160; infosys FY2026 p.33; infosys FY2026 p.13 |
| n06 | number | wrong, retrieval miss | Not found in the reports. |  | tcs FY2026 p.119; tcs FY2026 p.109; tcs FY2026 p.109; tcs FY2026 p.131; tcs FY2026 p.5 |
| n07 | number | wrong, citation ok, retrieval miss | Tech Mahindra’s consolidated revenue recognised in the statement of profit and loss for FY2026 was ₹489,270 million. [5] | [5] Tech Mahindra FY2026, p.507 | techmahindra FY2026 p.555; techmahindra FY2026 p.436; techmahindra FY2026 p.576; techmahindra FY2026 p.319; techmahindra FY2026 p.507 |
| n08 | number | correct, citation ok, retrieval hit | HCLTech’s consolidated profit after tax for FY2026 was ₹16,642 crores[4]. | [4] HCLTech FY2026, p.448 | hcltech FY2026 p.129; hcltech FY2026 p.375; hcltech FY2026 p.83; hcltech FY2026 p.448; hcltech FY2026 p.7 |
| w01 | narrative | answered, retrieval hit, keywords 0% | These dynamics pushed the margin to 25.0 %, a 70‑basis‑point gain over FY 2025 [1][2] | [1] TCS FY2026, p.59; [2] TCS FY2026, p.25 | tcs FY2026 p.59; tcs FY2026 p.25; tcs FY2026 p.59; tcs FY2026 p.6; tcs FY2026 p.38 |
| w02 | narrative | answered, retrieval hit, keywords 0% | The growth was also impacted by a reduction in discretionary spending by clients due to macroeconomic challenges and geopolitical dynamics. [1] | [1] Wipro FY2026, p.38 | wipro FY2026 p.38; wipro FY2026 p.124; wipro FY2026 p.19; wipro FY2026 p.35; wipro FY2026 p.40 |
| w03 | narrative | answered, retrieval hit, keywords 100% | Wipro’s general and administrative expenses increased in FY2026 mainly because of the implementation of a new labor code in India (₹2,599 million included in employee compensation), an increase in lifetime expected credit loss provisions, and a one‑time insurance claim of ₹1,805 million received in FY2025, which partially offset reductions in staff recruitment and headcount costs. [1] | [1] Wipro FY2026, p.38 | wipro FY2026 p.38; wipro FY2026 p.184; wipro FY2026 p.40; wipro FY2026 p.280; wipro FY2026 p.44 |
| w04 | narrative | answered, retrieval miss, keywords 50% | The consolidated impact of this item was ₹1,289 crore[4]. | [4] Infosys FY2026, p.80 | infosys FY2026 p.360; infosys FY2026 p.359; infosys FY2026 p.33; infosys FY2026 p.80; infosys FY2026 p.196 |
| r01 | refusal | refused (correct) | Not found in the reports. |  | wipro FY2026 p.33; wipro FY2026 p.286; wipro FY2025 p.16; wipro FY2026 p.35; wipro FY2025 p.101 |
| r02 | refusal | refused (correct) | Not found in the reports. |  | techmahindra FY2025 p.411; hcltech FY2025 p.107; techmahindra FY2025 p.304; techmahindra FY2025 p.412; techmahindra FY2025 p.33 |
| r03 | refusal | refused (correct) | Not found in the reports. |  | infosys FY2025 p.110; infosys FY2026 p.243; infosys FY2026 p.120; infosys FY2026 p.373; infosys FY2026 p.357 |
