.PHONY: run test install db-up db-down

install:
	uv pip install -e ".[dev]"

run:
	uv run uvicorn poker.server:app --host 0.0.0.0 --port 8000 --reload

test:
	uv run pytest -v

db-up:
	docker compose -f ../../docker-compose.yml up -d postgres

db-down:
	docker compose -f ../../docker-compose.yml down
