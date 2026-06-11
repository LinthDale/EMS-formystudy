.PHONY: install unit integration contract all

PYTHON ?= python3

install:
	$(PYTHON) -m pip install -r requirements-test.txt

# Unit tests — no Docker required
unit:
	$(PYTHON) -m pytest tests/unit -v

# Integration tests — requires `docker compose up -d`
integration:
	$(PYTHON) -m pytest tests/integration -v -m integration

# API contract gates — no Docker required (imports the device-service ASGI app)
# Needs device-service deps: pip install -r services/device-service/requirements.txt PyYAML
contract:
	$(PYTHON) -m pytest tests/contract -v

# All tests
all:
	$(PYTHON) -m pytest tests/ -v

# Unit tests only, with coverage report
coverage:
	$(PYTHON) -m pytest tests/unit --cov=services/simulator/src --cov-report=term-missing -v
