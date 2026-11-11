"""Scoring helpers for the eval suite. Pure functions, unit-tested in tests/test_evals.py."""

import re

TOLERANCE = 0.005  # numbers must be within 0.5%
# An answer may restate the number in another scale: 2,55,324 crore = 2.55 lakh crore
# = 2,553,240 million. Factors convert the stated number to the expected unit.
SCALE_FACTORS = (1, 10, 0.1, 1000, 0.001, 100_000)

_NUM = re.compile(r"(?<![\d.])\d[\d,]*(?:\.\d+)?")


def numbers_in(text: str) -> list[float]:
    """All numbers in a text. '₹2,55,324 crore' -> [255324.0]. Citation markers are ignored."""
    text = re.sub(r"\[\d+(?:\s*,\s*\d+)*\]", " ", text)
    out = []
    for m in _NUM.findall(text):
        try:
            out.append(float(m.replace(",", "")))
        except ValueError:
            pass
    return out


def matches_number(text: str, expected: float, tol: float = TOLERANCE) -> bool:
    """True if any number in text equals expected within tol, allowing a change of scale."""
    for n in numbers_in(text):
        for f in SCALE_FACTORS:
            if expected and abs(n * f - expected) / abs(expected) <= tol:
                return True
    return False


def contains_number(text: str, value: float) -> bool:
    """True if the value is printed in text, in any digit grouping (1,62,990 / 162,990)."""
    if float(value).is_integer():
        # Join digit groups split by commas ("2,55,324", OCR's "2, 55, 324") but not by plain
        # spaces, which separate adjacent table cells ("2,55,324 2,40,893").
        digits = re.sub(r"(?<=\d),\s?(?=\d)", "", text)
        return re.search(rf"(?<![\d.]){int(value)}(?![\d])", digits) is not None
    return re.search(rf"(?<![\d.]){re.escape(str(value))}(?!\d)", text) is not None


def claimed_numbers(text: str) -> list[float]:
    """Numbers an answer states as facts: everything except bare fiscal years like 2025."""
    return [n for n in numbers_in(text) if not (n.is_integer() and 2000 <= n <= 2030)]


def citation_supports(answer: str, cited_pages: list[str]) -> bool:
    """Every number the answer claims is printed on at least one of its cited pages."""
    claims = claimed_numbers(answer)
    return bool(claims) and all(any(contains_number(p, n) for p in cited_pages) for n in claims)


def keyword_coverage(text: str, key_points: list[str]) -> float:
    """Share of key points mentioned (case-insensitive). A cheap proxy, not faithfulness."""
    if not key_points:
        return 0.0
    t = text.lower()
    return sum(k.lower() in t for k in key_points) / len(key_points)


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    v = sorted(values)
    idx = min(len(v) - 1, max(0, round(p / 100 * (len(v) - 1))))
    return v[idx]
