.PHONY: install unit integration all

PYTHON ?= python3

install:
	$(PYTHON) -m pip install -r requirements-test.txt

# Unit tests — no Docker required
unit:
	$(PYTHON) -m pytest tests/unit -v

# Integration tests — requires `docker compose up -d`
integration:
	$(PYTHON) -m pytest tests/integration -v -m integration

# All tests
all:
	$(PYTHON) -m pytest tests/ -v

# Unit tests only, with coverage report
coverage:
	$(PYTHON) -m pytest tests/unit --cov=services/simulator/src --cov-report=term-missing -v
