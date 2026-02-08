.PHONY: build test test-e2e

build:
	forge build

test:
	forge test -vvv

test-e2e:
	forge test --fork-url $(BASE_RPC_URL) -vvv --match-contract E2E
