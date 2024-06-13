SHELL := /bin/bash
# =============================================================================
# Variables
# =============================================================================

.DEFAULT_GOAL:=help
.ONESHELL:
USING_PDM		=	$(shell grep "tool.pdm" pyproject.toml && echo "yes")
ENV_PREFIX		=.venv/bin/
VENV_EXISTS		=	$(shell python3 -c "if __import__('pathlib').Path('.venv/bin/activate').exists(): print('yes')")
PDM_OPTS 		?=
PDM 			?= 	pdm $(PDM_OPTS)

.EXPORT_ALL_VARIABLES:


.PHONY: help
help: 		   										## Display this help text for Makefile
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m\n"} /^[a-zA-Z0-9_-]+:.*?##/ { printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2 } /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } ' $(MAKEFILE_LIST)



# =============================================================================
# Developer Utils
# =============================================================================
install-hatch: 										## Install Hatch
	@sh ./scripts/install-hatch.sh ~/.local/bin/

configure-hatch: 										## Configure Hatch defaults
	@hatch config set dirs.env.virtual .direnv
	@hatch config set dirs.env.pip-compile .direnv

upgrade-hatch: 										## Update Hatch, UV, and Ruff
	@hatch self update

destroy-venv: 											## Destroy the virtual environment
	@hatch env prune
	@hatch env remove lint
	@rm -Rf .venv
	@rm -Rf .direnv

.PHONY: upgrade
upgrade:       										## Upgrade all dependencies to the latest stable versions
	@echo "=> Updating all dependencies"
	@hatch run lint:pre-commit autoupdate
	@echo "=> Updated Pre-commit"

install: 										## Install the project and all dependencies
	@if [ "$(VENV_EXISTS)" ]; then echo "=> Removing existing virtual environment"; $(MAKE) destroy-venv; fi
	@$(MAKE) clean
	@if ! hatch --version > /dev/null; then echo '=> Installing `hatch` with standalone installation'; $(MAKE) install-hatch ; fi
	@echo "=> Creating Python environments..."
	@$(MAKE) configure-hatch
	@hatch env create local
	@echo "=> Install complete! Note: If you want to re-install re-run 'make install'"



clean: 												## Cleanup temporary build artifacts
	@echo "=> Cleaning working directory"
	@if [ "$(USING_PDM)" ]; then $(PDM) run pre-commit clean; fi
	@rm -rf .pytest_cache .ruff_cache .hypothesis build/ -rf dist/ .eggs/
	@find . -name '*.egg-info' -exec rm -rf {} +
	@find . -name '*.egg' -exec rm -f {} +
	@find . -name '*.pyc' -exec rm -f {} +
	@find . -name '*.pyo' -exec rm -f {} +
	@find . -name '*~' -exec rm -f {} +
	@find . -name '__pycache__' -exec rm -rf {} +
	@find . -name '.ipynb_checkpoints' -exec rm -rf {} +
	@rm -rf .coverage coverage.xml coverage.json htmlcov/ .pytest_cache tests/.pytest_cache tests/**/.pytest_cache .mypy_cache
	$(MAKE) docs-clean

destroy: 											## Destroy the virtual environment
	@rm -rf .venv

# =============================================================================
# Tests, Linting, Coverage
# =============================================================================
.PHONY: lint
lint: 												## Runs pre-commit hooks; includes ruff linting, codespell, black
	@echo "=> Running pre-commit process"
	@$(ENV_PREFIX)pre-commit run --all-files
	@echo "=> Pre-commit complete"

.PHONY: coverage
coverage:  											## Run the tests and generate coverage report
	@echo "=> Running tests with coverage"
	@$(ENV_PREFIX)pytest tests --cov=litestar_asyncg
	@$(ENV_PREFIX)coverage html
	@$(ENV_PREFIX)coverage xml
	@echo "=> Coverage report generated"

.PHONY: test
test:  												## Run the tests
	@echo "=> Running test cases"
	@$(ENV_PREFIX)pytest tests
	@echo "=> Tests complete"


.PHONY: check-all
check-all: lint test coverage 						## Run all linting, tests, and coverage checks

# =============================================================================
# Docs
# =============================================================================
.PHONY: docs-install
docs-install: 										## Install docs dependencies
	@echo "=> Installing documentation dependencies"
	@$(PDM) install --group docs
	@echo "=> Installed documentation dependencies"

docs-clean: 										## Dump the existing built docs
	@echo "=> Cleaning documentation build assets"
	@rm -rf docs/_build
	@echo "=> Removed existing documentation build assets"

docs-serve: docs-clean 								## Serve the docs locally
	@echo "=> Serving documentation"
	$(ENV_PREFIX)sphinx-autobuild docs docs/_build/ -j auto --watch litestar_asyncg --watch docs --watch tests --watch CONTRIBUTING.rst --port 8002

docs: docs-clean 									## Dump the existing built docs and rebuild them
	@echo "=> Building documentation"
	@$(ENV_PREFIX)sphinx-build -M html docs docs/_build/ -E -a -j auto --keep-going
