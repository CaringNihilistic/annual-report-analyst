"""Groq chat completions with an on-disk response cache.

The cache key is (model, system prompt, user prompt), so re-running evals on unchanged
questions and retrieval costs nothing. Temperature is 0 so cached answers are representative.
"""

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from app.config import get_settings


@dataclass
class Completion:
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_s: float  # time of the original (uncached) call
    cached: bool = False


class LLM:
    def __init__(self, client=None, model: str | None = None, cache_dir: Path | None = None):
        s = get_settings()
        self.model = model or s.groq_model
        self.cache_dir = cache_dir if cache_dir is not None else s.llm_cache_dir
        self._client = client  # injected in tests; created lazily otherwise

    @property
    def client(self):
        if self._client is None:
            from groq import Groq  # only needed for real calls

            key = get_settings().groq_api_key
            if not key:
                raise RuntimeError("GROQ_API_KEY is not set. Add it to .env (see .env.example).")
            self._client = Groq(api_key=key)
        return self._client

    def _cache_path(self, system: str, user: str) -> Path:
        h = hashlib.sha256(json.dumps([self.model, system, user]).encode()).hexdigest()
        return self.cache_dir / f"{h}.json"

    def complete(self, system: str, user: str, max_tokens: int = 1500) -> Completion:
        path = self._cache_path(system, user)
        if path.exists():
            return Completion(**{**json.loads(path.read_text(encoding="utf-8")), "cached": True})

        extra = {}
        if self.model.startswith("openai/gpt-oss"):
            # Reasoning model: its hidden reasoning counts toward max_tokens, so keep it short.
            extra["reasoning_effort"] = "low"
        start = time.perf_counter()
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0,
            max_tokens=max_tokens,
            **extra,
        )
        result = Completion(
            text=resp.choices[0].message.content or "",
            model=self.model,
            input_tokens=resp.usage.prompt_tokens,
            output_tokens=resp.usage.completion_tokens,
            latency_s=round(time.perf_counter() - start, 3),
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(result)), encoding="utf-8")
        return result
