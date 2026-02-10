"""Tests for GameEventBus — in-process pub/sub for WebSocket state pushes."""

import asyncio

import pytest

from core.event_bus import GameEventBus, Subscriber


class TestGameEventBus:
    """Test event bus subscribe/publish/unsubscribe lifecycle."""

    @pytest.mark.asyncio
    async def test_subscribe_returns_subscriber(self):
        bus = GameEventBus()
        sub = bus.subscribe("game-1")
        assert isinstance(sub, Subscriber)
        assert sub.game_id == "game-1"

    @pytest.mark.asyncio
    async def test_publish_delivers_to_subscriber(self):
        bus = GameEventBus()
        sub = bus.subscribe("game-1")
        bus.publish("game-1", "action", {"player": "Alice"})
        event = await asyncio.wait_for(sub.get(), timeout=1.0)
        assert event == ("action", {"player": "Alice"})

    @pytest.mark.asyncio
    async def test_publish_to_different_game_not_received(self):
        bus = GameEventBus()
        sub = bus.subscribe("game-1")
        bus.publish("game-2", "action", {"player": "Bob"})
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(sub.get(), timeout=0.1)

    @pytest.mark.asyncio
    async def test_multiple_subscribers_same_game(self):
        bus = GameEventBus()
        sub1 = bus.subscribe("game-1")
        sub2 = bus.subscribe("game-1")
        bus.publish("game-1", "action", {"data": "test"})
        e1 = await asyncio.wait_for(sub1.get(), timeout=1.0)
        e2 = await asyncio.wait_for(sub2.get(), timeout=1.0)
        assert e1 == e2

    @pytest.mark.asyncio
    async def test_unsubscribe_stops_delivery(self):
        bus = GameEventBus()
        sub = bus.subscribe("game-1")
        bus.unsubscribe(sub)
        bus.publish("game-1", "action", {"data": "test"})
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(sub.get(), timeout=0.1)

    @pytest.mark.asyncio
    async def test_unsubscribe_idempotent(self):
        bus = GameEventBus()
        sub = bus.subscribe("game-1")
        bus.unsubscribe(sub)
        bus.unsubscribe(sub)  # Should not raise

    @pytest.mark.asyncio
    async def test_publish_to_game_with_no_subscribers(self):
        bus = GameEventBus()
        bus.publish("game-1", "action", {})  # Should not raise

    @pytest.mark.asyncio
    async def test_subscriber_count(self):
        bus = GameEventBus()
        assert bus.subscriber_count("game-1") == 0
        sub1 = bus.subscribe("game-1")
        assert bus.subscriber_count("game-1") == 1
        sub2 = bus.subscribe("game-1")
        assert bus.subscriber_count("game-1") == 2
        bus.unsubscribe(sub1)
        assert bus.subscriber_count("game-1") == 1

    @pytest.mark.asyncio
    async def test_total_subscribers(self):
        bus = GameEventBus()
        bus.subscribe("game-1")
        bus.subscribe("game-2")
        assert bus.total_subscribers == 2

    @pytest.mark.asyncio
    async def test_bounded_queue_drops_when_full(self):
        """When queue is full (slow consumer), publish should not block."""
        bus = GameEventBus(max_queue_size=2)
        sub = bus.subscribe("game-1")
        bus.publish("game-1", "e1", {})
        bus.publish("game-1", "e2", {})
        bus.publish("game-1", "e3", {})  # Queue full, should not block
        # The sub should have the first 2 events
        e1 = await asyncio.wait_for(sub.get(), timeout=1.0)
        e2 = await asyncio.wait_for(sub.get(), timeout=1.0)
        assert e1[0] == "e1"
        assert e2[0] == "e2"

    @pytest.mark.asyncio
    async def test_cleanup_game_removes_all_subscribers(self):
        bus = GameEventBus()
        sub1 = bus.subscribe("game-1")
        sub2 = bus.subscribe("game-1")
        bus.cleanup_game("game-1")
        assert bus.subscriber_count("game-1") == 0
