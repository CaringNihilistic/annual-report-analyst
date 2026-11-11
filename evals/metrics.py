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
    # 16.3 also matches "16.30" (trailing zeros), but not 16.35 or 116.3.
    return re.search(rf"(?<![\d.]){re.escape(str(value))}0*(?!\d)", text) is not None


def claimed_numbers(text: str) -> list[float]:
    """Numbers an answer states as facts: everything except bare fiscal years like 2025."""
    return [n for n in numbers_in(text) if not (n.is_integer() and 2000 <= n <= 2030)]


_MARKS = re.compile(r"((?:\s*\[\d+(?:\s*,\s*\d+)*\])+)")


def cited_claims(answer: str) -> list[tuple[list[float], list[int]]]:
    """(numbers, citation ids) for each stretch of text that ends in citation markers.

    "went from ₹17,399 crore in FY2025 [1] to ₹16,652 crore in FY2026 [2], a change of
    -4.3%." -> [([17399], [1]), ([16652], [2])]. Text after the last marker (here the
    computed change) is not attributed to any page, and neither is an approximate
    conversion in "(≈ ...)": both are derived, not quoted.
    """
    out, start = [], 0
    for m in _MARKS.finditer(answer):
        segment = re.sub(r"\(≈[^)]*\)", " ", answer[start : m.start()])
        # A segment runs back to the previous marker or sentence end, whichever is later.
        segment = re.split(r"(?<=[.!?])\s+", segment)[-1]
        ids = [int(n) for n in re.findall(r"\d+", m[1])]
        nums = claimed_numbers(segment)
        if nums:
            out.append((nums, ids))
        start = m.end()
    return out


def citation_supports(answer: str, pages: dict[int, str]) -> bool:
    """Every cited number is printed on at least one of the pages its own citation points to."""
    claims = cited_claims(answer)
    return bool(claims) and all(
        any(contains_number(pages.get(i, ""), n) for i in ids) for nums, ids in claims for n in nums
    )


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
