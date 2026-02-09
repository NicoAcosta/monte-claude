.PHONY: install test run-game run-data run-data-prod build-contracts test-contracts test-all db-up db-down

install:
	cd packages/server && $(MAKE) install

run-game:
	cd packages/server && $(MAKE) run-game

run-data:
	cd packages/server && $(MAKE) run-data

run-data-prod:
	cd packages/server && $(MAKE) run-data-prod

test:
	cd packages/server && $(MAKE) test

build-contracts:
	cd packages/contracts && $(MAKE) build

test-contracts:
	cd packages/contracts && $(MAKE) test

test-all: test test-contracts

db-up:
	docker compose up -d postgres

db-down:
	docker compose down
