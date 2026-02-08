.PHONY: install test run build-contracts test-contracts test-all

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
