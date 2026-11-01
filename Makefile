SHELL := /bin/bash

# =============================================================================
# Configuration and Environment Variables
# =============================================================================

.DEFAULT_GOAL:=help
.ONESHELL:
.SHELLFLAGS := -ec
.EXPORT_ALL_VARIABLES:
MAKEFLAGS += --no-print-directory

# -----------------------------------------------------------------------------
# Display Formatting and Colors
# -----------------------------------------------------------------------------
BLUE := $(shell printf "\033[1;34m")
GREEN := $(shell printf "\033[1;32m")
RED := $(shell printf "\033[1;31m")
YELLOW := $(shell printf "\033[1;33m")
NC := $(shell printf "\033[0m")
INFO := $(shell printf "$(BLUE)ℹ$(NC)")
OK := $(shell printf "$(GREEN)✓$(NC)")
WARN := $(shell printf "$(YELLOW)⚠$(NC)")
ERROR := $(shell printf "$(RED)✖$(NC)")

# =============================================================================
# Help and Documentation
# =============================================================================

.PHONY: help
help:                                               ## Display this help text for Makefile
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m\n"} /^[a-zA-Z0-9_-]+:.*?##/ { printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2 } /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

# =============================================================================
# Installation and Environment Setup
# =============================================================================

.PHONY: install-uv
install-uv:                                         ## Install latest version of uv
	@echo "${INFO} Installing uv..."
	@curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null 2>&1
	@echo "${OK} UV installed successfully"

.PHONY: install
install: destroy clean                              ## Install the project, dependencies, and pre-commit for local development
	@echo "${INFO} Starting fresh installation..."
	@uv python pin 3.12 >/dev/null 2>&1
	@uv venv >/dev/null 2>&1
	@uv sync
	@echo "${OK} Installation complete! 🎉"

.PHONY: destroy
destroy:                                            ## Destroy virtual environment and clean caches
	@echo "${INFO} Destroying virtual environment... 🗑️"
	@uvx prek clean >/dev/null 2>&1 || true
	@rm -rf .venv
	@echo "${OK} Virtual environment destroyed 🗑️"

# =============================================================================
# Dependency Management
# =============================================================================

.PHONY: upgrade
upgrade:                                            ## Upgrade all dependencies to latest stable versions
	@echo "${INFO} Updating all dependencies... 🔄"
	@uv lock --upgrade
	@echo "${OK} Dependencies updated 🔄"
	@uvx prek autoupdate --cooldown-days 7
	@echo "${OK} Updated prek hooks (7-day cooldown) 🔄"
	@uv lock >/dev/null 2>&1

.PHONY: lock
lock:                                              ## Rebuild lockfiles from scratch
	@echo "${INFO} Rebuilding lockfiles... 🔄"
	@uv lock --upgrade
	@echo "${OK} Lockfiles updated"

# =============================================================================
# Build and Release
# =============================================================================

.PHONY: build
build:                                             ## Build the project
	@echo "${INFO} Building package... 📦"
	@uv build
	@echo "${OK} Package build complete"

.PHONY: release
release:                                           ## Finalize a pre-release, or bump a stable release with bump=patch|minor|major
	@current_version="$$(uv run bump-my-version show current_version 2>/dev/null)"
	@release_version=""
	@if [[ "$$current_version" == *-* ]]; then \
		release_version="$${current_version%%-*}"; \
		echo "${INFO} Finalizing pre-release $$current_version as $$release_version... 📦"; \
	elif [ -z "$(bump)" ]; then \
		echo "${ERROR} Current version $$current_version is stable. Usage: make release bump=major|minor|patch"; \
		exit 1; \
	else \
		echo "${INFO} Preparing release bump ($(bump)) from $$current_version... 📦"; \
	fi
	@make clean
	@if [ -n "$$release_version" ]; then \
		uv run bump-my-version bump --new-version "$$release_version" pre; \
	else \
		uv run bump-my-version bump "$(bump)"; \
	fi
	@uv lock --upgrade-package litestar-granian >/dev/null 2>&1
	@make docs
	@make build
	@echo "${OK} Release complete 🎉"

