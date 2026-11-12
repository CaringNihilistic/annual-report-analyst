"""Shared test setup: unit tests never send traces, even if .env holds Langfuse keys."""

import pytest

from app import tracing


@pytest.fixture(autouse=True)
def _no_tracing(monkeypatch):
    monkeypatch.setattr(tracing, "_enabled", False)
