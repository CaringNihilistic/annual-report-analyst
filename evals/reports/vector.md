# Eval report: vector (vector search only (M2 baseline))

Model `openai/gpt-oss-20b`, k=5, embeddings `sentence-transformers/all-MiniLM-L6-v2`, 15 questions (8 number, 4 narrative, 3 refusal), 0 fresh LLM calls.

| Metric | Value |
|---|---|
| Numeric exact match (within 0.5%) | 38% (3/8) |
| Citation accuracy (numeric answers) | 100% (3/3) |
| Retrieval hit rate, top-k (number + narrative) | 42% (5/12) |
| Narrative answered (not refused) | 25% (1/4) |
| Narrative keyword coverage (proxy, not faithfulness) | 20% |
| Faithfulness (narrative) | not measured yet (M5: RAGAS + judge) |
| Refusal rate (should-refuse questions) | 100% (3/3) |
| p50 / p95 latency | 3.22s / 8.64s |
| Cost per query (est.) | $0.00009 |
| Tokens (in / out, all questions) | 15169 / 611 |

Cost uses Groq list prices in `PRICES` (an assumption; check the Groq console).

## Per question

| id | type | result | answer | citations | retrieved (top-k) |
|---|---|---|---|---|---|
| n01 | number | wrong, retrieval miss | Not found in the reports. |  | tcs FY2025 p.58; tcs FY2025 p.184; tcs FY2025 p.48; tcs FY2025 p.262; tcs FY2025 p.196 |
| n02 | number | wrong, retrieval miss | Not found in the reports. |  | infosys FY2025 p.8; infosys FY2025 p.242; infosys FY2025 p.257; infosys FY2025 p.346; infosys FY2025 p.317 |
| n03 | number | wrong, retrieval hit | Not found in the reports. |  | wipro FY2025 p.16; wipro FY2025 p.247; wipro FY2025 p.248; wipro FY2025 p.100; wipro FY2025 p.84 |
| n04 | number | correct, citation ok, retrieval hit | HCLTech’s operating profit ratio (EBIT margin) for FY 2025 was 18.3 %[1] | [1] HCLTech FY2025, p.79 | hcltech FY2025 p.79; hcltech FY2025 p.120; hcltech FY2025 p.91; hcltech FY2025 p.123; hcltech FY2025 p.80 |
| n05 | number | correct, citation ok, retrieval hit | The turnover rate for permanent employees at Infosys in fiscal 2026 was 12.6 %[5] | [5] Infosys FY2026, p.145 | infosys FY2026 p.145; infosys FY2026 p.33; infosys FY2026 p.13; infosys FY2026 p.357; infosys FY2026 p.145 |
| n06 | number | wrong, retrieval miss | Not found in the reports. |  | tcs FY2026 p.5; tcs FY2026 p.36; tcs FY2026 p.109; tcs FY2026 p.109; tcs FY2026 p.56 |
| n07 | number | wrong, retrieval miss | Not found in the reports. |  | techmahindra FY2026 p.436; techmahindra FY2026 p.319; techmahindra FY2026 p.280; techmahindra FY2026 p.495; techmahindra FY2026 p.315 |
| n08 | number | correct, citation ok, retrieval hit | HCLTech’s consolidated profit (net income) for FY 2026 was ₹16,642 crores[2] | [2] HCLTech FY2026, p.83 | hcltech FY2026 p.129; hcltech FY2026 p.83; hcltech FY2026 p.7; hcltech FY2026 p.132; hcltech FY2026 p.399 |
| w01 | narrative | answered, retrieval hit, keywords 80% | TCS’s operating margin expanded in FY 2026 mainly because of a favourable business mix, higher productivity and realisation, and a rebalancing of its service pyramid, all of which were supported by positive currency movements, offset only by investments in talent and capability building. [3] | [3] TCS FY2026, p.25 | tcs FY2026 p.59; tcs FY2026 p.5; tcs FY2026 p.25; tcs FY2026 p.6; tcs FY2026 p.59 |
| w02 | narrative | refused, retrieval miss, keywords 0% | Not found in the reports. |  | wipro FY2026 p.124; wipro FY2026 p.35; wipro FY2026 p.109; wipro FY2026 p.278; wipro FY2026 p.114 |
| w03 | narrative | refused, retrieval miss, keywords 0% | Not found in the reports. |  | wipro FY2026 p.184; wipro FY2026 p.280; wipro FY2026 p.44; wipro FY2026 p.54; wipro FY2026 p.35 |
| w04 | narrative | refused, retrieval miss, keywords 0% | Not found in the reports. |  | infosys FY2026 p.33; infosys FY2026 p.277; infosys FY2026 p.196; infosys FY2026 p.9; infosys FY2026 p.11 |
| r01 | refusal | refused (correct) | Not found in the reports. |  | wipro FY2026 p.33; wipro FY2026 p.35; wipro FY2025 p.101; wipro FY2025 p.17; wipro FY2026 p.114 |
| r02 | refusal | refused (correct) | Not found in the reports. |  | hcltech FY2025 p.107; techmahindra FY2025 p.411; techmahindra FY2025 p.33; hcltech FY2025 p.79; techmahindra FY2025 p.209 |
| r03 | refusal | refused (correct) | Not found in the reports. |  | infosys FY2025 p.110; infosys FY2026 p.120; infosys FY2026 p.357; infosys FY2025 p.231; infosys FY2026 p.245 |
