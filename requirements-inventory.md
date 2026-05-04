# EMS Requirements Inventory

This file is the full checklist for packages, tools, images, accounts, and
external services needed to run, test, operate, and demo this repository.

This file is not pip-installable. Use `requirements.txt` for the root local
Python test/development environment.

## Authoritative Dependency Manifests

| Scope | Manifest |
|---|---|
| Root local Python dev/test | `requirements.txt` |
| EMS simulator container | `services/simulator/requirements.txt` |
| KC Modbus MCP container | `external/kc_modbus_mcp/pyproject.toml` |
| KC IoT gateway container | `external/kc_iot_gateway/pyproject.toml` |
| Python tests | `tests/requirements-test.txt` |
| KC dashboard frontend | `external/kc_iot_gateway/dashboard/package.json` |
| Docker services | `docker-compose.yml` |

## Required Host Tools

| Tool | Version / constraint | Purpose |
|---|---:|---|
| Docker Engine | `>=24` | Run all EMS services |
| Docker Compose plugin | `>=2` | `docker compose up -d` workflow |
| Git | `>=2` | Source checkout and submodule/external source tracking |
| curl | `>=7` | Health checks, PostgREST, Grafana reload calls |
| Python | `>=3.12` recommended | Local tests and utility commands |
| pip | `>=23` recommended | Install root/test Python dependencies |

## Docker Images

| Image | Version | Used by |
|---|---:|---|
| `timescale/timescaledb` | `latest-pg15` | `timescaledb` |
| `eclipse-mosquitto` | `2` | `mosquitto` |
| `telegraf` | `1.30` | `gateway`, `ingest`, `kc-gateway`, `kc-ingest` |
| `grafana/grafana-oss` | `11.3.0` | `grafana` |
| `postgrest/postgrest` | `latest` | `query` |
| local build | `services/simulator/Dockerfile` | `simulator` |
| local build | `external/kc_modbus_mcp/Dockerfile` | `kc-modbus-sim`, `kc-mcp-server` |
| local build | `external/kc_iot_gateway/Dockerfile` | `kc-mqtt-sim` |

## Python Runtime Dependencies

### Root Local Dev/Test

Install with:

```bash
python -m pip install -r requirements.txt
```

The root file intentionally covers only local EMS simulator development and
tests. KC external projects keep their own Python environments because their
`pymodbus` constraints differ from the EMS simulator pin.

### `services/simulator`

Runtime: `python:3.11-slim`

```text
fastapi>=0.110,<1.0
uvicorn[standard]>=0.27,<1.0
pymodbus==3.6.9
```

### `external/kc_modbus_mcp`

Runtime: `python:3.12-slim-bookworm`

```text
fastmcp>=3.1.1
pymodbus>=3.7.0,<3.13
pyyaml>=6.0
python-dotenv>=1.0.0
```

Dev extras:

```text
pytest>=8.0
pytest-asyncio>=0.24
```

### `external/kc_iot_gateway`

Runtime: `python:3.12-slim-bookworm`

```text
fastapi>=0.115
uvicorn>=0.34
aiomqtt>=2.3
pymodbus>=3.7.0
aiocoap>=0.4
aiosqlite>=0.20
pyyaml>=6.0
python-dotenv>=1.0.0
httpx>=0.28
websockets>=14.0
fastmcp>=3.1.1
jsonpath-ng>=1.6
```

Dev extras:

```text
pytest>=8.0
pytest-asyncio>=0.24
httpx>=0.28
```

### `tests`

```text
pytest>=8.0
pytest-asyncio>=0.23
httpx>=0.27
psycopg2-binary>=2.9
pymodbus==3.6.9
paho-mqtt>=2.0
```

## Optional Host Tools

| Tool | Version / constraint | Purpose |
|---|---:|---|
| `mosquitto-clients` | `>=2` | Local `mosquitto_sub` / `mosquitto_pub`; optional because the container includes them |
| `postgresql-client` | `>=15` | Local `psql`; optional because the TimescaleDB container includes it |
| `make` | `>=4` | Use `tests/Makefile` on Linux/WSL |

## Cloudflare Demo Tools

| Tool / service | Required when | Notes |
|---|---|---|
| `cloudflared` | Exposing Grafana through Cloudflare Tunnel + Access | Install on a host that can reach Grafana |
| Tailscale | `cloudflared` runs on a bridge host instead of the EMS host | Optional network bridge path |
| Cloudflare account with Zero Trust Access | Public Grafana demo | Needed for Access policy and Tunnel |
| Cloudflare-managed DNS zone | Public Grafana demo | Needed for demo hostname |

## Telegram Alerting

| Secret / setting | Purpose |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Grafana alert notification bot |
| `TELEGRAM_CHAT_ID` | Grafana alert recipient |

## Optional KC Dashboard Frontend Development

Required only for `external/kc_iot_gateway/dashboard` local development.

| Tool | Version / constraint |
|---|---:|
| Node.js | `>=20.19` |
| npm | `>=10` |

Dependencies from `external/kc_iot_gateway/dashboard/package.json`:

```text
@tailwindcss/vite@^4.2.2
class-variance-authority@^0.7.1
clsx@^2.1.1
lucide-react@^0.577.0
react@^19.2.4
react-dom@^19.2.4
recharts@^3.8.0
tailwind-merge@^3.5.0
tailwindcss@^4.2.2
```

Dev dependencies:

```text
@eslint/js@^9.39.4
@types/node@^24.12.0
@types/react@^19.2.14
@types/react-dom@^19.2.3
@vitejs/plugin-react@^6.0.1
eslint@^9.39.4
eslint-plugin-react-hooks@^7.0.1
eslint-plugin-react-refresh@^0.5.2
gh-pages@^6.3.0
globals@^17.4.0
typescript@~5.9.3
typescript-eslint@^8.57.0
vite@^8.0.1
```
