"""Groq chat completions with an on-disk response cache and an optional Anthropic fallback.

The cache key is (model, system prompt, user prompt), so re-running evals on unchanged
questions and retrieval costs nothing. Temperature is 0 so cached answers are representative.

When Groq is rate-limited for longer than `fallback_after_s` (the free-tier daily token cap)
and ANTHROPIC_API_KEY is set, the call goes to `fallback_model` instead. `Completion.model`
records which model answered, so eval reports can say so.
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


class RateLimited(Exception):
    """Groq asked us to wait longer than we want to, and a fallback model is available."""

    def __init__(self, wait_s: float):
        super().__init__(f"rate-limited for {wait_s:.0f}s")
        self.wait_s = wait_s


@dataclass
class Completion:
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_s: float  # time of the original (uncached) call
    cached: bool = False


class LLM:
    def __init__(
        self,
        client=None,
        model: str | None = None,
        cache_dir: Path | None = None,
        fallback_client=None,
        fallback_model: str | None = None,
        fallback_after_s: float = 60,
    ):
        s = get_settings()
        self.model = model or s.groq_model
        self.cache_dir = cache_dir if cache_dir is not None else s.llm_cache_dir
        self._client = client  # injected in tests; created lazily otherwise
        # Only the default generator falls back; an explicit model (e.g. the eval judge) waits.
        if fallback_model is None and model is None and s.anthropic_api_key:
            fallback_model = s.anthropic_model
        self.fallback_model = fallback_model
        self.fallback_after_s = fallback_after_s
        self._fallback_client = fallback_client

    @property
    def fallback_client(self):
        if self._fallback_client is None:
            import anthropic  # only needed when falling back

            self._fallback_client = anthropic.Anthropic(api_key=get_settings().anthropic_api_key)
        return self._fallback_client

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
        """Retry on HTTP 429, waiting as long as Groq's "try again in 8m40s" says (capped).

        With a fallback model configured, a wait longer than `fallback_after_s` raises
        RateLimited instead.
        """
        for attempt in range(attempts):
            try:
                return self.client.chat.completions.create(**kwargs)
            except Exception as e:  # noqa: BLE001 - groq.RateLimitError, without importing groq
                if getattr(e, "status_code", None) != 429:
                    raise
                wait = retry_after_seconds(str(e))
                if self.fallback_model and wait > self.fallback_after_s:
                    raise RateLimited(wait) from e
                if wait > max_wait_s or attempt == attempts - 1:
                    raise
                time.sleep(wait + 2)
        raise AssertionError("unreachable")

    def _complete_fallback(self, system: str, user: str) -> Completion:
        start = time.perf_counter()
        resp = self.fallback_client.messages.create(
            model=self.fallback_model,
            # Thinking counts toward max_tokens; low effort keeps it short. No temperature:
            # current Claude models reject non-default sampling parameters.
            max_tokens=8000,
            output_config={"effort": "low"},
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return Completion(
            text="".join(b.text for b in resp.content if b.type == "text"),
            model=self.fallback_model,
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
            latency_s=round(time.perf_counter() - start, 3),
        )

    def _cache_path(self, system: str, user: str, model: str | None = None) -> Path:
        key = [model or self.model, system, user]
        h = hashlib.sha256(json.dumps(key).encode()).hexdigest()
        return self.cache_dir / f"{h}.json"

    def _save(self, path: Path, result: Completion) -> Completion:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(result)), encoding="utf-8")
        return result

    def complete(self, system: str, user: str, max_tokens: int = 1500) -> Completion:
        path = self._cache_path(system, user)
        paths = [path]
        if self.fallback_model:
            paths.append(self._cache_path(system, user, self.fallback_model))
        for p in paths:
            if p.exists():
                return Completion(**{**json.loads(p.read_text(encoding="utf-8")), "cached": True})

        extra = {}
        if self.model.startswith("openai/gpt-oss"):
            # Reasoning model: its hidden reasoning counts toward max_tokens, so keep it short.
            extra["reasoning_effort"] = "low"
        start = time.perf_counter()
        try:
            resp = self._create_with_retry(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0,
                max_tokens=max_tokens,
                **extra,
            )
        except RateLimited:
            return self._save(paths[1], self._complete_fallback(system, user))
        result = Completion(
            text=resp.choices[0].message.content or "",
            model=self.model,
            input_tokens=resp.usage.prompt_tokens,
            output_tokens=resp.usage.completion_tokens,
            latency_s=round(time.perf_counter() - start, 3),
        )
        return self._save(path, result)
