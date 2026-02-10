.PHONY: run-game run-data run-data-prod run-account run-account-prod test install db-up db-down

DATA_WORKERS ?= 4
ACCOUNT_WORKERS ?= 2

# Anvil account #0 — deterministic dev key for local testing
SERVER_PRIVATE_KEY ?= 0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80
MONTE_TOKEN_ADDRESS ?=

install:
	uv pip install -e ".[dev]"

run-game:
	SERVER_PRIVATE_KEY=$(SERVER_PRIVATE_KEY) uv run uvicorn game_api.app:app --host 0.0.0.0 --port 8001 --reload

run-data:
	MONTE_TOKEN_ADDRESS=$(MONTE_TOKEN_ADDRESS) uv run uvicorn data_api.app:app --host 0.0.0.0 --port 8000 --reload

run-data-prod:
	MONTE_TOKEN_ADDRESS=$(MONTE_TOKEN_ADDRESS) uv run uvicorn data_api.app:app --host 0.0.0.0 --port 8000 --workers $(DATA_WORKERS)

run-account:
	uv run uvicorn account_api.app:app --host 0.0.0.0 --port 8002 --reload

run-account-prod:
	uv run uvicorn account_api.app:app --host 0.0.0.0 --port 8002 --workers $(ACCOUNT_WORKERS)

test:
	SERVER_PRIVATE_KEY=$(SERVER_PRIVATE_KEY) uv run pytest -v

db-up:
	docker compose -f ../../docker-compose.yml up -d postgres

db-down:
	docker compose -f ../../docker-compose.yml down
