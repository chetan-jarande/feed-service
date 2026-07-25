PYTHON_VERSION ?= 3.12
VENV_ROOT ?= ./.venv
HOST ?= 0.0.0.0
PORT ?= 8080

.DEFAULT_GOAL := help

.PHONY: help venv deps dev run run-reload test lint format clean

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

venv: ## Create the uv virtual environment
	uv venv --python $(PYTHON_VERSION) $(VENV_ROOT)

deps: ## Install runtime dependencies only
	uv sync --no-dev

dev: ## Install runtime + dev dependencies
	uv sync

run: ## Start the API server
	uv run uvicorn main:app --host $(HOST) --port $(PORT)

run-reload: ## Start with auto-reload
	uv run uvicorn main:app --reload --port $(PORT)

test: ## Run the test suite
	uv run pytest -vvv

lint: ## Run ruff checks
	uv run ruff check .

format: ## Auto-format with ruff
	uv run ruff format .

clean: ## Remove caches and virtual environment
	rm -rf __pycache__ .venv .pytest_cache .ruff_cache .mypy_cache
