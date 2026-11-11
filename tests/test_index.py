from ingest.index import build_rows, embed_text, index_chunks, table_chunks


def fake_embed(texts):
    return [[float(len(t))] * 3 for t in texts]


TABLE = {
    "page": 150,
    "section": "Consolidated Statement of Profit and Loss",
    "caption": None,
    "context": "(₹ crore)",
    "rows": [["Particulars", "FY 2024-25"], ["Revenue from operations", "2,55,324"]],
}


def test_build_rows_without_network_or_db():
    doc = {
        "company": "tcs",
        "fiscal_year": 2025,
        "chunks": [
            {"page": 3, "section": "Chairman's letter", "text": "Hello"},
            {"page": 4, "section": None, "text": "World!"},
        ],
        "tables": [TABLE],
    }
    chunks, metrics = build_rows(doc, fake_embed)

    # Two text chunks plus one table chunk; the embedded text carries the section heading.
    assert [(c.page, c.text) for c in chunks[:2]] == [(3, "Hello"), (4, "World!")]
    assert chunks[0].embedding == [float(len("Chairman's letter\nHello"))] * 3
    assert chunks[2].page == 150 and "Revenue from operations | 2,55,324" in chunks[2].text
    assert all(c.company == "tcs" and c.fiscal_year == 2025 for c in chunks)
    (m,) = metrics
    assert (m.metric, m.value, m.unit, m.currency, m.source_page) == (
        "revenue",
        255324.0,
        "crore",
        "INR",
        150,
    )


def test_heading_only_chunks_are_not_indexed():
    doc = {
        "chunks": [
            {"page": 81, "section": "TCS' Business", "text": "TCS' Business"},
            {"page": 81, "section": "TCS' Business", "text": "TCS' Business\nWe serve clients..."},
        ],
        "tables": [],
    }
    assert [c["text"] for c in index_chunks(doc)] == ["TCS' Business\nWe serve clients..."]


def test_table_chunk_has_title_unit_header_and_rows():
    (chunk,) = table_chunks(TABLE)
    assert chunk["text"].splitlines() == [
        "Table: Consolidated Statement of Profit and Loss",
        "(₹ crore)",
        "Particulars | FY 2024-25",
        "Revenue from operations | 2,55,324",
    ]


def test_long_table_splits_and_repeats_header():
    rows = [["Particulars", "2025"]] + [[f"Line item {i}", f"{i},000"] for i in range(200)]
    chunks = table_chunks({**TABLE, "rows": rows}, max_chars=300)
    assert len(chunks) > 1
    assert all(len(c["text"]) <= 300 for c in chunks)
    assert all("Particulars | 2025" in c["text"] for c in chunks)
    assert sum(c["text"].count("Line item") for c in chunks) == 200


def test_embed_text_does_not_repeat_heading():
    assert embed_text({"section": "Overview", "text": "Overview\nBody"}) == "Overview\nBody"
    assert embed_text({"section": None, "text": "Body"}) == "Body"


def test_every_column_is_labelled_with_its_group():
    # Infosys/TCS layout: the group name appears only on each group's first column.
    table = {
        **TABLE,
        "rows": [
            ["Particulars", "Standalone 2025", "2024", "Consolidated 2025", "2024"],
            ["Revenue from operations", "1,36,592", "1,28,933", "1,62,990", "1,53,670"],
        ],
    }
    (chunk,) = table_chunks(table)
    assert (
        "Particulars | Standalone 2025 | Standalone 2024 | Consolidated 2025 | Consolidated 2024"
        in chunk["text"]
    )
