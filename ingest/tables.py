"""Turn raw parsed tables into financial_metrics rows.

Rule-based: a row label is matched against patterns for each metric, the value is
read from the column whose header names the report's own fiscal year, and the unit
is read from the label, header, caption or the text just above the table. If the
year column or the unit can't be determined, the row is skipped rather than guessed.

Usage (spot-check helper, prints what would be loaded and from which page):
    python -m ingest.tables
"""

import json
import re
from collections import Counter
from dataclasses import asdict, dataclass

from app.config import get_settings

# Metric -> row-label patterns (matched against the lowercased, whitespace-normalised label).
METRIC_PATTERNS: dict[str, list[str]] = {
    "revenue": [
        r"^(total )?(income|revenue)s? from operations\b",
        r"^(total )?revenues?( \(\w+\))?$",  # "Revenue", "Revenue (1)" with a footnote marker
        r"^revenues? in [hci`₹]",  # Wipro "Revenue in C million"
        # Contract-price reconciliation, not "Revenue recognised that was included in ..."
        r"^revenue recognised( in (the )?statement of profit and loss)?$",
    ],
    "net_profit": [
        r"^(net )?profit for the (year|period)\b",
        r"^profit after tax\b",
        r"^net profit\b(?!.*margin)",
    ],
    "operating_margin": [
        r"\boperating (profit )?margin\b",
        r"\bebit margin\b",
        r"^operating profit ratio\b",  # HCLTech "Key financial ratios"
    ],
    # Needs a qualifier: a bare "Employees" row is usually a count of something else
    # (e.g. complaints filed by employees).
    "headcount": [
        r"^total (number of )?(permanent )?employees\b",
        r"^(total )?number of employees\b",
        r"^employees \((no\.?|nos\.?|number)\)$",
        r"^(total )?headcount\b",
    ],
    "attrition": [r"\battrition\b"],
}
# Ratio-style labels, checked before EXCLUDE_LABEL (which rejects "/"). TCS: "EBIT / Total Revenue".
RATIO_PATTERNS: dict[str, str] = {
    "operating_margin": r"^(ebit|operating (income|profit)) ?/ ?(total )?revenues?\b",
}
# Labels that contain a metric's words but are something else
# (e.g. "Revenue (KL/Mn USD)" water intensity, "Profit after tax (% of revenue)").
EXCLUDE_LABEL = (
    r"intensity|/|\bper\b|% of|segment|provident|differently|benefit|growth|energy|emission"
)
PERCENT_METRICS = {"operating_margin", "attrition"}
COUNT_METRICS = {"headcount"}

# Many reports' fonts map the rupee sign to another glyph: "(` crore)" (Infosys),
# "(H crore)" (TCS), "(C in million)", "(I in millions", "H 713,451 Million" (Wipro).
# Treat a lone `, H, C or I before a scale (optionally with an amount between) as INR.
INR_RE = re.compile(
    r"₹|\binr\b|\brs\.?(?=\s|\d|$)"
    r"|(?:^|[\s(.])[hci`]\s*(?:in\s+)?(?:\d[\d,.]*\s*)?(?:crores?|lakhs?|millions?|mn)\b"
    r"|\bin\s+[hci`]\s+(?:crores?|lakhs?|millions?)\b"
)
# Tables about a slice of the group, whose "Revenue from operations" is not the company's.
TABLE_EXCLUDE = r"related part|transactions with|nature of transaction"
# Headings that start the standalone or consolidated financial statements. Note tables inside
# them ("v. Contract Price") don't say which set they belong to, so the part is tracked by page.
PART_HEADING = re.compile(r"\b(standalone|consolidated) financial statements?\b")
USD_RE = re.compile(r"us\$|\busd\b|\$")

SCALES = {
    "crore": "crore",
    "crores": "crore",
    "lakh": "lakh",
    "lakhs": "lakh",
    "million": "million",
    "millions": "million",
    "mn": "million",
    "billion": "billion",
    "billions": "billion",
    "bn": "billion",
}


@dataclass
class MetricRow:
    company: str
    fiscal_year: int
    metric: str
    value: float
    unit: str
    currency: str | None
    source_page: int


