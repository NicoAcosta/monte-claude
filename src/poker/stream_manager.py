from __future__ import annotations

from dataclasses import dataclass

from poker.stream import Stream


@dataclass(frozen=True)
class StreamSummary:
    id: int
    game_id: int
    host_username: str
    title: str


class StreamManager:
    def __init__(self) -> None:
        self._streams: dict[int, Stream] = {}
        self._next_id = 1

    def create_stream(self, game_id: int, host_username: str, title: str) -> Stream:
        for s in self._streams.values():
            if s.game_id == game_id and s.host_username == host_username:
                raise ValueError(f"User '{host_username}' already has a stream on this game")

        stream = Stream(
            id=self._next_id,
            game_id=game_id,
            host_username=host_username,
            title=title,
        )
        self._streams[stream.id] = stream
        self._next_id += 1
        return stream

    def get_stream(self, stream_id: int) -> Stream | None:
        return self._streams.get(stream_id)

    def list_streams_for_game(self, game_id: int) -> list[StreamSummary]:
        return [
            StreamSummary(
                id=s.id,
                game_id=s.game_id,
                host_username=s.host_username,
                title=s.title,
            )
            for s in self._streams.values()
            if s.game_id == game_id
        ]

    def list_all_streams(self) -> list[StreamSummary]:
        return [
            StreamSummary(
                id=s.id,
                game_id=s.game_id,
                host_username=s.host_username,
                title=s.title,
            )
            for s in self._streams.values()
        ]
