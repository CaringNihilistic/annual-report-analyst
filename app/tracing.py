"""Optional Langfuse tracing: one trace per question, with the retrieval and LLM steps inside.

Off unless both are true:
  1. the entry point calls `enable()` (the web app and `python -m app.ask` do; evals don't,
     so eval runs stay offline and repeatable), and
  2. LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are set (LANGFUSE_BASE_URL picks the region).

When off, `observe()` yields a do-nothing object and the langfuse package is never imported,
so tests need no network. Tracing must never break an answer: errors from Langfuse itself
are logged and swallowed, while errors from the traced code pass through unchanged.
"""

import logging
from contextlib import contextmanager
from functools import lru_cache

from app.config import get_settings

log = logging.getLogger(__name__)
_enabled = False


def enable() -> None:
    global _enabled
    _enabled = True


class _Quiet:
    """Wraps an observation so that a failing `update` can't fail the request."""

    def __init__(self, obs=None):
        self._obs = obs

    def update(self, **fields) -> None:
        if self._obs is None:
            return
        try:
            self._obs.update(**fields)
        except Exception as e:  # noqa: BLE001 - tracing is best effort
            log.warning("langfuse update failed: %s", e)


@lru_cache
def _client():
    s = get_settings()
    if not (s.langfuse_public_key and s.langfuse_secret_key):
        return None
    try:
        from langfuse import Langfuse

        return Langfuse(
            public_key=s.langfuse_public_key,
            secret_key=s.langfuse_secret_key,
            base_url=s.langfuse_base_url,
        )
    except Exception as e:  # noqa: BLE001 - no tracing is better than no answers
        log.warning("langfuse disabled: %s", e)
        return None


def client():
    """The Langfuse client, or None when tracing is off."""
    return _client() if _enabled else None


@contextmanager
def observe(name: str, as_type: str = "span", **fields):
    """Record the enclosed block as a Langfuse observation (span, generation, retriever...).

    Observations opened inside another one nest under it, so the trace mirrors the call tree.
    """
    lf = client()
    if lf is None:
        yield _Quiet()
        return
    try:
        cm = lf.start_as_current_observation(name=name, as_type=as_type, **fields)
        obs = cm.__enter__()
    except Exception as e:  # noqa: BLE001
        log.warning("langfuse observation failed: %s", e)
        yield _Quiet()
        return
    try:
        yield _Quiet(obs)
    except BaseException as e:
        _Quiet(obs).update(level="ERROR", status_message=type(e).__name__)
        _exit(cm, type(e), e, e.__traceback__)
        raise
    _exit(cm, None, None, None)


def _exit(cm, *exc) -> None:
    try:
        cm.__exit__(*exc)
    except Exception as e:  # noqa: BLE001
        log.warning("langfuse close failed: %s", e)


def flush() -> None:
    """Send queued traces now (the SDK also does this on normal exit)."""
    lf = client()
    if lf is not None:
        try:
            lf.flush()
        except Exception as e:  # noqa: BLE001
            log.warning("langfuse flush failed: %s", e)


def traced_answer(agent, question: str):
    """Run the agent on one question as the root of a trace (route, answer, citations)."""
    from app.agent.router import plan  # pure rules; imported here to keep this module light

    with observe("ask", as_type="agent", input=question) as root:
        a = agent(question)
        root.update(
            output={
                "answer": a.text,
                "citations": [f"{c.company} FY{c.fiscal_year} p.{c.page}" for c in a.citations],
                "refused": a.refused,
            },
            metadata={
                "route": plan(question).route,
                "model": a.completion.model if a.completion else None,
                "cached": bool(a.completion and a.completion.cached),
            },
        )
        return a
