"""Tests for SessionStore — written BEFORE implementation (TDD)."""

import pytest

from src.core.session_store import SessionStore
from src.exceptions import SessionNotFoundError


class TestSessionStore:
    """Test SessionStore CRUD operations."""

    def test_create_session(self, store):
        result = store.create(name="测试会话")
        assert result["status"] == "created"
        assert "session_id" in result

    def test_load_session(self, store):
        created = store.create(name="test")
        loaded = store.load(created["session_id"])
        assert loaded["status"] == "loaded"
        assert loaded["name"] == "test"

    def test_load_not_found(self, store):
        with pytest.raises(SessionNotFoundError):
            store.load("nonexistent")

    def test_list_sessions(self, store):
        store.create(name="s1")
        store.create(name="s2")
        sessions = store.list_active()
        assert len(sessions) == 2

    def test_update_strategy(self, store):
        created = store.create(name="test")
        store.update_current_strategy(created["session_id"], "strat_001")
        loaded = store.load(created["session_id"])
        assert loaded["current_strategy_id"] == "strat_001"

    def test_update_backtest(self, store):
        created = store.create(name="test")
        store.update_current_backtest(created["session_id"], "bt_001")
        loaded = store.load(created["session_id"])
        assert loaded["current_backtest_id"] == "bt_001"

    def test_delete_session(self, store):
        created = store.create(name="test")
        store.delete(created["session_id"])
        sessions = store.list_active()
        assert len(sessions) == 0

    def test_list_only_active(self, store):
        s1 = store.create(name="active")
        store.create(name="deleted")
        store.delete(s1["session_id"])
        sessions = store.list_active()
        assert len(sessions) == 1
        assert sessions[0]["name"] == "deleted"


@pytest.fixture
def store(tmp_path):
    return SessionStore(db_path=str(tmp_path / "sessions.db"))
