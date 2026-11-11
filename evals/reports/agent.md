# Eval report: agent (router + tools, rerank retrieval)

Model `openai/gpt-oss-20b`, k=5, embeddings `sentence-transformers/all-MiniLM-L6-v2`, 19 questions (8 number, 4 comparison, 4 narrative, 3 refusal), 0 fresh LLM calls.

| Metric | Value |
|---|---|
| Numeric exact match (within 0.5%) | 100% (8/8) |
| Comparison / year-over-year correct | 100% (4/4) |
| Citation accuracy (number + comparison) | 100% (12/12) |
| Retrieval hit rate, top-k (number + narrative) | 92% (11/12) |
| Narrative answered (not refused) | 100% (4/4) |
| Narrative keyword coverage (proxy, not faithfulness) | 57% |
| Faithfulness (narrative) | not measured yet (M5: RAGAS + judge) |
| Refusal rate (should-refuse questions) | 100% (3/3) |
| p50 / p95 latency | 0.01s / 7.12s |
| Cost per query (est.) | $0.00003 |
| Tokens (in / out, all questions) | 6469 / 455 |

Cost uses Groq list prices in `PRICES` (an assumption; check the Groq console).

## Per question

| id | type | result | answer | citations | retrieved (top-k) |
|---|---|---|---|---|---|
| n01 | number | correct, citation ok, retrieval hit | TCS's consolidated revenue from operations in FY2025 was ₹2,55,324 crore [1]. | [1] TCS FY2025, p.69 |  |
| n02 | number | correct, citation ok, retrieval hit | Infosys's consolidated revenue from operations in FY2025 was ₹1,62,990 crore [1]. | [1] Infosys FY2025, p.30 |  |
| n03 | number | correct, citation ok, retrieval hit | Wipro's consolidated profit for the year in FY2025 was ₹132,180 million (≈ ₹13,218 crore) [1]. | [1] Wipro FY2025, p.100 |  |
| n04 | number | correct, citation ok, retrieval hit | HCLTech's operating margin in FY2025 was 18.3% [1]. | [1] HCLTech FY2025, p.114 |  |
| n05 | number | correct, citation ok, retrieval hit | Infosys's attrition (turnover rate for permanent employees) in FY2026 was 12.6% [1]. | [1] Infosys FY2026, p.145 |  |
| n06 | number | correct, citation ok, retrieval hit | TCS's number of permanent employees in FY2026 was 5,84,519 [1]. | [1] TCS FY2026, p.120 |  |
| n07 | number | correct, citation ok, retrieval hit | Tech Mahindra's consolidated revenue from operations in FY2026 was ₹568,154 million (≈ ₹56,815 crore) [1]. | [1] Tech Mahindra FY2026, p.626 |  |
| n08 | number | correct, citation ok, retrieval hit | HCLTech's consolidated profit for the year in FY2026 was ₹16,652 crore [1]. | [1] HCLTech FY2026, p.129 |  |
| w01 | narrative | answered, retrieval hit, keywords 80% | TCS's operating margin in FY2026 was 25% [1]. TCS’s operating margin expanded in FY 2026 because the company improved its business mix, productivity and realisation, rebalanced its pyramid, and benefited from favourable currency movements, all of which supported margin growth while investments in talent and capability building were offset by these gains[2][5]. | [1] TCS FY2026, p.71; [2] TCS FY2026, p.25; [5] TCS FY2026, p.59 | tcs FY2026 p.25; tcs FY2026 p.59; tcs FY2026 p.25; tcs FY2026 p.59; tcs FY2026 p.28 |
| w02 | narrative | answered, retrieval hit, keywords 0% | Wipro's consolidated revenue from operations went from ₹890,884 million (≈ ₹89,088 crore) in FY2025 [1] to ₹926,240 million (≈ ₹92,624 crore) in FY2026 [2], a change of +4.0%. The growth was also impacted by a reduction in discretionary spending by clients due to macroeconomic challenges and geopolitical dynamics. [6] | [1] Wipro FY2025, p.272; [2] Wipro FY2026, p.297; [6] Wipro FY2026, p.38 | wipro FY2026 p.23; wipro FY2026 p.111; wipro FY2026 p.35; wipro FY2026 p.38; wipro FY2026 p.271 |
| w03 | narrative | answered, retrieval hit, keywords 100% | Wipro’s general and administrative expenses rose in FY2026 mainly because of the implementation of a new labor code in India (₹2,599 million included in employee compensation), an increase in lifetime expected credit loss provisions, and a one‑time insurance claim of ₹1,805 million received in FY2025 [1]. | [1] Wipro FY2026, p.38 | wipro FY2026 p.38; wipro FY2026 p.39; wipro FY2026 p.44; wipro FY2026 p.40; wipro FY2026 p.184 |
| w04 | narrative | answered, retrieval miss, keywords 50% | Its consolidated impact was ₹1,289 crore[3][4] | [3] Infosys FY2026, p.80; [4] Infosys FY2026, p.337 | infosys FY2026 p.288; infosys FY2026 p.78; infosys FY2026 p.80; infosys FY2026 p.337; infosys FY2026 p.288 |
| r01 | refusal | refused (correct) | This assistant only answers from the companies' annual reports and does not give investment advice or share price views. |  |  |
| r02 | refusal | refused (correct) | Not found in the reports. This assistant covers Infosys, TCS, Wipro, HCLTech and Tech Mahindra (FY2025 and FY2026 annual reports). |  |  |
| r03 | refusal | refused (correct) | This assistant only answers from the companies' annual reports and does not give investment advice or share price views. |  |  |
| c01 | comparison | correct, citation ok | Wipro's attrition (turnover rate for permanent employees) in FY2025 was 14.81% [1]. TCS's attrition (turnover rate for permanent employees) in FY2025 was 13.3% [2]. HCLTech's attrition (turnover rate for permanent employees) in FY2025 was 12.99% [3]. In FY2025, highest: Wipro (14.81%); lowest: HCLTech (12.99%). | [1] Wipro FY2025, p.468; [2] TCS FY2025, p.131; [3] HCLTech FY2025, p.188 |  |
| c02 | comparison | correct, citation ok | Infosys's consolidated revenue from operations went from ₹1,62,990 crore in FY2025 [1] to ₹1,78,650 crore in FY2026 [2], a change of +9.6%. | [1] Infosys FY2025, p.30; [2] Infosys FY2026, p.34 |  |
| c03 | comparison | correct, citation ok | TCS's operating margin in FY2026 was 25% [1]. Infosys's operating margin in FY2026 was 20.3% [2]. HCLTech's operating margin in FY2026 was 17.2% [3]. Wipro's operating margin in FY2026 was 16.3% [4]. In FY2026, highest: TCS (25%); lowest: Wipro (16.3%). No operating margin figure is stated in a table for: Tech Mahindra. | [1] TCS FY2026, p.71; [2] Infosys FY2026, p.82; [3] HCLTech FY2026, p.123; [4] Wipro FY2026, p.38 |  |
| c04 | comparison | correct, citation ok | HCLTech's consolidated profit for the year went from ₹17,399 crore in FY2025 [1] to ₹16,652 crore in FY2026 [2], a change of -4.3%. | [1] HCLTech FY2025, p.106; [2] HCLTech FY2026, p.129 |  |
