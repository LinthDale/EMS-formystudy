# EMS BFF (PRD-0005 §9 GATE-1) — the ONLY channel between the SPA and backends.
# Same toolchain as device-service (python:3.11-slim + FastAPI/uvicorn).
FROM python:3.11-slim AS base
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bff ./bff
COPY config ./config

# --- test stage: docker build --target test -t ems-bff-test services/bff ---
FROM base AS test
COPY requirements-dev.txt .
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY tests ./tests
COPY pytest.ini .
CMD ["python", "-m", "pytest", "tests", "-v"]

# --- runtime (default) ---
FROM base AS runtime
EXPOSE 8003
CMD ["uvicorn", "bff.main:app", "--host", "0.0.0.0", "--port", "8003"]
