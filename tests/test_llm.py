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
