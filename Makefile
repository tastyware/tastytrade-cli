.PHONY: clean venv test

clean:
	find . -name '*.py[co]' -delete

venv:
	python -m venv --prompt 'twcli' env
	env/bin/pip install -r requirements.txt

test:
	isort --check --diff twcli/ tests/
	flake8 --count --show-source --statistics --ignore=E501 twcli/ tests/
	python -m pytest --cov=twcli --cov-report=term-missing tests/
