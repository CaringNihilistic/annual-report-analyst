from ingest.index import build_rows


def fake_embed(texts):
    return [[float(len(t))] * 3 for t in texts]


def test_build_rows_without_network_or_db():
    doc = {
        "company": "tcs",
        "fiscal_year": 2025,
        "chunks": [
            {"page": 3, "section": "Chairman's letter", "text": "Hello"},
            {"page": 4, "section": None, "text": "World!"},
        ],
        "tables": [
            {
                "page": 150,
                "section": "Consolidated Statement of Profit and Loss",
                "caption": None,
                "context": "(₹ crore)",
                "rows": [["Particulars", "FY 2024-25"], ["Revenue from operations", "2,55,324"]],
            }
        ],
    }
    chunks, metrics = build_rows(doc, fake_embed)

    assert [(c.page, c.text, c.embedding) for c in chunks] == [
        (3, "Hello", [5.0] * 3),
        (4, "World!", [6.0] * 3),
    ]
    assert all(c.company == "tcs" and c.fiscal_year == 2025 for c in chunks)
    (m,) = metrics
    assert (m.metric, m.value, m.unit, m.currency, m.source_page) == (
        "revenue",
        255324.0,
        "crore",
        "INR",
        150,
    )