def _norm(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def parse_number(s: str | None) -> float | None:
    """Parse '1,53,670', '(1,234.5)', '21.1%', '₹ 4,567' -> float. Dashes/blank -> None."""
    if s is None:
        return None
    t = re.sub(r"(₹|rs\.?|inr|us\$|usd|\$|%|\*|\s)", "", str(s).strip(), flags=re.I)
    t = t.replace(",", "")
    neg = t.startswith("(") and t.endswith(")")
    t = t.strip("()")
    if not re.fullmatch(r"-?\d+(\.\d+)?", t):
        return None
    v = float(t)
    return -v if neg else v


def match_metric(label: str, where: str = "") -> str | None:
    """Metric for a row label. `where` is the table's surrounding text (section, header...)."""
    lab = _norm(label)
    for metric, pattern in RATIO_PATTERNS.items():
        if re.search(pattern, lab):
            return metric
    if re.search(EXCLUDE_LABEL, lab):
        return None
    # BRSR "Turnover rate for permanent employees" tables: the row is just "Permanent employees"
    # (or "Permanent" when the label wraps onto a second row, as in Tech Mahindra FY2026).
    if re.search(r"turnover|attrition", _norm(where)) and re.search(
        r"^(total )?permanent( employees)?\b", lab
    ):
        return "attrition"
    for metric, patterns in METRIC_PATTERNS.items():
        if any(re.search(p, lab) for p in patterns):
            return metric
    return None


def _years_in(text: str) -> set[int]:
    """Fiscal years named in a header cell. '2024-25' and 'FY25' both mean 2025."""
    t = _norm(text)
    years: set[int] = set()

    def _range(m):
        start, end = int(m[1]), int(m[2])
        if end not in (start + 1, (start + 1) % 100):
            return m[0]  # not a fiscal range (e.g. a date like 2025-03-31); leave as is
        years.add(start + 1)
        return " "

    t = re.sub(r"\b(20\d{2})\s*[-–/]\s*(\d{2}(?:\d{2})?)\b", _range, t)
    years.update(2000 + int(y) for y in re.findall(r"\b(?:fy|fiscal)\s*'?\s*(\d{2})\b", t))
    years.update(int(y) for y in re.findall(r"\b(20\d{2})\b", t))
    return years


def header_texts(rows: list[list[str]]) -> list[str]:
    """Combine multi-row headers: the header row plus following rows that hold no data."""
    header = list(rows[0])
    for row in rows[1:3]:
        if any(parse_number(c) is not None and not _years_in(c) for c in row[1:]):
            break
        header = [f"{h} {c}".strip() for h, c in zip(header, row, strict=False)]
    return header


def column_groups(header: list[str]) -> list[str | None]:
    """'standalone' / 'consolidated' / None per column.

    Spanning headers often name the group only on its first column
    ("Standalone FY25", "FY24", "Consolidated FY25", "FY24"), so the label carries right.
    """
    groups, cur = [], None
    for h in header:
        t = _norm(h)
        if "standalone" in t:
            cur = "standalone"
        elif "consolidated" in t:
            cur = "consolidated"
        groups.append(cur)
    return groups


def find_year_column(header: list[str], fiscal_year: int) -> int | None:
    """Index of the column for fiscal_year, never a standalone one.

    Prefers a 'total' sub-column if there are several (e.g. Male / Female / Total).
    """
    groups = column_groups(header)
    hits = []
    for i, h in enumerate(header):
        if i == 0 or groups[i] == "standalone":
            continue
        if re.search(r"change|growth|\bvs\b|% of", _norm(h)):
            continue
        if _years_in(h) == {fiscal_year}:
            hits.append(i)
    if not hits:
        return None
    totals = [i for i in hits if "total" in _norm(header[i])]
    return (totals or hits)[0]


def _currency(t: str) -> str | None:
    return "USD" if USD_RE.search(t) else ("INR" if INR_RE.search(t) else None)


def _scale(t: str) -> str | None:
    return next((SCALES[w] for w in re.findall(r"[a-z]+", t) if w in SCALES), None)


def detect_unit(metric: str, texts: list[str | None]) -> tuple[str, str | None] | None:
    """(unit, currency) for a metric, or None if it can't be determined."""
    if metric in PERCENT_METRICS:
        return "percent", None
    if metric in COUNT_METRICS:
        return "count", None
    currencies, scales = [], []
    for raw in texts:
        t = _norm(raw)
        if not t:
            continue
        cur, scale = _currency(t), _scale(t)
        if cur and scale:
            return scale, cur  # most specific text (row label first) wins
        if cur:
            currencies.append(cur)
        if scale:
            scales.append(scale)
    if len(set(currencies)) == 1 and len(set(scales)) == 1:
        return scales[0], currencies[0]
    # Crore and lakh are only ever rupees, so OCR losing the ₹ ("( crore)") doesn't matter.
    # "million" is used for both ₹ and US$, so it still needs an explicit currency.
    if (
        not currencies
        and set(scales)
        and set(scales) <= {"crore", "lakh"}
        and len(set(scales)) == 1
    ):
        return scales[0], "INR"
    return None


def statement_parts(chunks: list[dict]) -> list[tuple[int, str]]:
    """(first page, 'standalone' | 'consolidated') for each run of financial-statement pages."""
    parts: list[tuple[int, str]] = []
    for c in chunks:
        m = PART_HEADING.search(_norm(c.get("section")))
        if m and (not parts or parts[-1][1] != m[1]):
            parts.append((c["page"], m[1]))
    return parts


def _part_at(parts: list[tuple[int, str]], page: int) -> str | None:
    current = None
    for start, part in parts:
        if start > page:
            break
        current = part
    return current


def extract_candidates(doc: dict) -> list[tuple[MetricRow, int]]:
    """Every (metric row, score) found in one parsed report."""
    company, fy = doc["company"], doc["fiscal_year"]
    parts = statement_parts(doc.get("chunks", []))
    out = []
    for table in doc["tables"]:
        rows = table["rows"]
        if len(rows) < 2:
            continue
        header = header_texts(rows)
        col = find_year_column(header, fy)
        surrounding = [table.get("section"), table.get("caption"), table.get("context")]
        where = _norm(" ".join(filter(None, surrounding)))
        if col is None or re.search(
            TABLE_EXCLUDE, f"{_norm(header[0])} {_norm(table.get('section'))}"
        ):
            continue
        consolidated = column_groups(header)[col] == "consolidated"
        if "standalone" in where and not consolidated:
            continue
        consolidated = consolidated or "consolidated" in where
        # Unlabelled tables take the part of the report they sit in, as a preference only.
        part = None if consolidated else _part_at(parts, table["page"])
        all_headers = " ".join(header)
        row_unit = None  # set by a unit-only row such as "In US$ million" partway down a table
        for row in rows[1:]:
            if not row[0]:
                continue
            if all(parse_number(c) is None for c in row[1:]):
                text = " ".join(row)
                if _currency(_norm(text)):
                    row_unit = text
                continue
            if col >= len(row):
                continue
            metric = match_metric(row[0], f"{where} {all_headers}")
            if not metric:
                continue
            raw = row[col]
            value = parse_number(raw)
            if value is None or (metric in COUNT_METRICS and (value <= 0 or value % 1)):
                continue
            if metric == "revenue" and value <= 0:
                continue
            # A money/count metric whose row is expressed in % (e.g. "Units: %") is a ratio.
            if metric not in PERCENT_METRICS and (
                "%" in str(raw) or any(_norm(c) in {"%", "(%)", "in %"} for c in row)
            ):
                continue
            unit = detect_unit(
                metric,
                [row[0], row_unit, header[col], all_headers, *surrounding],
            )
            if unit is None:
                continue
            score = (3 if consolidated or part == "consolidated" else 0) + (
                1 if unit[1] == "INR" else 0
            )
            if part == "standalone":
                score -= 3
            # Companies' headline headcount is permanent employees (Infosys FY2025: 323,578);
            # BRSR "Total employees" also counts contract staff (348,596).
            if metric == "headcount" and "permanent" in _norm(row[0]):
                score += 1
            out.append(
                (MetricRow(company, fy, metric, value, unit[0], unit[1], table["page"]), score)
            )
    return out


def pick_best(candidates: list[tuple[MetricRow, int]]) -> list[MetricRow]:
    """One row per metric: highest score, then the value seen in most tables, then earliest page."""
    seen = Counter((c.metric, c.value, c.unit, c.currency) for c, _ in candidates)
    best: dict[str, tuple] = {}
    for c, score in candidates:
        key = (score, seen[(c.metric, c.value, c.unit, c.currency)], -c.source_page)
        if c.metric not in best or key > best[c.metric][0]:
            best[c.metric] = (key, c)
    return [c for _, c in best.values()]


def extract_metrics(doc: dict) -> list[MetricRow]:
    return pick_best(extract_candidates(doc))


def main() -> None:
    s = get_settings()
    files = sorted(s.processed_dir.glob("*.json"))
    if not files:
        raise SystemExit(f"No parsed reports in {s.processed_dir}. Run python -m ingest.parse")
    for f in files:
        doc = json.loads(f.read_text(encoding="utf-8"))
        rows = extract_metrics(doc)
        print(f"\n{f.stem}: {len(rows)} metrics")
        for r in sorted(rows, key=lambda r: r.metric):
            d = asdict(r)
            print(
                f"  {d['metric']:<17} {d['value']:>14,.2f} {d['unit']:<8} "
                f"{d['currency'] or '':<4} p.{d['source_page']}"
            )
        missing = set(METRIC_PATTERNS) - {r.metric for r in rows}
        if missing:
            print(f"  not found: {', '.join(sorted(missing))}")


if __name__ == "__main__":
    main()
