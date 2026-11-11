import pytest

from evals.metrics import contains_number, keyword_coverage, matches_number, numbers_in, percentile


def test_numbers_in_ignores_citation_markers():
    assert numbers_in("Revenue was ₹2,55,324 crore [1][2].") == [255324.0]


@pytest.mark.parametrize(
    "text, expected, ok",
    [
        ("₹2,55,324 crore [1]", 255324, True),
        ("₹255,324 crore", 255324, True),
        ("about ₹2.55 lakh crore", 255324, True),  # restated in lakh crore
        ("₹2,553,240 million", 255324, True),  # restated in million
        ("₹2,40,893 crore", 255324, False),  # last year's figure
        ("18.3%", 18.3, True),
        ("18.2%", 18.3, False),  # 0.5% tolerance is tighter than 0.1 pp at 18.3
        ("Not found in the reports.", 18.3, False),
    ],
)
def test_matches_number(text, expected, ok):
    assert matches_number(text, expected) is ok


@pytest.mark.parametrize(
    "text, value, ok",
    [
        ("Revenue from operations 1,62,990 1,53,670", 162990, True),
        ("Revenue 162,990", 162990, True),
        ("OCR: 2, 55, 324", 255324, True),
        ("2,55,324 2,40,893", 2553242, False),  # adjacent cells must not merge
        ("1,162,990", 162990, False),
        ("Operating profit ratio % 18.3 18.2", 18.3, True),
        ("118.3", 18.3, False),
    ],
)
def test_contains_number(text, value, ok):
    assert contains_number(text, value) is ok


def test_keyword_coverage_and_percentile():
    assert keyword_coverage(
        "Driven by Productivity and pyramid", ["productivity", "pyramid", "x"]
    ) == (pytest.approx(2 / 3))
    assert percentile([1, 2, 3, 4, 5], 50) == 3
    assert percentile([], 95) == 0.0


def test_citation_supports_checks_the_answers_own_numbers():
    from evals.metrics import citation_supports

    page = "Net income was ₹16,642 crores while OCF was ₹19,975 crores"
    assert citation_supports("Net income was ₹16,642 crores [1].", [page])
    assert not citation_supports("Net income was ₹16,652 crores [1].", [page])
    assert citation_supports(
        "In FY2026, net income was ₹16,642 crores [1].", [page]
    )  # year ignored
    assert not citation_supports("Not found in the reports.", [page])  # no claim to support
