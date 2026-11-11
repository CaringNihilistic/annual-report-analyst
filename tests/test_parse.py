from pathlib import Path

import pandas as pd
import pytest

from ingest.parse import Element, chunk_elements, parse_filename, table_to_rows


def test_parse_filename():
    assert parse_filename(Path("data/raw/infosys_FY2025.pdf")) == ("infosys", 2025)
    assert parse_filename(Path("techmahindra_FY2024.pdf")) == ("techmahindra", 2024)


@pytest.mark.parametrize("name", ["Infosys_FY2025.pdf", "infosys_2025.pdf", "acme_FY2025.pdf"])
def test_parse_filename_rejects_bad_names(name):
    with pytest.raises(ValueError):
        parse_filename(Path(name))


def test_chunks_merge_within_page_and_section():
    els = [Element(1, "Overview", "First."), Element(1, "Overview", "Second.")]
    chunks = chunk_elements(els)
    assert len(chunks) == 1
    assert chunks[0].text == "First.\nSecond."
    assert chunks[0].page == 1


def test_chunks_never_span_pages_or_sections():
    els = [
        Element(1, "A", "one"),
        Element(2, "A", "two"),
        Element(2, "B", "three"),
    ]
    chunks = chunk_elements(els)
    assert [(c.page, c.section, c.text) for c in chunks] == [
        (1, "A", "one"),
        (2, "A", "two"),
        (2, "B", "three"),
    ]


def test_chunks_respect_max_chars():
    long_para = " ".join(f"Sentence number {i}." for i in range(200))
    chunks = chunk_elements([Element(5, None, long_para)], max_chars=300)
    assert len(chunks) > 1
    assert all(len(c.text) <= 300 for c in chunks)
    assert all(c.page == 5 for c in chunks)
    assert " ".join(c.text for c in chunks) == long_para


def test_empty_elements_skipped():
    assert chunk_elements([Element(1, None, "   ")]) == []


def test_table_to_rows():
    df = pd.DataFrame({"Particulars": ["Revenue"], "2025": ["1,62,990"]})
    assert table_to_rows(df) == [["Particulars", "2025"], ["Revenue", "1,62,990"]]