.PHONY: pre-release
pre-release:                                       ## Set a pre-release: make pre-release version=0.16.0-beta.1
	@if [ -z "$(version)" ]; then \
		echo "${ERROR} Usage: make pre-release version=X.Y.Z-alpha.N"; \
		echo ""; \
		echo "Pre-release workflow:"; \
		echo "  1. Start alpha:     make pre-release version=0.16.0-alpha.1"; \
		echo "  2. Next alpha:      make pre-release version=0.16.0-alpha.2"; \
		echo "  3. Move to beta:    make pre-release version=0.16.0-beta.1"; \
		echo "  4. Move to rc:      make pre-release version=0.16.0-rc.1"; \
		echo "  5. Final release:   make release"; \
		exit 1; \
	fi
	@echo "${INFO} Preparing pre-release $(version)... 🧪"
	@make clean
	@uv run bump-my-version bump --new-version $(version) pre
	@uv lock --upgrade-package litestar-granian >/dev/null 2>&1
	@make build
	@echo "${OK} Pre-release $(version) complete 🧪"
	@echo ""
	@echo "${INFO} Next steps:"
	@echo "  1. Push: git push origin HEAD"
	@echo "  2. Create a GitHub pre-release: gh release create v$(version) --prerelease --generate-notes --title 'v$(version)'"
	@echo "  3. This will publish to PyPI with pre-release tags"

# =============================================================================
# Cleaning and Maintenance
# =============================================================================

.PHONY: clean
clean:                                              ## Cleanup temporary build artifacts
	@echo "${INFO} Cleaning working directory... 🧹"
	@rm -rf .pytest_cache .ruff_cache .hypothesis build/ dist/ .eggs/ .coverage coverage.xml coverage.json htmlcov/ .pytest_cache tests/.pytest_cache tests/**/.pytest_cache .mypy_cache >/dev/null 2>&1
	@find . -name '*.egg-info' -exec rm -rf {} + >/dev/null 2>&1
	@find . -type f -name '*.egg' -exec rm -f {} + >/dev/null 2>&1
	@find . -name '*.pyc' -exec rm -f {} + >/dev/null 2>&1
	@find . -name '*.pyo' -exec rm -f {} + >/dev/null 2>&1
	@find . -name '*~' -exec rm -f {} + >/dev/null 2>&1
	@find . -name '__pycache__' -exec rm -rf {} + >/dev/null 2>&1
	@find . -name '.ipynb_checkpoints' -exec rm -rf {} + >/dev/null 2>&1
	@echo "${OK} Working directory cleaned"
	$(MAKE) docs-clean

# =============================================================================
# Testing and Quality Checks
# =============================================================================

.PHONY: test
test:                                              ## Run the tests
	@echo "${INFO} Running test cases... 🧪"
	@uv run pytest tests
	@echo "${OK} Tests complete ✨"

.PHONY: test-all
test-all: test                                     ## Run all tests

.PHONY: coverage
coverage:                                          ## Run tests with coverage report
	@echo "${INFO} Running tests with coverage... 📊"
	@uv run pytest tests --cov -n auto
	@uv run coverage html >/dev/null 2>&1
	@uv run coverage xml >/dev/null 2>&1
	@echo "${OK} Coverage report generated ✨"

# -----------------------------------------------------------------------------
# Type Checking
# -----------------------------------------------------------------------------

.PHONY: mypy
mypy:                                              ## Run mypy
	@echo "${INFO} Running mypy... 🔍"
	@uv run dmypy run
	@echo "${OK} Mypy checks passed ✨"

.PHONY: mypy-nocache
mypy-nocache:                                      ## Run Mypy without cache
	@echo "${INFO} Running mypy without cache... 🔍"
	@uv run mypy
	@echo "${OK} Mypy checks passed ✨"

.PHONY: pyright
pyright:                                           ## Run pyright
	@echo "${INFO} Running pyright... 🔍"
	@uv run pyright
	@echo "${OK} Pyright checks passed ✨"

