from fastapi.testclient import TestClient

from data_api.app import app as data_app
from game_api.app import app as game_app


class TestGameApiHealth:
    def test_health_returns_healthy(self):
        client = TestClient(game_app)
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "healthy"
        assert body["db"] is True
        assert "pool" in body
        assert "size" in body["pool"]
        assert "available" in body["pool"]
        assert "waiting" in body["pool"]

    def test_ping_still_works(self):
        client = TestClient(game_app)
        resp = client.get("/ping")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestDataApiHealth:
    def test_health_returns_healthy(self):
        client = TestClient(data_app)
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "healthy"
        assert body["db"] is True
        assert "pool" in body

    def test_ping_still_works(self):
        client = TestClient(data_app)
        resp = client.get("/ping")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
