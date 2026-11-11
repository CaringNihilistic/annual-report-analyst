import pytest

from ingest.tables import (
    detect_unit,
    extract_metrics,
    find_year_column,
    header_texts,
    match_metric,
    parse_number,
)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("1,53,670", 153670.0),
        ("(1,234.5)", -1234.5),
        ("21.1%", 21.1),
        ("₹ 4,567", 4567.0),
        ("12.5*", 12.5),
        ("-", None),
        ("—", None),
        ("", None),
        ("n/a", None),
    ],
)
def test_parse_number(raw, expected):
    assert parse_number(raw) == expected


@pytest.mark.parametrize(
    "label, metric",
    [
        ("Revenue from operations", "revenue"),
        ("Total income from operations", "revenue"),
        ("Profit for the year", "net_profit"),
        ("Operating margin (%)", "operating_margin"),
        ("Total employees", "headcount"),
        ("Attrition rate (IT services)", "attrition"),
        ("Revenue growth (%)", None),
        ("Other income", None),
    ],
)
def test_match_metric(label, metric):
    assert match_metric(label) == metric


@pytest.mark.parametrize(
    "header, fy, idx",
    [
        (["Particulars", "2025", "2024"], 2025, 1),
        (["Particulars", "2025", "2024"], 2024, 2),
        (["Particulars", "FY 2024-25", "FY 2023-24"], 2025, 1),
        (["Particulars", "FY24", "FY25"], 2025, 2),
        (["Particulars", "Year ended March 31, 2025", "Year ended March 31, 2024"], 2025, 1),
        (["Particulars", "2025 vs 2024 change %", "2025"], 2025, 2),
        (["Particulars", "FY25 Male", "FY25 Total", "FY24 Total"], 2025, 2),
        (["Particulars", "Q4", "Q3"], 2025, None),
    ],
)
def test_find_year_column(header, fy, idx):
    assert find_year_column(header, fy) == idx


def test_date_is_not_a_fiscal_range():
    # "2025-03-31" must not be read as fiscal 2025-26
    assert find_year_column(["Particulars", "As at 2025-03-31"], 2025) == 1


def test_header_texts_merges_header_rows():
    rows = [["", "FY 2024-25", "FY 2024-25"], ["Particulars", "Male", "Total"], ["x", "1", "2"]]
    assert header_texts(rows) == ["Particulars", "FY 2024-25 Male", "FY 2024-25 Total"]


def test_detect_unit():
    assert detect_unit("revenue", ["Revenue", "(₹ in crore)"]) == ("crore", "INR")
    assert detect_unit("revenue", ["Revenue (US$ million)", "(₹ in crore)"]) == ("million", "USD")
    assert detect_unit("revenue", ["Revenue", None]) is None
    assert detect_unit("attrition", []) == ("percent", None)
    assert detect_unit("headcount", []) == ("count", None)


def _doc(tables):
    return {"company": "infosys", "fiscal_year": 2025, "chunks": [], "tables": tables}


def test_extract_metrics_end_to_end():
    doc = _doc(
        [
            {
                "page": 210,
                "section": "Consolidated Statement of Profit and Loss",
                "caption": None,
                "context": "(In ₹ crore)",
                "rows": [
                    ["Particulars", "2025", "2024"],
                    ["Revenue from operations", "1,62,990", "1,53,670"],
                    ["Profit for the year", "26,750", "26,248"],
                ],
            },
            {
                "page": 12,
                "section": "Key highlights",
                "caption": None,
                "context": None,
                "rows": [["Metric", "FY25", "FY24"], ["Operating margin", "21.1%", "20.7%"]],
            },
        ]
    )
    got = {m.metric: m for m in extract_metrics(doc)}
    assert got["revenue"].value == 162990.0
    assert (got["revenue"].unit, got["revenue"].currency) == ("crore", "INR")
    assert got["revenue"].source_page == 210
    assert got["net_profit"].value == 26750.0
    assert got["operating_margin"].value == 21.1
    assert got["operating_margin"].unit == "percent"


