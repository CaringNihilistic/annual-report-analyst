"""Groq chat completions with an on-disk response cache.

The cache key is (model, system prompt, user prompt), so re-running evals on unchanged
questions and retrieval costs nothing. Temperature is 0 so cached answers are representative.
"""

import hashlib
import json
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from app.config import get_settings


def retry_after_seconds(message: str, default: float = 30.0) -> float:
    """'Please try again in 8m40.128s' -> 520.128. Also handles '12.5s' and '1h2m3s'."""
    m = re.search(r"try again in ((?:\d+h)?(?:\d+m)?(?:[\d.]+s)?)", message)
    if not m or not m[1]:
        return default
    parts = {unit: value for value, unit in re.findall(r"([\d.]+)([hms])", m[1])}
    return (
        float(parts.get("h", 0)) * 3600 + float(parts.get("m", 0)) * 60 + float(parts.get("s", 0))
    )


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

    def _create_with_retry(self, max_wait_s: float = 3600, attempts: int = 12, **kwargs):
        """Retry on HTTP 429, waiting as long as Groq's "try again in 8m40s" says (capped)."""
        for attempt in range(attempts):
            try:
                return self.client.chat.completions.create(**kwargs)
            except Exception as e:  # noqa: BLE001 - groq.RateLimitError, without importing groq
                if getattr(e, "status_code", None) != 429 or attempt == attempts - 1:
                    raise
                wait = retry_after_seconds(str(e))
                if wait > max_wait_s:
                    raise
                time.sleep(wait + 2)
        raise AssertionError("unreachable")

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
        resp = self._create_with_retry(
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
