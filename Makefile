# default target is build
.DEFAULT_GOAL := help

.PHONY: help
help: ## Displays this help message
	@echo "$$(grep -hE '^\S+:.*##' $(MAKEFILE_LIST) | sed -e 's/:.*##\s*/|/' -e 's/^\(.\+\):\(.*\)/\\x1b[36m\1\\x1b[m:\2/' | column -c2 -t -s'|' | sort)"

.PHONY: docs
docs: ## Builds the documentation
	@[ ! -d .venv ] && python -m venv .venv || :
	@.venv/bin/pip install -U -r requirements-docs.txt
	.venv/bin/mkdocs build --strict

.PHONY: docs-local
docs-local: ## Build and locally host the documentation
	@[ ! -d .venv ] && python -m venv .venv || :
	@.venv/bin/pip install -U -r requirements-docs.txt
	.venv/bin/mkdocs serve --strict
