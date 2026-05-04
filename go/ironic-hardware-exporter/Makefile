BINARY    := ironic-hardware-exporter
CMD       := ./cmd/ironic-hardware-exporter
IMG       ?= ironic-hardware-exporter:dev

CONTAINER_TOOL ?= docker
GOLANGCI_LINT  ?= golangci-lint

.PHONY: all
all: build

.PHONY: help
help: ## Display this help.
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m\n"} /^[a-zA-Z_0-9-]+:.*?##/ { printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2 } /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

##@ Development

.PHONY: fmt
fmt: ## Run go fmt against code.
	go fmt ./...

.PHONY: vet
vet: ## Run go vet against code.
	go vet ./...

.PHONY: test
test: fmt vet ## Run tests.
	GOCACHE=/tmp/gocache go test ./...

.PHONY: test-race
test-race: ## Run tests with the race detector.
	go test -race ./...

.PHONY: lint
lint: ## Run golangci-lint.
	$(GOLANGCI_LINT) run ./...

.PHONY: lint-fix
lint-fix: ## Run golangci-lint and apply fixes.
	$(GOLANGCI_LINT) run --fix ./...

##@ Build

.PHONY: build
build: fmt vet ## Build the binary.
	go build -o $(BINARY) $(CMD)

.PHONY: run
run: fmt vet ## Run the service locally (requires RABBITMQ_PASSWORD).
	go run $(CMD)/main.go

.PHONY: docker-build
docker-build: ## Build the container image.
	$(CONTAINER_TOOL) build -t $(IMG) .

.PHONY: docker-push
docker-push: ## Push the container image.
	$(CONTAINER_TOOL) push $(IMG)

##@ Validation

.PHONY: smoke
smoke: ## Run the local RabbitMQ smoke test (all cases).
	GOCACHE=/tmp/gocache ./local/rabbitmq/smoke.sh all
