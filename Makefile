.PHONY: install test run build-contracts test-contracts test-all db-up db-down

install:
	cd packages/server && $(MAKE) install

run:
	cd packages/server && $(MAKE) run

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
