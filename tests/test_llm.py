from types import SimpleNamespace

from app.llm import LLM


class FakeClient:
    """Stands in for groq.Groq: records calls, returns a fixed reply."""

    def __init__(self, reply="Revenue was ₹2,55,324 crore [1]."):
        self.calls = 0
        self.reply = reply
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls += 1
        assert kwargs["temperature"] == 0
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.reply))],
            usage=SimpleNamespace(prompt_tokens=100, completion_tokens=20),
        )


def test_second_identical_call_comes_from_cache(tmp_path):
    client = FakeClient()
    llm = LLM(client=client, model="test-model", cache_dir=tmp_path)
    first = llm.complete("system", "user")
    second = llm.complete("system", "user")
    assert client.calls == 1
    assert not first.cached and second.cached
    assert second.text == first.text and second.input_tokens == 100


def test_different_prompt_or_model_is_not_cached(tmp_path):
    client = FakeClient()
    LLM(client=client, model="a", cache_dir=tmp_path).complete("s", "u1")
    LLM(client=client, model="a", cache_dir=tmp_path).complete("s", "u2")
    LLM(client=client, model="b", cache_dir=tmp_path).complete("s", "u1")
    assert client.calls == 3


def test_retry_after_parsing():
    from app.llm import retry_after_seconds

    assert retry_after_seconds("Please try again in 8m40.128s. Need more") == 520.128
    assert retry_after_seconds("try again in 12.5s") == 12.5
    assert retry_after_seconds("try again in 1h2m3s") == 3723
    assert retry_after_seconds("no hint here") == 30.0


def test_rate_limit_is_retried(tmp_path, monkeypatch):
    import app.llm as llm_mod

    class RateLimited(Exception):
        status_code = 429

    client = FakeClient()
    real = client._create
    failures = iter([RateLimited("Please try again in 1.5s")])

    def flaky(**kw):
        for e in failures:
            raise e
        return real(**kw)

    client.chat.completions.create = flaky
    slept = []
    monkeypatch.setattr(llm_mod.time, "sleep", slept.append)
    out = LLM(client=client, model="m", cache_dir=tmp_path).complete("s", "u")
    assert out.text and slept == [3.5]


class FakeAnthropic:
    """Stands in for anthropic.Anthropic."""

    def __init__(self):
        self.calls = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        assert "temperature" not in kwargs  # current Claude models reject it
        return SimpleNamespace(
            content=[SimpleNamespace(type="thinking"), SimpleNamespace(type="text", text="ok [1]")],
            usage=SimpleNamespace(input_tokens=90, output_tokens=10),
        )


def _always_rate_limited(wait="9m30s"):
    class TPDLimit(Exception):
        status_code = 429

    def create(**kw):
        raise TPDLimit(f"Please try again in {wait}")

    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def test_long_rate_limit_falls_back_and_records_model(tmp_path, monkeypatch):
    import app.llm as llm_mod

    monkeypatch.setattr(llm_mod.time, "sleep", lambda s: (_ for _ in ()).throw(AssertionError))
    fb = FakeAnthropic()
    llm = LLM(
        client=_always_rate_limited(),
        model="m",
        cache_dir=tmp_path,
        fallback_client=fb,
        fallback_model="claude-test",
    )
    out = llm.complete("s", "u")
    assert out.text == "ok [1]" and out.model == "claude-test" and not out.cached
    again = llm.complete("s", "u")  # served from the fallback's cache entry
    assert again.cached and again.model == "claude-test" and len(fb.calls) == 1


def test_short_rate_limit_waits_instead_of_falling_back(tmp_path, monkeypatch):
    import app.llm as llm_mod

    slept = []
    monkeypatch.setattr(llm_mod.time, "sleep", slept.append)
    client = FakeClient()
    real = client._create
    failures = iter([type("E", (Exception,), {"status_code": 429})("try again in 5s")])

    def flaky(**kw):
        for e in failures:
            raise e
        return real(**kw)

    client.chat.completions.create = flaky
    fb = FakeAnthropic()
    out = LLM(
        client=client, model="m", cache_dir=tmp_path, fallback_client=fb, fallback_model="c"
    ).complete("s", "u")
    assert out.model == "m" and slept == [7] and fb.calls == []
