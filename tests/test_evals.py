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

    page = {1: "Net income was ₹16,642 crores while OCF was ₹19,975 crores"}
    assert citation_supports("Net income was ₹16,642 crores [1].", page)
    assert not citation_supports("Net income was ₹16,652 crores [1].", page)
    assert citation_supports("In FY2026, net income was ₹16,642 crores [1].", page)  # year ignored
    assert not citation_supports("Not found in the reports.", page)  # no claim to support


def test_each_number_is_checked_against_its_own_citation():
    from evals.metrics import citation_supports, cited_claims

    text = (
        "Profit went from ₹17,399 crore in FY2025 [1] to ₹16,652 crore in FY2026 [2], "
        "a change of -4.3%. Highest: HCLTech."
    )
    assert cited_claims(text) == [([17399.0], [1]), ([16652.0], [2])]  # -4.3% is derived
    assert citation_supports(text, {1: "Profit after tax 17,399", 2: "Profit 16,652"})
    assert not citation_supports(text, {1: "Profit 16,652", 2: "Profit after tax 17,399"})
    # An approximate conversion is not a quoted figure.
    assert cited_claims("₹132,180 million (≈ ₹13,218 crore) [1].") == [([132180.0], [1])]


def test_decimal_matches_trailing_zeros():
    assert contains_number("Operating Margin 16.30%", 16.3)
    assert not contains_number("16.35%", 16.3)


def test_states_change_uses_absolute_tolerance_and_ignores_sign():
    from evals.metrics import states_change

    assert states_change("fell from ₹1,74,957 to ₹1,73,422, a change of -0.9%", 0.88)
    assert states_change("a change of -4.3%", 4.98) is False
    assert states_change("up 20.1%", 20.1)


def test_judge_verdict_parsing():
    from evals.judge import build_judge_prompt, parse_verdict

    v = parse_verdict(
        'Sure: {"claims": [{"claim": "Margin rose", "supported": true},'
        ' {"claim": "Due to AI", "supported": false}]}'
    )
    assert (v.supported, v.total, v.faithfulness, v.faithful) == (1, 2, 0.5, False)
    assert parse_verdict("not json").total == 0 and parse_verdict("not json").faithfulness is None
    assert '<source n="1">' in build_judge_prompt("q", "a", ["text"])
