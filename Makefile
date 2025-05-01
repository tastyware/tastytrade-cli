.PHONY: install lint

install:
	uv sync

lint:
	uv run ruff format ttcli/
	uv run ruff check ttcli/
	uv run pyright ttcli/
