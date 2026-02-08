import pytest

from poker.stream_manager import StreamManager


@pytest.fixture
def mgr():
    return StreamManager()


class TestStreamManager:
    def test_create_stream(self, mgr):
        stream = mgr.create_stream(1, "Alice", "Alice's commentary")
        assert stream.id == 1
        assert stream.game_id == 1
        assert stream.host_username == "Alice"
        assert stream.title == "Alice's commentary"
        assert stream.commentary_text is None

    def test_create_stream_increments_id(self, mgr):
        s1 = mgr.create_stream(1, "Alice", "Stream 1")
        s2 = mgr.create_stream(1, "Bob", "Stream 2")
        assert s1.id == 1
        assert s2.id == 2

    def test_duplicate_host_per_game_rejected(self, mgr):
        mgr.create_stream(1, "Alice", "First stream")
        with pytest.raises(ValueError, match="already has a stream"):
            mgr.create_stream(1, "Alice", "Second stream")

    def test_same_host_different_games_allowed(self, mgr):
        s1 = mgr.create_stream(1, "Alice", "Game 1 stream")
        s2 = mgr.create_stream(2, "Alice", "Game 2 stream")
        assert s1.game_id == 1
        assert s2.game_id == 2

    def test_get_stream(self, mgr):
        stream = mgr.create_stream(1, "Alice", "Test stream")
        assert mgr.get_stream(stream.id) is stream

    def test_get_stream_not_found(self, mgr):
        assert mgr.get_stream(999) is None

    def test_list_streams_for_game(self, mgr):
        mgr.create_stream(1, "Alice", "Stream A")
        mgr.create_stream(1, "Bob", "Stream B")
        mgr.create_stream(2, "Charlie", "Stream C")

        game1_streams = mgr.list_streams_for_game(1)
        assert len(game1_streams) == 2
        hosts = {s.host_username for s in game1_streams}
        assert hosts == {"Alice", "Bob"}

        game2_streams = mgr.list_streams_for_game(2)
        assert len(game2_streams) == 1
        assert game2_streams[0].host_username == "Charlie"

    def test_list_streams_for_game_empty(self, mgr):
        assert mgr.list_streams_for_game(999) == []

    def test_list_all_streams(self, mgr):
        mgr.create_stream(1, "Alice", "Stream A")
        mgr.create_stream(2, "Bob", "Stream B")
        all_streams = mgr.list_all_streams()
        assert len(all_streams) == 2

    def test_list_all_streams_empty(self, mgr):
        assert mgr.list_all_streams() == []

    def test_commentary_text_mutable(self, mgr):
        stream = mgr.create_stream(1, "Alice", "Test")
        stream.commentary_text = "What a play!"
        fetched = mgr.get_stream(stream.id)
        assert fetched is not None
        assert fetched.commentary_text == "What a play!"

    def test_multiple_streams_independent_commentary(self, mgr):
        s1 = mgr.create_stream(1, "Alice", "Stream A")
        s2 = mgr.create_stream(1, "Bob", "Stream B")
        s1.commentary_text = "Alice's take"
        s2.commentary_text = "Bob's take"
        assert mgr.get_stream(s1.id).commentary_text == "Alice's take"
        assert mgr.get_stream(s2.id).commentary_text == "Bob's take"
