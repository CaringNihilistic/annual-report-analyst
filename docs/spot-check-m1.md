# M1 spot-check: 20 extracted numbers

Open `data/raw/<report>.pdf` at the page shown (PDF page number, not the printed one) and write what the report says. Mark OK if it matches and is the consolidated, current-year figure.

**Checked on 2026-11-11 by Claude (AI), not by a person.** Method: each cited PDF page was rendered to an image and the number read off the page by eye, independently of the parsed text. The printed page label is noted too, to show it differs from the PDF page.

| # | Report | Metric | Extracted | PDF page | Why it's on the list | PDF shows | OK? |
|---|---|---|---|---|---|---|---|
| 1 | tcs_FY2025 | revenue | 255,324 INR crore | 69 | OCR'd report | Board's Report "Financial results", Consolidated FY 2025, Revenue from operations ₹2,55,324 crore (printed p.67) | OK |
| 2 | tcs_FY2025 | net_profit | 48,797 INR crore | 69 | OCR'd report | Same table, Consolidated FY 2025, Profit for the year 48,797 (attributable to shareholders 48,553) | OK |
| 3 | tcs_FY2025 | attrition | 13.3% | 131 | OCR'd report; text layer unreadable, check by eye | BRSR 22 "Turnover rate for permanent employees", FY 2025 Total% 13.3 (printed p.129) | OK |
| 4 | tcs_FY2025 | operating_margin | 24.3% | 96 | OCR'd report | "Ratio Analysis – 10 years", EBIT / Total Revenue, FY 2025: 24.3% (printed p.94) | OK |
| 5 | tcs_FY2026 | operating_margin | 25% | 71 | from 'EBIT / Total Revenue' ratio row | "Ratio Analysis – 10 years", EBIT / Total Revenue, FY 2026: 25.0% (printed p.100) | OK |
| 6 | tcs_FY2026 | headcount | 584,519 | 120 |  | BRSR 7, Total Permanent Employees FY 2026: 5,84,519 (printed p.149) | OK |
| 7 | infosys_FY2025 | revenue | 162,990 INR crore | 30 |  | Board's report, Consolidated 2025, Revenue from operations 1,62,990 (₹ crore) (printed p.58) | OK |
| 8 | infosys_FY2025 | headcount | 323,578 | 149 | permanent employees, not BRSR total | BRSR 7, Total permanent employees Fiscal 2025: 3,23,578 (printed p.177) | OK |
| 9 | infosys_FY2026 | net_profit | 29,474 INR crore | 34 | statutory incl. non-controlling interests (29,440 attributable) | Board's report, Consolidated 2026, Profit after tax 29,474; attributable to owners 29,440 (printed p.64) | OK |
| 10 | infosys_FY2026 | attrition | 12.6% | 145 |  | BRSR 22, Turnover rate in fiscal 2026, Total 12.6 (printed p.175) | OK |
| 11 | wipro_FY2025 | net_profit | 132,180 INR million | 100 | ₹ million | Board's Report key highlights, Consolidated 2024-25, Net profit for the year 132,180 (₹ in Millions) (printed p.114) | OK |
| 12 | wipro_FY2025 | headcount | 225,306 | 483 | permanent (BRSR total employees is 235,415) | BRSR 7, Total Permanent Employees FY 2024-25: 225,306 (printed p.497) | OK |
| 13 | wipro_FY2026 | revenue | 926,240 INR million | 297 | consolidated statement; MD&A shows 928,093 | Consolidated Statement of Profit and Loss (Ind AS), Revenue from operations, year ended March 31, 2026: 926,240 (₹ in millions) (printed p.310). The MD&A on p.38 explains 928,093 includes exchange-rate effects for segment reporting | OK |
| 14 | wipro_FY2026 | operating_margin | 16.3% | 38 |  | MD&A "Financial Performance", Operating Margin FY26: 16.30% (printed p.46) | OK |
| 15 | hcltech_FY2025 | operating_margin | 18.3% | 114 | from 'Operating profit ratio' | "Key financial ratios", Operating profit ratio, 31 March 2025: 18.3% (printed p.107; group figures, the standalone ratios follow later) | OK |
| 16 | hcltech_FY2025 | revenue | 117,055 INR crore | 106 |  | "Results of operations (Consolidated)", Revenue from operations, 31 March 2025: 117,055 (₹ Crores) (printed p.99) | OK |
| 17 | hcltech_FY2026 | net_profit | 16,652 INR crore | 129 |  | Directors' Report "Financial Results", Consolidated FY ended March 31, 2026, Profit for the year 16,652 (₹ in crores) (printed p.126) | OK |
| 18 | techmahindra_FY2025 | revenue | 529,883 INR million | 624 | ₹ million, unlabelled note in consolidated part | "Notes forming part of the Consolidated Financial Statements", v. Contract Price, Revenue recognised in statement of Profit and Loss, March 31, 2025: 529,883 (₹ in Million) (printed p.622) | OK |
| 19 | techmahindra_FY2026 | revenue | 568,154 INR million | 626 | ₹ million, unlabelled note in consolidated part | Same note in FY2026 consolidated notes, March 31, 2026: 568,154 (₹ in Million) (printed p.624) | OK |
| 20 | techmahindra_FY2026 | attrition | 12.1% | 381 | label split over two rows | BRSR 22, Turnover rate for permanent employees, FY 2025-26 Total 12.1 (printed p.379). The same page lists ₹4,89,270 Mn as *standalone* turnover, confirming it was right to reject that value as revenue | OK |

Result: 20 / 20 correct.

## Notes from the check

- **Page numbers:** every citation needs the PDF page, not the printed one. The two differ on every page checked, by between 2 and 30 pages.
- **Net profit definition:** companies label it differently. HCLTech FY2025 shows "Profit after tax 17,399" (including non-controlling interests) and "Profit for the year 17,390" (attributable). The definition used throughout is the figure including non-controlling interests.
- **Not covered by this check:** whether the *missing* values are truly absent. Tech Mahindra states no operating margin in any table, and this check doesn't prove that. It also doesn't cover the 28 extracted numbers that weren't sampled, although all 48 were automatically confirmed to be printed on their cited page (47 from the PDF text layer; TCS FY2025 attrition by eye, because its text layer is broken).
