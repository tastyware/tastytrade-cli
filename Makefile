.PHONY: install lint

install:
	uv sync
	uv pip install .

lint:
	uv run ruff check ttcli/
	uv run pyright ttcli/
