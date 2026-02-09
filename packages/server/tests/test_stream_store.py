"""Unit tests for StreamStore."""

import pytest

from poker.db import get_pool
from poker.stream_store import StreamStore


class TestStreamStore:
    def test_create_and_get(self):
        store = StreamStore(get_pool())
        stream = store.create(game_id=1, host_username="Alice", title="Test Stream")
        assert stream.id >= 1
        assert stream.game_id == 1
        assert stream.host_username == "Alice"
        assert stream.title == "Test Stream"
        assert stream.commentary_text is None

        fetched = store.get(stream.id)
        assert fetched is not None
        assert fetched.title == "Test Stream"

    def test_get_nonexistent(self):
        store = StreamStore(get_pool())
        assert store.get(999) is None

    def test_duplicate_host_per_game_rejected(self):
        store = StreamStore(get_pool())
        store.create(game_id=1, host_username="Alice", title="First")
        with pytest.raises(ValueError, match="already has a stream"):
            store.create(game_id=1, host_username="Alice", title="Second")

    def test_same_host_different_game_ok(self):
        store = StreamStore(get_pool())
        s1 = store.create(game_id=1, host_username="Alice", title="Game 1 Stream")
        s2 = store.create(game_id=2, host_username="Alice", title="Game 2 Stream")
        assert s1.id != s2.id

    def test_update_commentary(self):
        store = StreamStore(get_pool())
        stream = store.create(game_id=1, host_username="Alice", title="Test")
        store.update_commentary(stream.id, "Hello viewers!")
        fetched = store.get(stream.id)
        assert fetched.commentary_text == "Hello viewers!"

    def test_list_for_game(self):
        store = StreamStore(get_pool())
        store.create(game_id=1, host_username="Alice", title="Stream A")
        store.create(game_id=1, host_username="Bob", title="Stream B")
        store.create(game_id=2, host_username="Charlie", title="Other")

        summaries = store.list_for_game(1)
        assert len(summaries) == 2
        hosts = {s.host_username for s in summaries}
        assert hosts == {"Alice", "Bob"}

    def test_list_all(self):
        store = StreamStore(get_pool())
        store.create(game_id=1, host_username="Alice", title="S1")
        store.create(game_id=2, host_username="Bob", title="S2")
        summaries = store.list_all()
        assert len(summaries) == 2

    def test_list_all_empty(self):
        store = StreamStore(get_pool())
        assert store.list_all() == []
