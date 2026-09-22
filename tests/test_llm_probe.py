"""Tests for per-preset custom headers and the connection probe.

Two things are pinned here that a shallow test would miss.

First, headers must survive all the way onto the wire. A gateway like OpenCode
Go answers 400 unless ``x-opencode-session`` is present, so "we stored the
string" is not the interesting claim — the interesting claim is that the HTTP
request carries it, which is asserted against a captured request.

Second, the probe must not report a false pass. ``create_llm()`` silently falls
back to the ``.env`` configuration when base URL, key or model is empty, so an
incomplete form would otherwise probe the .env config and come back green.
"""

import json

import httpx
import httpx2
import pytest

from src.core.llm_probe import probe_llm_config
from src.core.models import LLMConfig
from src.core.settings_store import SettingsStore
from src.llm_factory import create_llm

#: ``llm_presets`` as created before the protocol/headers columns existed.
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


def _openai_sse() -> str:
    """A minimal OpenAI-compatible SSE stream, sentinel included."""
    chunks = [
        {"id": "c1", "object": "chat.completion.chunk", "created": 0, "model": "probe",
         "choices": [{"index": 0, "delta": {"role": "assistant", "content": "ok"},
                      "finish_reason": None}]},
        {"id": "c1", "object": "chat.completion.chunk", "created": 0, "model": "probe",
         "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
    ]
    body = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks)
    return body + "data: [DONE]\n\n"


def _anthropic_sse() -> str:
    """A minimal Anthropic SSE stream: start, one text delta, stop."""
    events = [
        ("message_start", {"type": "message_start", "message": {
            "id": "m1", "type": "message", "role": "assistant", "model": "probe",
            "content": [], "stop_reason": None,
            "usage": {"input_tokens": 1, "output_tokens": 1}}}),
        ("content_block_start", {"type": "content_block_start", "index": 0,
                                 "content_block": {"type": "text", "text": ""}}),
        ("content_block_delta", {"type": "content_block_delta", "index": 0,
                                 "delta": {"type": "text_delta", "text": "ok"}}),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        ("message_delta", {"type": "message_delta",
                           "delta": {"stop_reason": "end_turn"},
                           "usage": {"output_tokens": 1}}),
        ("message_stop", {"type": "message_stop"}),
    ]
    return "".join(f"event: {name}\ndata: {json.dumps(payload)}\n\n" for name, payload in events)


@pytest.fixture
def captured(monkeypatch):
    """Capture outgoing HTTP requests instead of performing them.

    ``create_llm()`` builds every client with ``streaming=True``, so the
    responses have to be SSE streams; a plain JSON body makes the client
    parse zero chunks and raise. The anthropic SDK goes through ``httpx2``
    while the openai SDK uses ``httpx``, so both are patched — that split is
    easy to miss and would silently make one protocol's assertions vacuous.
    """
    requests: list[httpx.Request] = []

    def fake_send(self, request, **kwargs):
        requests.append(request)
        is_anthropic = "/messages" in str(request.url)
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_anthropic_sse() if is_anthropic else _openai_sse(),
            request=request,
        )

    monkeypatch.setattr(httpx.Client, "send", fake_send)
    monkeypatch.setattr(httpx2.Client, "send", fake_send)
    return requests


# ── Headers reach the wire ─────────────────────────────────────────


@pytest.mark.parametrize("protocol", ["openai", "anthropic"])
def test_custom_headers_are_sent(protocol, captured):
    headers = {"x-opencode-session": "aifund5", "X-Trace": "t1"}
    llm = create_llm(
        LLMConfig(
            base_url="https://gw.internal.invalid/v1",
            api_key="k",
            model="m",
            protocol=protocol,
            headers=headers,
        )
    )
    llm.invoke("hi")

    sent = {k.lower(): v for k, v in captured[-1].headers.items()}
    assert sent["x-opencode-session"] == "aifund5"
    assert sent["x-trace"] == "t1"


@pytest.mark.parametrize(
    ("protocol", "auth_header"),
    [("openai", "authorization"), ("anthropic", "x-api-key")],
)
def test_custom_headers_do_not_replace_auth(protocol, auth_header, captured):
    """A gateway header must ride alongside authentication, not clobber it."""
    llm = create_llm(
        LLMConfig(
            base_url="https://gw.internal.invalid/v1",
            api_key="secret-key",
            model="m",
            protocol=protocol,
            headers={"x-opencode-session": "s"},
        )
    )
    llm.invoke("hi")

    sent = {k.lower(): v for k, v in captured[-1].headers.items()}
    assert "secret-key" in sent[auth_header]


def test_absent_headers_add_nothing(captured):
    """Existing presets keep sending exactly what they sent before."""
    llm = create_llm(
        LLMConfig(base_url="https://gw.internal.invalid/v1", api_key="k", model="m")
    )
    llm.invoke("hi")

    sent = {k.lower() for k in captured[-1].headers}
    assert "x-opencode-session" not in sent


# ── Persistence and migration ──────────────────────────────────────


def test_headers_roundtrip(tmp_path):
    store = SettingsStore(db_path=str(tmp_path / "p.db"))
    try:
        preset_id = store.add_preset(
            label="gw",
            base_url="https://gw.internal/v1",
            api_key="k",
            model="m",
            headers={"x-opencode-session": "aifund5"},
        )
        store.activate_preset(preset_id)

        assert store.get_active_config()["headers"] == {"x-opencode-session": "aifund5"}
        assert store.list_presets()[0]["headers"] == {"x-opencode-session": "aifund5"}
    finally:
        store.close()


