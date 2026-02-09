.PHONY: run-game run-data run-data-prod run-account run-account-prod test install db-up db-down

DATA_WORKERS ?= 4
ACCOUNT_WORKERS ?= 2

install:
	uv pip install -e ".[dev]"

run-game:
	uv run uvicorn game_api.app:app --host 0.0.0.0 --port 8001 --reload

run-data:
	uv run uvicorn data_api.app:app --host 0.0.0.0 --port 8000 --reload

run-data-prod:
	uv run uvicorn data_api.app:app --host 0.0.0.0 --port 8000 --workers $(DATA_WORKERS)

run-account:
	uv run uvicorn account_api.app:app --host 0.0.0.0 --port 8002 --reload

run-account-prod:
	uv run uvicorn account_api.app:app --host 0.0.0.0 --port 8002 --workers $(ACCOUNT_WORKERS)

test:
	uv run pytest -v

db-up:
	docker compose -f ../../docker-compose.yml up -d postgres

db-down:
	docker compose -f ../../docker-compose.yml down