def test_extract_metrics_skips_standalone_and_unknown_units():
    doc = _doc(
        [
            {
                "page": 300,
                "section": "Standalone Statement of Profit and Loss",
                "caption": None,
                "context": "(In ₹ crore)",
                "rows": [["Particulars", "2025"], ["Revenue from operations", "1,36,592"]],
            },
            {
                "page": 5,
                "section": None,
                "caption": None,
                "context": None,  # no unit anywhere -> must not guess
                "rows": [["Particulars", "2025"], ["Revenue from operations", "19,277"]],
            },
        ]
    )
    assert extract_metrics(doc) == []


def test_consolidated_preferred_over_unlabelled():
    revenue_row = lambda v: [["Particulars", "2025"], ["Revenue from operations", v]]  # noqa: E731
    doc = _doc(
        [
            {
                "page": 8,
                "section": "Highlights",
                "caption": None,
                "context": "₹ crore",
                "rows": revenue_row("1,63,000"),
            },
            {
                "page": 210,
                "section": "Consolidated Balance",
                "caption": None,
                "context": "₹ crore",
                "rows": revenue_row("1,62,990"),
            },
        ]
    )
    (rev,) = extract_metrics(doc)
    assert rev.value == 162990.0 and rev.source_page == 210


# --- Rules learned from the real reports (see docstrings for the source) ---


@pytest.mark.parametrize(
    "text",
    ["(In ` crore)", "(H crore)", "(C in millions, except per share data)", "Revenue in C million"],
)
def test_rupee_glyph_substitutes_are_inr(text):
    # Infosys renders ₹ as `, TCS as H, Wipro as C.
    assert detect_unit("revenue", [text])[1] == "INR"


def test_standalone_columns_skipped_in_spanning_header():
    # TCS FY2026 p.36: only the first column of each group names it.
    header = [
        "Particulars",
        "Standalone Financial Year 2025-26",
        "Financial Year 2024-25",
        "Consolidated Financial Year 2025-26",
        "(H crore) Financial Year 2024-25",
    ]
    assert find_year_column(header, 2026) == 3
    assert find_year_column(header, 2025) == 4


def test_percent_header_is_a_valid_year_column():
    # Infosys BRSR turnover table: "Turnover rate in fiscal 2025 (In %)".
    header = ["", "fiscal 2025 (In %) Male", "fiscal 2025 (In %) Total", "fiscal 2024 (In %) Total"]
    assert find_year_column(header, 2025) == 2


def test_permanent_employees_in_turnover_table_is_attrition():
    assert match_metric("Permanent employees", "22. Turnover rate for permanent employees") == (
        "attrition"
    )
    assert match_metric("Permanent employees") is None


@pytest.mark.parametrize(
    "label, metric",
    [
        ("EBIT / Total Revenue", "operating_margin"),  # TCS
        ("Revenue (KL/Mn USD)", None),  # Wipro water intensity
        ("Profit after tax (% of revenue)", None),
        ("Segmental operating margin (%)", None),
        ("The Employees' Provident Funds Act", None),
        ("Total Permanent Employees", "headcount"),
        ("Net profit #", "net_profit"),
        ("Net profit margin (%)", None),
    ],
)
def test_label_rules_from_real_reports(label, metric):
    assert match_metric(label) == metric


def test_unit_only_row_changes_unit_for_rows_below():
    # Infosys "Key trends": ₹ crore block, then a "US$ million" block with the same labels.
    doc = _doc(
        [
            {
                "page": 17,
                "section": "Key trends",
                "caption": None,
                "context": None,
                "rows": [
                    ["In ₹ crore", "FY 2026", "FY 2025"],
                    ["Net profit", "29,440", "26,713"],
                    ["In US$ million", "", ""],
                    ["Net profit", "3,313", "3,158"],
                ],
            }
        ]
    )
    from ingest.tables import extract_candidates

    got = {(m.value, m.currency) for m, _ in extract_candidates({**doc, "fiscal_year": 2026})}
    assert got == {(29440.0, "INR"), (3313.0, "USD")}