def test_add_preset_without_headers_stores_empty(tmp_path):
    store = SettingsStore(db_path=str(tmp_path / "p.db"))
    try:
        preset_id = store.add_preset(label="x", base_url="u", api_key="k", model="m")
        store.activate_preset(preset_id)
        assert store.get_active_config()["headers"] == {}
    finally:
        store.close()


def test_legacy_database_migrates_both_columns(tmp_path):
    """A pre-existing database gains protocol *and* headers, unused by default."""
    import sqlite3

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
        config = store.get_active_config()
        assert config["protocol"] == "auto"
        assert config["headers"] == {}
    finally:
        store.close()


def test_corrupt_header_blob_degrades_to_empty(tmp_path):
    """One unreadable row must not take the settings page down."""
    store = SettingsStore(db_path=str(tmp_path / "p.db"))
    try:
        preset_id = store.add_preset(label="x", base_url="u", api_key="k", model="m")
        store._conn.execute(
            "UPDATE llm_presets SET headers = ? WHERE id = ?", ("not-json", preset_id)
        )
        store._conn.commit()
        store.activate_preset(preset_id)
        assert store.get_active_config()["headers"] == {}
    finally:
        store.close()


def test_llm_cache_key_includes_headers(tmp_path, monkeypatch):
    """Two presets differing only in headers must not share a cache entry."""
    from src.agent.graph import _llm_config_key

    store = SettingsStore(db_path=str(tmp_path / "p.db"))
    try:
        class _Services:
            pass

        services = _Services()
        services.settings_store = store
        monkeypatch.setattr("src.api.dependencies.get_services", lambda: services)

        common = {"base_url": "https://gw.internal/v1", "api_key": "k", "model": "m"}
        first = store.add_preset(label="a", headers={"x-opencode-session": "one"}, **common)
        store.activate_preset(first)
        first_key = _llm_config_key()

        second = store.add_preset(label="b", headers={"x-opencode-session": "two"}, **common)
        store.activate_preset(second)
        second_key = _llm_config_key()

        assert first_key != second_key
    finally:
        store.close()


# ── API boundary validation ────────────────────────────────────────


@pytest.mark.parametrize(
    "headers",
    [
        {"x-bad\nx-injected": "v"},  # CRLF in the name
        {"x-ok": "v\r\nX-Injected: evil"},  # CRLF in the value
        {"x bad": "v"},  # space is not an RFC 7230 token character
    ],
)
def test_preset_payload_rejects_header_injection(headers):
    from pydantic import ValidationError

    from src.api.routes.settings import PresetCreate

    with pytest.raises(ValidationError):
        PresetCreate(label="x", base_url="u", api_key="k", model="m", headers=headers)


def test_preset_payload_accepts_a_legal_header():
    from src.api.routes.settings import PresetCreate

    payload = PresetCreate(
        label="x",
        base_url="u",
        api_key="k",
        model="m",
        headers={"x-opencode-session": "aifund5"},
    )
    assert payload.headers == {"x-opencode-session": "aifund5"}


# ── Probe verdicts ─────────────────────────────────────────────────


def test_probe_reports_success_and_tool_calling(monkeypatch):
    """A tool call in the response is what makes the config usable here."""

    class _Chunk:
        def __init__(self, content="", tool_calls=None):
            self.content = content
            self.tool_calls = tool_calls or []

        def __add__(self, other):
            return _Chunk(
                self.content + other.content, self.tool_calls + other.tool_calls
            )

    class _FakeLlm:
        def bind_tools(self, tools):
            assert tools, "the probe must bind a tool"
            return self

        def stream(self, prompt):
            yield _Chunk("正在查询")

    monkeypatch.setattr("src.core.llm_probe.create_llm", lambda cfg: _FakeLlm())

    result = probe_llm_config(
        LLMConfig(base_url="https://gw/v1", api_key="k", model="m")
    )

    # The stub never emits a tool call, so this must NOT claim tool support.
    assert result["ok"] is True
    assert result["tool_calling"] is False
    assert result["stage"] == "ok"


def test_probe_classifies_http_failures(monkeypatch):
    class _Boom(Exception):
        def __init__(self, status):
            super().__init__(f"Error code: {status} - nope")
            self.status_code = status

    class _FakeLlm:
        def __init__(self, status):
            self._status = status

        def bind_tools(self, tools):
            return self

        def stream(self, prompt):
            raise _Boom(self._status)
            yield  # pragma: no cover — makes this a generator

    for status, stage in [(400, "request"), (401, "auth"), (402, "quota"), (404, "model")]:
        monkeypatch.setattr(
            "src.core.llm_probe.create_llm", lambda cfg, s=status: _FakeLlm(s)
        )
        result = probe_llm_config(
            LLMConfig(base_url="https://gw/v1", api_key="k", model="m")
        )
        assert result["ok"] is False, status
        assert result["stage"] == stage, status
        assert result["http_status"] == status
        assert result["hint"]


def test_probe_refuses_an_incomplete_config(monkeypatch):
    """An empty model must not silently probe the .env config and pass.

    ``create_llm()`` falls back to ``.env`` whenever base URL, key or model is
    empty, so without the guard the probe would report the .env setup's health
    as if it were the form's.
    """
    called = False

    def _explode(cfg):
        nonlocal called
        called = True
        raise AssertionError("create_llm must not be reached")

    monkeypatch.setattr("src.core.llm_probe.create_llm", _explode)

    result = probe_llm_config(
        LLMConfig(base_url="https://gw/v1", api_key="k", model="")
    )

    assert called is False
    assert result["ok"] is False
    assert result["stage"] == "config"
    assert "Model" in result["hint"]
