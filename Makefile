# Basewright -- development entry points.
# Every target here is also what CI runs, so a green `make all` means a green pull request.

PYTHON ?= python
VENV   ?= .venv

.DEFAULT_GOAL := help

.PHONY: help
help:  ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
	    | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[1m%-14s\033[0m %s\n", $$1, $$2}'

.PHONY: install
install:  ## Install the package and development dependencies
	$(PYTHON) -m pip install -e ".[dev]"

.PHONY: lint
lint: ruff mypy yamllint  ## Run every static check

.PHONY: ruff
ruff:  ## Lint and format-check the Python core
	$(PYTHON) -m ruff check basewright test tools
	$(PYTHON) -m ruff format --check basewright test tools

.PHONY: format
format:  ## Apply formatting fixes
	$(PYTHON) -m ruff check --fix basewright test tools
	$(PYTHON) -m ruff format basewright test tools

.PHONY: mypy
mypy:  ## Type-check the Python core
	$(PYTHON) -m mypy

.PHONY: yamllint
yamllint:  ## Lint every YAML file in the repository
	$(PYTHON) -m yamllint -s .

.PHONY: test
test:  ## Run the unit and golden test suites with coverage
	$(PYTHON) -m pytest --cov --cov-report=term-missing

.PHONY: schema
schema:  ## Validate every profile against the profile JSON Schema
	$(PYTHON) -m basewright.profiles --all profiles
	$(PYTHON) -m pytest test/unit -k schema

.PHONY: guard
guard:  ## Fail if an engine name leaks into the engine-agnostic core
	$(PYTHON) -m pytest test/unit -k engine_names

.PHONY: assets
assets:  ## Regenerate the documentation diagrams and terminal captures
	$(PYTHON) tools/render_assets.py

.PHONY: assets-check
assets-check:  ## Fail if a committed diagram or capture is stale
	$(PYTHON) tools/render_assets.py --check

.PHONY: golden
golden:  ## Regenerate the golden plans, then read the diff -- it is the review
	$(PYTHON) tools/render_goldens.py

.PHONY: golden-check
golden-check:  ## Fail if a committed golden plan is stale
	$(PYTHON) tools/render_goldens.py --check

.PHONY: molecule
molecule:  ## Run the Ansible role tests in containers (slow)
	$(PYTHON) -m molecule test

.PHONY: all
all: lint test assets-check golden-check  ## Everything CI runs on a pull request, except molecule

.PHONY: clean
clean:  ## Remove build and cache artifacts
	rm -rf build dist .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +
