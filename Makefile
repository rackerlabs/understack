# default target is build
.DEFAULT_GOAL := help

# if we are on GitHub Actions then use the "system" otherwise virtualenv
ifeq ($(GITHUB_ACTIONS), true)
	VENV_DIR :=
	PIP := pip
	PYTHON := python
	MKDOCS := mkdocs
	# throw away to ensure we always run this
	ACTIVATE := .activate
else
	VENV_DIR := .venv
	PIP := $(VENV_DIR)/bin/pip
	PYTHON := $(VENV_DIR)/bin/python
	MKDOCS := $(VENV_DIR)/bin/mkdocs
	ACTIVATE := $(VENV_DIR)/bin/activate
endif

.PHONY: help
help: ## Displays this help message
	@echo "$$(grep -hE '^\S+:.*##' $(MAKEFILE_LIST) | sed -e 's/:.*##\s*/|/' -e 's/^\(.\+\):\(.*\)/\\x1b[36m\1\\x1b[m:\2/' | column -c2 -t -s'|' | sort)"

$(ACTIVATE): requirements-docs.txt
	@[ ! -d "$(VENV_DIR)" ] && python -m venv "$(VENV_DIR)" || :
	@$(PIP) install -U -r requirements-docs.txt
	@touch $(ACTIVATE)

docs/workflows/argo-events.md: $(ACTIVATE)
	@mkdir -p docs/workflows
	@$(PYTHON) scripts/argo-workflows-to-mkdocs.py workflows docs/workflows

.PHONY: docs
docs: $(ACTIVATE) docs/workflows/argo-events.md ## Builds the documentation
	$(MKDOCS) build --strict

.PHONY: docs-local
docs-local: $(ACTIVATE) docs/workflows/argo-events.md ## Build and locally host the documentation
	$(MKDOCS) serve --strict
