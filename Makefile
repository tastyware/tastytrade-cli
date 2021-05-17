.PHONY: clean venv test

clean:
	find . -name '*.py[co]' -delete

venv:
	python -m venv --prompt 'tw' env
	env/bin/pip install -r requirements.txt
	env/bin/pip install -r requirements-dev.txt

test:
	isort --check --diff src/ tests/
	flake8 --count --show-source --statistics --ignore=E501 src/ tests/
	python -m pytest --cov=src --cov-report=term-missing tests/
