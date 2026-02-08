.PHONY: run test install

install:
	uv pip install -e ".[dev]"

run:
	uv run uvicorn poker.server:app --host 0.0.0.0 --port 8000 --reload

test:
	uv run pytest -v
