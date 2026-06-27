"""Shared test fixtures."""

import os
import tempfile
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _test_env(tmp_path, monkeypatch):
    """Set up isolated test environment."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-for-mocking")
    monkeypatch.setenv("SQLITE_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("CHROMA_PERSIST_DIR", str(tmp_path / "chroma"))
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("QLIB_DATA_PATH", str(tmp_path / "qlib_data"))
    yield
