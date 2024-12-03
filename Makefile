.PHONY: install lint

install:
	uv sync
	uv pip install -e .

lint:
	uv run ruff format ttcli/
	uv run ruff check ttcli/
	uv run pyright ttcli/
