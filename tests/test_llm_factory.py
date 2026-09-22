"""Tests for LLM protocol resolution and per-preset protocol storage.

Regression target: the wire protocol was inferred from the base URL alone, so a
self-hosted gateway was routed onto whichever SDK its URL happened to resemble
("anthropic" anywhere in the host won). Two follow-on traps are pinned here as
well: a preset that stores no protocol must still behave exactly as before, and
the agent's LLM cache — keyed on model/key/url — must notice a protocol-only
switch, otherwise the change silently does nothing.
"""

import sqlite3

import pytest
from pydantic import ValidationError

from src.core.models import LLMConfig
from src.core.settings_store import SettingsStore
from src.llm_factory import _detect_protocol, _resolve_protocol, create_llm

#: ``llm_presets`` as it was created before the ``protocol`` column existed.
LEGACY_SCHEMA = """
    CREATE TABLE llm_presets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        label TEXT NOT NULL DEFAULT '',
        api_key TEXT DEFAULT '',
        base_url TEXT DEFAULT '',
        model TEXT DEFAULT '',
        is_active INTEGER DEFAULT 0
    );
"""


# ── Protocol resolution ────────────────────────────────────────────


@pytest.mark.parametrize(
    ("base_url", "expected"),
    [
        ("", "openai"),
        ("https://api.deepseek.com", "openai"),
        ("https://api.openai.com/v1", "openai"),
        ("https://gw.internal/v1", "openai"),
        ("https://api.deepseek.com/anthropic", "anthropic"),
        # Matched by the host-name rule, not by a "/anthropic" path.
        ("https://api.anthropic.com", "anthropic"),
        # The misfire that motivated the explicit field: a gateway whose *name*
        # looks like an Anthropic proxy is forced onto the Anthropic SDK.
        ("https://anthropic-proxy.internal/v1", "anthropic"),
    ],
)
def test_detect_protocol_heuristic(base_url, expected):
    assert _detect_protocol(base_url) == expected


@pytest.mark.parametrize(
    ("protocol", "base_url", "expected"),
    [
        # Each URL below would be inferred as the *opposite* protocol, so a
        # pass proves the explicit choice actually wins.
        ("anthropic", "https://gw.internal/v1", "anthropic"),
        ("openai", "https://anthropic-proxy.internal/v1", "openai"),
        ("openai", "https://api.anthropic.com", "openai"),
        # "auto" (and anything unrecognised) falls back to the heuristic.
        ("auto", "https://api.deepseek.com/anthropic", "anthropic"),
        ("auto", "https://gw.internal/v1", "openai"),
        ("", "https://api.deepseek.com/anthropic", "anthropic"),
    ],
)
def test_resolve_protocol(protocol, base_url, expected):
    assert _resolve_protocol(protocol, base_url) == expected


def test_create_llm_uses_the_pinned_protocol():
    """One base URL, two protocols → two different client classes."""
    base_url = "https://gw.internal.invalid/v1"
    as_openai = create_llm(LLMConfig(base_url=base_url, api_key="k", model="m", protocol="openai"))
    as_anthropic = create_llm(LLMConfig(base_url=base_url, api_key="k", model="m", protocol="anthropic"))

    assert type(as_openai).__name__ == "ChatOpenAI"
    assert type(as_anthropic).__name__ == "ChatAnthropic"


# ── Persistence ────────────────────────────────────────────────────


def test_preset_protocol_roundtrip(tmp_path):
    store = SettingsStore(db_path=str(tmp_path / "p.db"))
    try:
        preset_id = store.add_preset(
            label="自建网关",
            base_url="https://gw.internal/v1",
            api_key="k",
            model="m",
            protocol="anthropic",
        )
        store.activate_preset(preset_id)

        assert store.get_active_config()["protocol"] == "anthropic"
        assert store.list_presets()[0]["protocol"] == "anthropic"
    finally:
        store.close()


def test_add_preset_defaults_to_auto(tmp_path):
    """Callers that omit the protocol keep the old infer-from-URL behaviour."""
    store = SettingsStore(db_path=str(tmp_path / "p.db"))
    try:
        preset_id = store.add_preset(label="x", base_url="u", api_key="k", model="m")
        store.activate_preset(preset_id)
        assert store.get_active_config()["protocol"] == "auto"
    finally:
        store.close()


def test_existing_presets_migrate_to_auto(tmp_path):
    """A database created before the column exists must keep working."""
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(LEGACY_SCHEMA)
    conn.execute(
        "INSERT INTO llm_presets (label, api_key, base_url, model, is_active)"
        " VALUES ('legacy', 'k', 'https://gw.internal/v1', 'm', 1)"
    )
    conn.commit()
    conn.close()

    store = SettingsStore(db_path=str(db_path))
    try:
        assert store.get_active_config()["protocol"] == "auto"
        assert store.list_presets()[0]["protocol"] == "auto"
    finally:
        store.close()


# ── The two follow-on traps ────────────────────────────────────────


def test_llm_cache_key_includes_protocol(tmp_path, monkeypatch):
    """Two presets differing only in protocol must not share a cache entry.

    Without the protocol in the key, switching to the second preset would reuse
    the first preset's client and the switch would appear to do nothing.
    """
    from src.agent.graph import _llm_config_key

    store = SettingsStore(db_path=str(tmp_path / "p.db"))
    try:
        class _Services:
            pass

        services = _Services()
        services.settings_store = store
        monkeypatch.setattr("src.api.dependencies.get_services", lambda: services)

        common = {
            "base_url": "https://gw.internal/v1",
            "api_key": "k",
            "model": "m",
        }
        first = store.add_preset(label="a", protocol="openai", **common)
        store.activate_preset(first)
        openai_key = _llm_config_key()

        second = store.add_preset(label="b", protocol="anthropic", **common)
        store.activate_preset(second)
        anthropic_key = _llm_config_key()

        assert openai_key != anthropic_key
        # Membership, not position: the key later gained a headers element, and
        # a positional assertion would have silently stopped testing protocol.
        assert "openai" in openai_key
        assert "anthropic" in anthropic_key
    finally:
        store.close()


def test_create_llm_takes_the_protocol_from_the_active_preset(tmp_path, monkeypatch):
    """The production path: no override, so the stored preset decides."""
    store = SettingsStore(db_path=str(tmp_path / "p.db"))
    try:
        class _Services:
            pass

        services = _Services()
        services.settings_store = store
        monkeypatch.setattr("src.api.dependencies.get_services", lambda: services)

        preset_id = store.add_preset(
            label="gw",
            base_url="https://gw.internal.invalid/v1",
            api_key="k",
            model="m",
            protocol="anthropic",
        )
        store.activate_preset(preset_id)

        assert type(create_llm()).__name__ == "ChatAnthropic"
    finally:
        store.close()


def test_preset_payload_constrains_protocol():
    """A typo must be rejected instead of silently degrading to URL guessing."""
    from src.api.routes.settings import PresetCreate

    assert PresetCreate(label="x", base_url="u", api_key="k", model="m").protocol == "auto"
    with pytest.raises(ValidationError):
        PresetCreate(label="x", base_url="u", api_key="k", model="m", protocol="Antropic")
