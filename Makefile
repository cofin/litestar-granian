SHELL := /bin/bash
# =============================================================================
# Variables
# =============================================================================

.DEFAULT_GOAL:=help
.ONESHELL:
.EXPORT_ALL_VARIABLES:


.PHONY: help
help: 		   										## Display this help text for Makefile
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m\n"} /^[a-zA-Z0-9_-]+:.*?##/ { printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2 } /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

.PHONY: upgrade
upgrade:       										## Upgrade all dependencies to the latest stable versions
	@echo "=> Updating all dependencies"
	@uv lock --upgrade
	@echo "=> Dependencies Updated"
	@uv run pre-commit autoupdate
	@echo "=> Updated Pre-commit"

# =============================================================================
# Developer Utils
# =============================================================================
.PHONY: install-uv
install-uv: 										## Install latest version of uv
	@curl -LsSf https://astral.sh/uv/install.sh | sh

.PHONY: install
install: clean										## Install the project, dependencies, and pre-commit for local development
	@uv sync --all-extras --dev
	@echo "=> Install complete!"

build: 												## Build the project
	@uv build
	@echo "=> Build complete!"

.PHONY: clean
clean: 												## Cleanup temporary build artifacts
	@echo "=> Cleaning working directory"
	@rm -rf .pytest_cache .ruff_cache .hypothesis build/ -rf dist/ .eggs/
	@find . -name '*.egg-info' -exec rm -rf {} +
	@find . -type f -name '*.egg' -exec rm -f {} +
	@find . -name '*.pyc' -exec rm -f {} +
	@find . -name '*.pyo' -exec rm -f {} +
	@find . -name '*~' -exec rm -f {} +
	@find . -name '__pycache__' -exec rm -rf {} +
	@find . -name '.ipynb_checkpoints' -exec rm -rf {} +
	@rm -rf .coverage coverage.xml coverage.json htmlcov/ .pytest_cache tests/.pytest_cache tests/**/.pytest_cache .mypy_cache
	$(MAKE) docs-clean

.PHONY: destroy
destroy: 											## Destroy the virtual environment
	@rm -rf .venv

.PHONY: lock
lock:                                             ## Rebuild lockfiles from scratch, updating all dependencies
	@uv lock --upgrade

# =============================================================================
# Tests, Linting, Coverage
# =============================================================================
.PHONY: mypy
mypy:                                               ## Run mypy
	@echo "=> Running mypy"
	@uv run dmypy run
	@echo "=> mypy complete"

.PHONY: mypy-nocache
mypy-nocache:                                       ## Run Mypy without cache
	@echo "=> Running mypy without a cache"
	@uv run mypy
	@echo "=> mypy complete"

.PHONY: pyright
pyright:                                            ## Run pyright
	@echo "=> Running pyright"
	@uv run pyright
	@echo "=> pyright complete"

.PHONY: type-check
type-check: mypy pyright                            ## Run all type checking

.PHONY: pre-commit
pre-commit: 										## Runs pre-commit hooks; includes ruff formatting and linting, codespell
	@echo "=> Running pre-commit process"
	@uv run pre-commit run --all-files
	@echo "=> Pre-commit complete"

.PHONY: slotscheck
slotscheck: 										## Run slotscheck
	@echo "=> Running slotscheck"
	@uv run slotscheck litestar_granian/
	@echo "=> slotscheck complete"

.PHONY: lint
lint: pre-commit type-check slotscheck						## Run all linting

.PHONY: coverage
coverage:  											## Run the tests and generate coverage report
	@echo "=> Running tests with coverage"
	@uv run pytest tests --cov -n auto
	@uv run coverage html
	@uv run coverage xml
	@echo "=> Coverage report generated"

.PHONY: test
test:  												## Run the tests
	@echo "=> Running test cases"
	@uv run pytest tests
	@echo "=> Tests complete"

.PHONY: test-examples
test-examples:            			              	## Run the examples tests
	@uv run pytest docs/examples

.PHONY: test-all
test-all: test test-examples 						## Run all tests

.PHONY: check-all
check-all: lint test-all coverage                   ## Run all linting, tests, and coverage checks


# =============================================================================
# Docs
# =============================================================================
docs-clean: 										## Dump the existing built docs
	@echo "=> Cleaning documentation build assets"
	@rm -rf docs/_build
	@echo "=> Removed existing documentation build assets"

docs-serve: docs-clean 								## Serve the docs locally
	@echo "=> Serving documentation"
	uv run sphinx-autobuild docs docs/_build/ -j auto --watch litestar_granian --watch docs --watch tests --watch CONTRIBUTING.rst --port 8002

docs: docs-clean 									## Dump the existing built docs and rebuild them
	@echo "=> Building documentation"
	@uv run sphinx-build -M html docs docs/_build/ -E -a -j auto -W --keep-going

.PHONY: docs-linkcheck
docs-linkcheck: 									## Run the link check on the docs
	@uv run sphinx-build -b linkcheck ./docs ./docs/_build -D linkcheck_ignore='http://.*','https://.*'

.PHONY: docs-linkcheck-full
docs-linkcheck-full: 									## Run the full link check on the docs
	@uv run sphinx-build -b linkcheck ./docs ./docs/_build -D linkcheck_anchors=0
