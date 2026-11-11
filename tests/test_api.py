"""API tests with a fake answerer and database check: no models, database or keys needed."""

from fastapi.testclient import TestClient

from app.api import app, get_answerer, get_db_check
from app.llm import Completion
from app.rag import Answer, Citation

client = TestClient(app)


def fake_answer(question: str) -> Answer:
    return Answer(
        question=question,
        text="TCS's revenue was ₹2,55,324 crore [1].",
        citations=[Citation(1, "tcs", 2025, 112)],
        refused=False,
        completion=Completion("TCS revenue...", "openai/gpt-oss-20b", 900, 40, 1.2, cached=True),
    )


def setup_function():
    app.dependency_overrides.clear()


def test_ask_returns_answer_with_citations():
    app.dependency_overrides[get_answerer] = lambda: fake_answer
    r = client.post("/ask", json={"question": "  What was TCS's revenue in FY2025?  "})
    assert r.status_code == 200
    body = r.json()
    assert body["question"] == "What was TCS's revenue in FY2025?"  # stripped
    assert body["citations"] == [
        {"n": 1, "company": "tcs", "company_name": "TCS", "fiscal_year": 2025, "page": 112}
    ]
    assert body["model"] == "openai/gpt-oss-20b" and body["cached"] is True
    assert body["refused"] is False and "Not investment advice" in body["disclaimer"]


def test_refusal_without_llm_has_no_model():
    app.dependency_overrides[get_answerer] = lambda: lambda q: Answer(q, "Out of scope.", [], True)
    body = client.post("/ask", json={"question": "Should I buy Infosys shares?"}).json()
    assert body["refused"] is True and body["model"] is None and body["citations"] == []


def test_question_length_is_validated():
    app.dependency_overrides[get_answerer] = lambda: fake_answer
    assert client.post("/ask", json={"question": "hi"}).status_code == 422
    assert client.post("/ask", json={"question": "x" * 501}).status_code == 422


def test_answer_errors_do_not_leak_details():
    def boom(q):
        raise RuntimeError("GROQ_API_KEY=secret-value")

    app.dependency_overrides[get_answerer] = lambda: boom
    r = client.post("/ask", json={"question": "What was TCS's revenue?"})
    assert r.status_code == 503 and "secret" not in r.text


def test_health_ok_and_down():
    app.dependency_overrides[get_db_check] = lambda: lambda: None
    assert client.get("/health").json() == {"status": "ok", "db": "ok"}

    def down():
        raise ConnectionError("refused")

    app.dependency_overrides[get_db_check] = lambda: down
    assert client.get("/health").status_code == 503
