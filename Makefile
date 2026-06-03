.PHONY: sync test lint format format-check typecheck check precommit build clean

# Install dev tooling against the locked environment.
sync:
	uv sync --extra dev --locked

# Run the default (non-integration) suite with coverage.
test:
	uv run pytest -m "not integration" --cov=pyxschem --cov-report=term-missing

lint:
	uv run ruff check src/ tests/

format:
	uv run ruff format src/ tests/

format-check:
	uv run ruff format --check src/ tests/

typecheck:
	uv run pyright src/

# Run every pre-commit hook over the whole tree.
precommit:
	uvx pre-commit run --all-files

# The full gate CI enforces.
check: lint format-check typecheck test

build:
	uv build

clean:
	rm -rf dist build .pytest_cache .ruff_cache
