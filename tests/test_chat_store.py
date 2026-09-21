"""Tests for the chat history store.

The store is the source of truth behind the history page, so the two properties
that were quietly broken are pinned here: timestamps must be unambiguous
ISO-8601 UTC (a bare ``datetime('now')`` reads as *local* time in JavaScript,
which shifted every displayed time and scrambled the ordering), and the message
count must be the real number of messages rather than a size estimate.
"""

import sqlite3

import pytest

from src.core.chat_store import ChatStore


@pytest.fixture
def store(tmp_path):
    instance = ChatStore(db_path=str(tmp_path / "chat.db"))
    yield instance
    instance.close()


def _legacy_db(tmp_path, rows) -> str:
    """A database whose timestamps predate the ISO migration."""
    path = tmp_path / "legacy.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE chats (
            id TEXT PRIMARY KEY, title TEXT DEFAULT '', messages_json TEXT DEFAULT '[]',
            created_at TEXT, updated_at TEXT
        );
        """
    )
    conn.executemany("INSERT INTO chats VALUES (?,?,?,?,?)", rows)
    conn.commit()
    conn.close()
    return str(path)


LEGACY_ROW = ("old", "标题", "[]", "2026-07-21 02:09:48", "2026-09-21 07:49:41")


class TestTimestamps:
    def test_saved_timestamps_are_iso_utc(self, store):
        store.save_chat("c1", [{"id": "m1", "role": "user", "content": "hi"}])

        updated = store.get_chat("c1")["updatedAt"]

        assert "T" in updated and updated.endswith("Z")

    def test_legacy_timestamps_are_migrated(self, tmp_path):
        store = ChatStore(db_path=_legacy_db(tmp_path, [LEGACY_ROW]))

        row = store.get_chat("old")

        assert row["createdAt"] == "2026-07-21T02:09:48Z"
        assert row["updatedAt"] == "2026-09-21T07:49:41Z"
        store.close()

    def test_migration_is_idempotent(self, tmp_path):
        db = _legacy_db(tmp_path, [LEGACY_ROW])
        ChatStore(db_path=db).close()

        store = ChatStore(db_path=db)  # reopening must not tag the value twice

        assert store.get_chat("old")["updatedAt"] == "2026-09-21T07:49:41Z"
        store.close()


class TestListChats:
    def test_message_count_is_the_real_number(self, store):
        """The old `size / 100` estimate reported nonsense for long messages."""
        messages = [{"id": f"m{i}", "role": "user", "content": "x" * 500} for i in range(7)]
        store.save_chat("c1", messages)

        assert store.list_chats()[0]["messageCount"] == 7

    def test_listing_is_most_recent_first(self, store):
        store.save_chat("a", [{"id": "m1", "role": "user", "content": "a"}])
        store.save_chat("b", [{"id": "m2", "role": "user", "content": "b"}])
        # Both saves land in the same second, so give `a` an unambiguous older
        # stamp rather than relying on a wall-clock sleep.
        store._conn.execute("UPDATE chats SET updated_at='2020-01-01T00:00:00Z' WHERE id='a'")
        store._conn.commit()

        assert [c["id"] for c in store.list_chats()] == ["b", "a"]

    def test_title_defaults_to_the_first_user_message(self, store):
        store.save_chat("c1", [{"id": "m1", "role": "user", "content": "帮我回测"}])

        assert store.list_chats()[0]["title"] == "帮我回测"


class TestRoundTrip:
    def test_save_get_delete(self, store):
        messages = [{"id": "m1", "role": "user", "content": "问题"}]
        store.save_chat("c1", messages)

        assert store.get_chat("c1")["messages"] == messages

        store.delete_chat("c1")
        assert store.get_chat("c1") is None

    def test_saving_again_replaces_the_messages(self, store):
        store.save_chat("c1", [{"id": "m1", "role": "user", "content": "一"}])
        store.save_chat(
            "c1",
            [
                {"id": "m1", "role": "user", "content": "一"},
                {"id": "m2", "role": "assistant", "content": "二"},
            ],
        )

        assert len(store.get_chat("c1")["messages"]) == 2
        assert len(store.list_chats()) == 1