def test_ratio_rows_in_percent_are_not_money():
    # TCS "Ratio Analysis": "Profit After Tax*" with Units "%" is growth, not profit.
    doc = _doc(
        [
            {
                "page": 71,
                "section": "Ratio Analysis",
                "caption": "(₹ crore)",
                "context": None,
                "rows": [["Ratio", "Units", "FY 2025"], ["Profit After Tax*", "%", "4.2"]],
            }
        ]
    )
    assert extract_metrics(doc) == []


@pytest.mark.parametrize(
    "text", ["(I in millions, except share data)", "sales of H 713,451 Million"]
)
def test_more_rupee_glyphs(text):
    # Wipro FY2026 uses I, and H directly before an amount.
    assert detect_unit("revenue", [text]) == ("million", "INR")


def test_related_party_tables_skipped():
    # HCLTech FY2025 p.403: "Revenue from operations" from a related party (₹34 crore).
    doc = _doc(
        [
            {
                "page": 403,
                "section": "Notes to consolidated financial statements",
                "caption": None,
                "context": "(All amounts in crores of ₹)",
                "rows": [
                    ["Transactions with related parties", "Year ended 31 March 2025"],
                    ["Revenue from operations", "34"],
                ],
            }
        ]
    )
    assert extract_metrics(doc) == []


@pytest.mark.parametrize(
    "label, where, metric",
    [
        ("Employees", "", None),  # TechM p.382: complaints filed by employees
        ("Change in specific energy (%) per headcount", "", None),
        ("Total employees (D + E)", "", "headcount"),
        ("Permanent", "22. Turnover rate for permanent employees", "attrition"),
    ],
)
def test_headcount_and_attrition_labels(label, where, metric):
    assert match_metric(label, where) == metric


def test_permanent_employees_preferred_for_headcount():
    # Headline headcount is permanent employees; BRSR 'Total employees' adds contract staff.
    doc = _doc(
        [
            {
                "page": 483,
                "section": "BRSR",
                "caption": None,
                "context": None,
                "rows": [
                    ["Category", "FY 2024-25 Total"],
                    ["Total Permanent Employees", "225,306"],
                ],
            },
            {
                "page": 489,
                "section": "BRSR",
                "caption": None,
                "context": None,
                "rows": [["Category", "FY 2024-25 Total (A)"], ["Total Employees", "235,415"]],
            },
        ]
    )
    (hc,) = extract_metrics(doc)
    assert hc.value == 225306.0


def test_unlabelled_note_takes_part_from_heading():
    # TechM FY2026: "v. Contract Price" notes exist in both the standalone and consolidated parts.
    def note(page, value):
        return {
            "page": page,
            "section": "v. Contract Price",
            "caption": "` in Million",
            "context": None,
            "rows": [["Particulars", "Year ended March 31, 2025"], ["Revenue recognised", value]],
        }

    doc = _doc([note(507, "489,270"), note(626, "568,154")])
    doc["chunks"] = [
        {"page": 427, "section": "Standalone Financial Statements", "text": ""},
        {"page": 542, "section": "Consolidated Financial Statements", "text": ""},
    ]
    (rev,) = extract_metrics(doc)
    assert rev.value == 568154.0 and rev.source_page == 626


def test_crore_without_currency_is_inr_but_million_is_not():
    # OCR of TCS FY2025 drops the ₹: "( crore) Year ended March 31, 2024".
    assert detect_unit("revenue", ["( crore) Year ended March 31, 2024"]) == ("crore", "INR")
    assert detect_unit("revenue", ["(in million)"]) is None


def test_revenue_recognised_from_deferred_revenue_is_not_revenue():
    # TCS FY2025 p.216: a deferred-revenue movement, not the company's revenue.
    assert match_metric("Revenue recognised that was included in the unearned revenue") is None
    assert match_metric("Revenue recognised") == "revenue"
