.PHONY: venv lint

venv:
	python -m venv .venv
	.venv/bin/pip install -r requirements.txt
	.venv/bin/pip install -e .

lint:
	isort --check --diff ttcli/
	flake8 --count --show-source --statistics ttcli/
	mypy -p ttcli/
