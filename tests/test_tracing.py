"""Tracing is optional and must never change or break an answer."""

import sys

import pytest

from app import tracing
from app.rag import Answer, Citation


class FakeObs:
    def __init__(self, log, name, fields):
        self.log, self.name = log, name
        log.append(("start", name, fields))

    def update(self, **fields):
        self.log.append(("update", self.name, fields))


class FakeCM:
    def __init__(self, log, name, fields):
        self.log, self.name, self.fields = log, name, fields

    def __enter__(self):
        return FakeObs(self.log, self.name, self.fields)

    def __exit__(self, *exc):
        self.log.append(("end", self.name, exc[0]))
        return False


class FakeLangfuse:
    def __init__(self):
        self.log = []

    def start_as_current_observation(self, name, **fields):
        return FakeCM(self.log, name, fields)

    def flush(self):
        self.log.append(("flush",))


@pytest.fixture
def fake(monkeypatch):
    lf = FakeLangfuse()
    monkeypatch.setattr(tracing, "_enabled", True)
    monkeypatch.setattr(tracing, "_client", lambda: lf)
    return lf


def test_off_by_default_is_a_no_op_and_never_imports_langfuse(monkeypatch):
    monkeypatch.delitem(sys.modules, "langfuse", raising=False)
    with tracing.observe("x", input="q") as obs:
        obs.update(output="anything")
    tracing.flush()
    assert tracing.client() is None
    assert "langfuse" not in sys.modules


def test_enabled_without_keys_stays_off(monkeypatch):
    monkeypatch.setattr(tracing, "_enabled", True)
    tracing._client.cache_clear()
    monkeypatch.setattr(
        tracing, "get_settings", lambda: type("S", (), {"langfuse_public_key": ""})()
    )
    assert tracing.client() is None
    tracing._client.cache_clear()


def test_traced_answer_records_question_answer_and_citations(fake):
    a = Answer("q", "Revenue was ₹1 crore [1].", [Citation(1, "tcs", 2025, 7)], False)
    q = "What was TCS revenue in FY2025?"
    assert tracing.traced_answer(lambda _: a, q) is a
    start, update, end = fake.log
    assert start == ("start", "ask", {"as_type": "agent", "input": q})
    assert update[2]["output"]["citations"] == ["tcs FY2025 p.7"]
    assert update[2]["metadata"]["route"] == "metrics"
    assert end == ("end", "ask", None)


def test_errors_in_traced_code_pass_through_and_are_marked(fake):
    with pytest.raises(ValueError), tracing.observe("llm", as_type="generation"):
        raise ValueError("boom")
    assert ("update", "llm", {"level": "ERROR", "status_message": "ValueError"}) in fake.log
    assert fake.log[-1] == ("end", "llm", ValueError)


def test_a_broken_langfuse_never_breaks_the_answer(monkeypatch):
    class Broken:
        def start_as_current_observation(self, **kw):
            raise ConnectionError("langfuse down")

    monkeypatch.setattr(tracing, "_enabled", True)
    monkeypatch.setattr(tracing, "_client", lambda: Broken())
    with tracing.observe("x") as obs:
        obs.update(output="still fine")
        result = 42
    assert result == 42


def test_llm_call_is_recorded_as_a_generation(fake, tmp_path):
    from app.llm import LLM

    class Resp:
        choices = [type("C", (), {"message": type("M", (), {"content": "hi"})()})()]
        usage = type("U", (), {"prompt_tokens": 3, "completion_tokens": 1})()

    client = type("G", (), {})()
    client.chat = type("Ch", (), {})()
    client.chat.completions = type("Co", (), {"create": staticmethod(lambda **kw: Resp())})()
    LLM(client=client, model="m", cache_dir=tmp_path).complete("sys", "user")
    start, update, _ = fake.log
    assert start[2]["as_type"] == "generation"
    assert update[2]["model"] == "m" and update[2]["usage_details"] == {
        "input_tokens": 3,
        "output_tokens": 1,
    }
