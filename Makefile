.PHONY: run test install

install:
	pip install -e ".[dev]"

run:
	uvicorn poker.server:app --host 0.0.0.0 --port 8000 --reload

test:
	pytest -v
