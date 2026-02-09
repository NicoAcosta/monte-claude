.PHONY: run-game run-data test install db-up db-down

install:
	uv pip install -e ".[dev]"

run-game:
	uv run uvicorn game_api.app:app --host 0.0.0.0 --port 8001 --reload

run-data:
	uv run uvicorn data_api.app:app --host 0.0.0.0 --port 8000 --reload

test:
	uv run pytest -v

db-up:
	docker compose -f ../../docker-compose.yml up -d postgres

db-down:
	docker compose -f ../../docker-compose.yml down
