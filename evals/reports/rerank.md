# Eval report: rerank (BM25 + vector, fused, then cross-encoder rerank (default))

Model `openai/gpt-oss-20b`, k=5, embeddings `sentence-transformers/all-MiniLM-L6-v2`, 19 questions (8 number, 4 comparison, 4 narrative, 3 refusal), 0 fresh LLM calls.

| Metric | Value |
|---|---|
| Numeric exact match (within 0.5%) | 88% (7/8) |
| Comparison / year-over-year correct | 0% (0/4) |
| Citation accuracy (number + comparison) | 90% (9/10) |
| Retrieval hit rate, top-k (number + narrative) | 75% (9/12) |
| Narrative answered (not refused) | 100% (4/4) |
| Narrative keyword coverage (proxy, not faithfulness) | 57% |
| Faithfulness (narrative) | not measured yet (M5: RAGAS + judge) |
| Refusal rate (should-refuse questions) | 100% (3/3) |
| p50 / p95 latency | 4.08s / 15.20s |
| Cost per query (est.) | $0.00015 |
| Tokens (in / out, all questions) | 31477 / 1405 |

Cost uses Groq list prices in `PRICES` (an assumption; check the Groq console).

## Per question

| id | type | result | answer | citations | retrieved (top-k) |
|---|---|---|---|---|---|
| n01 | number | correct, citation ok, retrieval hit | TCS’s consolidated revenue from operations for FY 2025 was ₹2,55,324 crore. [1] | [1] TCS FY2025, p.70 | tcs FY2025 p.70; tcs FY2025 p.88; tcs FY2025 p.88; tcs FY2025 p.69; tcs FY2025 p.184 |
| n02 | number | correct, citation ok, retrieval hit | Infosys’s consolidated revenue from operations for fiscal 2025 was ₹1,62,990 crore in reported currency terms. [4] | [4] Infosys FY2025, p.73 | infosys FY2025 p.30; infosys FY2025 p.317; infosys FY2025 p.238; infosys FY2025 p.73; infosys FY2025 p.242 |
| n03 | number | wrong, citation ok, retrieval miss | Wipro’s consolidated net profit for FY2025 was H131.4 billion. [2] | [2] Wipro FY2025, p.16 | wipro FY2025 p.128; wipro FY2025 p.16; wipro FY2025 p.365; wipro FY2025 p.365; wipro FY2025 p.364 |
| n04 | number | correct, citation ok, retrieval hit | HCLTech’s operating profit ratio (EBIT margin) for FY2025 was 18.3%[1] | [1] HCLTech FY2025, p.11 | hcltech FY2025 p.11; hcltech FY2025 p.120; hcltech FY2025 p.91; hcltech FY2025 p.11; hcltech FY2025 p.120 |
| n05 | number | correct, citation ok, retrieval hit | The turnover rate for permanent employees at Infosys in fiscal 2026 was 12.6 %[1] | [1] Infosys FY2026, p.145 | infosys FY2026 p.145; infosys FY2026 p.85; infosys FY2026 p.168; infosys FY2026 p.168; infosys FY2026 p.168 |
| n06 | number | correct, citation ok, retrieval hit | TCS had 5,84,519 permanent employees at the end of FY 2026. [2][4] | [2] TCS FY2026, p.44; [4] TCS FY2026, p.130 | tcs FY2026 p.56; tcs FY2026 p.44; tcs FY2026 p.119; tcs FY2026 p.130; tcs FY2026 p.120 |
| n07 | number | correct, citation ok, retrieval hit | Tech Mahindra’s consolidated revenue recognised in the statement of profit and loss for FY2026 was ₹568,154 million[2]. | [2] Tech Mahindra FY2026, p.626 | techmahindra FY2026 p.543; techmahindra FY2026 p.626; techmahindra FY2026 p.608; techmahindra FY2026 p.319; techmahindra FY2026 p.578 |
| n08 | number | correct, citation ok, retrieval miss | HCLTech’s consolidated net income for FY2026 was ₹16,642 crores. [1] | [1] HCLTech FY2026, p.83 | hcltech FY2026 p.83; hcltech FY2026 p.367; hcltech FY2026 p.8; hcltech FY2026 p.448; hcltech FY2026 p.451 |
| w01 | narrative | answered, retrieval hit, keywords 80% | TCS’s operating margin expanded in FY 2026 because the company improved its business mix, productivity and realisation, rebalanced its pyramid, and benefited from favourable currency movements, all of which supported margin growth while investments in talent and capability building were offset by these gains[1][4]. | [1] TCS FY2026, p.25; [4] TCS FY2026, p.59 | tcs FY2026 p.25; tcs FY2026 p.59; tcs FY2026 p.25; tcs FY2026 p.59; tcs FY2026 p.28 |
| w02 | narrative | answered, retrieval hit, keywords 0% | The growth was also impacted by a reduction in discretionary spending by clients due to macroeconomic challenges and geopolitical dynamics. [4] | [4] Wipro FY2026, p.38 | wipro FY2026 p.23; wipro FY2026 p.111; wipro FY2026 p.35; wipro FY2026 p.38; wipro FY2026 p.271 |
| w03 | narrative | answered, retrieval hit, keywords 100% | Wipro’s general and administrative expenses rose in FY2026 mainly because of the implementation of a new labor code in India (₹2,599 million included in employee compensation), an increase in lifetime expected credit loss provisions, and a one‑time insurance claim of ₹1,805 million received in FY2025 [1]. | [1] Wipro FY2026, p.38 | wipro FY2026 p.38; wipro FY2026 p.39; wipro FY2026 p.44; wipro FY2026 p.40; wipro FY2026 p.184 |
| w04 | narrative | answered, retrieval miss, keywords 50% | Its consolidated impact was ₹1,289 crore[3][4] | [3] Infosys FY2026, p.80; [4] Infosys FY2026, p.337 | infosys FY2026 p.288; infosys FY2026 p.78; infosys FY2026 p.80; infosys FY2026 p.337; infosys FY2026 p.288 |
| r01 | refusal | refused (correct) | Not found in the reports. |  | wipro FY2026 p.114; wipro FY2025 p.104; wipro FY2026 p.222; wipro FY2025 p.128; wipro FY2025 p.202 |
| r02 | refusal | refused (correct) | Not found in the reports. |  | tcs FY2025 p.70; tcs FY2025 p.88; techmahindra FY2025 p.411; tcs FY2025 p.76; hcltech FY2025 p.107 |
| r03 | refusal | refused (correct) | Not found in the reports. |  | infosys FY2026 p.119; infosys FY2025 p.109; infosys FY2025 p.214; infosys FY2026 p.227; infosys FY2026 p.102 |
| c01 | comparison | wrong | Not found in the reports. |  | tcs FY2025 p.85; tcs FY2025 p.140; hcltech FY2025 p.125; hcltech FY2025 p.11; tcs FY2025 p.140 |
| c02 | comparison | wrong, citation bad | Infosys’s consolidated revenue rose from ₹1,62,990 crore in FY2025 to ₹1,78,650 crore in FY2026, an increase of ₹15,660 crore. [1] | [1] Infosys FY2026, p.78 | infosys FY2026 p.78; infosys FY2026 p.288; infosys FY2026 p.288; infosys FY2026 p.79; infosys FY2026 p.82 |
| c03 | comparison | wrong, citation ok | The company with the highest operating margin in FY 2026 was Tata Consultancy Services (TCS) with an operating margin of 25.0%[1][2][3]. | [1] TCS FY2026, p.59; [2] TCS FY2026, p.25; [3] TCS FY2026, p.9 | tcs FY2026 p.59; tcs FY2026 p.25; tcs FY2026 p.9; techmahindra FY2026 p.19; wipro FY2026 p.33 |
| c04 | comparison | wrong | Not found in the reports. |  | hcltech FY2026 p.6; hcltech FY2026 p.83; hcltech FY2026 p.8; hcltech FY2026 p.182; hcltech FY2026 p.7 |