.PHONY: type-check
type-check: mypy pyright                           ## Run all type checking

# -----------------------------------------------------------------------------
# Linting and Formatting
# -----------------------------------------------------------------------------

.PHONY: prek
prek:                                               ## Run prek hooks
	@echo "${INFO} Running prek checks... 🔍"
	@git ls-files --cached --others --exclude-standard -z | \
		xargs -0 uvx prek run --show-diff-on-failure --color=always --files
	@echo "${OK} prek checks passed ✨"

.PHONY: pre-commit
pre-commit: prek                                    ## Compatibility alias for prek

.PHONY: zizmor
zizmor:                                            ## Run zizmor workflow security scanner
	@echo "${INFO} Running zizmor workflow security checks... 🛡️"
	@if [ -d ".github/workflows" ]; then \
		uvx zizmor .github/workflows; \
	else \
		echo "${WARN} No .github/workflows directory found"; \
	fi
	@echo "${OK} zizmor workflow checks passed ✨"

.PHONY: slotscheck
slotscheck:                                        ## Run slotscheck
	@echo "${INFO} Running slots check... 🔍"
	@uv run slotscheck litestar_granian/
	@echo "${OK} Slots check passed ✨"

.PHONY: lint
lint: prek type-check slotscheck zizmor             ## Run all linting checks

.PHONY: check-all
check-all: lint test-all coverage                  ## Run all checks (lint, test, coverage)

# =============================================================================
# Documentation
# =============================================================================

.PHONY: docs-clean
docs-clean:                                        ## Remove built documentation and Zensical cache
	@echo "${INFO} Cleaning documentation build assets... 🧹"
	@rm -rf site .cache docs/_build
	@echo "${OK} Documentation assets cleaned"

.PHONY: docs
docs: docs-clean                                   ## Build and verify Zensical documentation
	@echo "${INFO} Building documentation (Zensical)... 📝"
	@uv run --no-sync python -m tools.docs.scan_public_docstrings --check-leaks --check-overloads --check-typeddicts litestar_granian
	@uv run --no-sync python -m tools.docs.generate_cli_docs --check
	@uv run --no-sync zensical build --clean
	@uv run --no-sync python -m tools.docs.postbuild --site-dir site --docs-dir docs --zensical-config zensical.toml
	@uv run --no-sync python -m tools.docs.verify_docs_artifacts --site-dir site
	@echo "${OK} Documentation built and verified in site/"

.PHONY: docs-serve
docs-serve: docs                                   ## Build and serve documentation locally
	@echo "${INFO} Starting documentation server... 📚"
	@uv run --no-sync zensical serve --dev-addr 127.0.0.1:8000

.PHONY: docs-check
docs-check: docs                                   ## Build docs and verify live zensical serve HTTP 200
	@echo "${INFO} Verifying zensical serve..."
	@set -euo pipefail; \
	server_log="$$(mktemp)"; \
	server_pid=""; \
	cleanup() { \
		if [ -n "$$server_pid" ] && kill -0 "$$server_pid" 2>/dev/null; then \
			kill "$$server_pid" 2>/dev/null || true; \
			wait "$$server_pid" 2>/dev/null || true; \
		fi; \
		rm -f "$$server_log"; \
	}; \
	trap cleanup EXIT INT TERM; \
	uv run --no-sync zensical serve --dev-addr 127.0.0.1:8000 >"$$server_log" 2>&1 & \
	server_pid="$$!"; \
	for _ in $$(seq 1 50); do \
		if curl --silent --show-error --fail http://127.0.0.1:8000/ >/dev/null 2>&1 || curl --silent --show-error --fail http://127.0.0.1:8000/litestar-granian/ >/dev/null 2>&1; then \
			echo "${OK} Docs server responded with HTTP 200"; \
			exit 0; \
		fi; \
		if ! kill -0 "$$server_pid" 2>/dev/null; then \
			cat "$$server_log" >&2; \
			exit 1; \
		fi; \
		sleep 0.2; \
	done; \
	cat "$$server_log" >&2; \
	exit 1
