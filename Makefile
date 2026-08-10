# default target is build
.DEFAULT_GOAL := help

# if we are on GitHub Actions then use the "system" otherwise virtualenv
ifeq ($(GITHUB_ACTIONS), true)
	VENV_DIR :=
	PIP := pip
	PYTHON := python
	PROPERDOCS := properdocs
	SCRIV := scriv
	# throw away to ensure we always run this
	ACTIVATE := .activate
else
	VENV_DIR := .venv
	PIP := $(VENV_DIR)/bin/pip
	PYTHON := $(VENV_DIR)/bin/python
	PROPERDOCS := $(VENV_DIR)/bin/properdocs
	SCRIV := $(VENV_DIR)/bin/scriv
	ACTIVATE := $(VENV_DIR)/bin/activate
endif

NEUTRON_SAMPLE_CONFIG := docs/design-guide/neutron-understack-config-sample.md

UNRELEASED_NOTES := docs/release-notes/unreleased.md

WFTMPLS := $(wildcard components/*-workflows/*/workflowtemplates/*.yaml)

.PHONY: help
help: ## Displays this help message
	@echo "$$(grep -hE '^\S+:.*##' $(MAKEFILE_LIST) | sed -e 's/:.*##\s*/|/' -e 's/^\(.\+\):\(.*\)/\\x1b[36m\1\\x1b[m:\2/' | column -c2 -t -s'|' | sort)"

$(ACTIVATE): requirements-docs.txt
	@[ -n "${VENV_DIR}" -a ! -d "${VENV_DIR}" ] && python -m venv $(VENV_DIR) || :
	@$(PIP) install -U -r requirements-docs.txt
	@touch $(ACTIVATE)

.PHONY: wftmpls
wftmpls: $(WFTMPLS) $(ACTIVATE)
	@mkdir -p docs/workflows
	@rm -f docs/workflows/*.md
	@$(PYTHON) scripts/argo-workflows-to-mkdocs.py components/global-workflows docs/workflows
	@$(PYTHON) scripts/argo-workflows-to-mkdocs.py workflows docs/workflows

.PHONY: component-docs-check
component-docs-check: ## Validate component docs coverage for ArgoCD app templates
	@$(PYTHON) scripts/check-component-docs.py

$(NEUTRON_SAMPLE_CONFIG): ## Generate neutron-understack sample configuration docs
	@mkdir -p docs/design-guide
	@uv sync --directory python/neutron-understack
	@{ printf '# neutron-understack Sample Configuration\n\n```ini\n'; \
	   uv run --directory python/neutron-understack oslo-config-generator \
	       --config-file tools/config/neutron-understack-config-generator.conf; \
	   printf '\n```\n'; } > $(NEUTRON_SAMPLE_CONFIG)

# Renders the release-note fragments in changelog.d/ into a generated
# "Unreleased" page. scriv has no --draft mode, so this collects with --keep,
# which leaves the fragments in place. scriv exits 2 when there is nothing to
# collect, which is the normal case; any other failure is real.
.PHONY: unreleased-notes
unreleased-notes: $(ACTIVATE) ## Render pending release notes into the Unreleased page
	@printf '%s\n' \
	  '# Unreleased' \
	  '' \
	  'Changes merged to `main` that are not yet in a tagged release. If you' \
	  'deploy with `understack_ref: HEAD`, these apply to your deployment now.' \
	  '' \
	  'This page is generated from the fragments in `changelog.d/`. If nothing' \
	  'is listed below, nothing merged since the last tag needs operator action.' \
	  '' \
	  '<!-- scriv-insert-here -->' > $(UNRELEASED_NOTES)
	@$(SCRIV) collect --config changelog.d/unreleased.ini --keep --no-add \
	  || [ $$? -eq 2 ]

.PHONY: docs
docs: $(ACTIVATE) wftmpls $(NEUTRON_SAMPLE_CONFIG) unreleased-notes component-docs-check ## Builds the documentation
	$(PROPERDOCS) build --strict

.PHONY: docs-local
docs-local: $(ACTIVATE) wftmpls $(NEUTRON_SAMPLE_CONFIG) unreleased-notes component-docs-check ## Build and locally host the documentation
	$(PROPERDOCS) serve --strict --livereload
