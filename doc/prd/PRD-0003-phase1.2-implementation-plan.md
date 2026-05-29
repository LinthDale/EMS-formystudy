# PRD-0003 Phase 1.2 實作計畫 — device-service 雛型

| 欄位 | 內容 |
|------|------|
| 對應 PRD | [PRD-0003](PRD-0003-Device-Registry-Auto-Discovery.md) §12.2 |
| 決策紀錄 | [decision-log](../governance/decision-log.md) DL-008 |
| 狀態 | Planned（2026-05-29） |
| 前置 | Phase 1.1 已完成（migrations 003~011 + ADR-009~018，schema 已套用 dev DB） |
| 對應實作 | services/device-service（待建） |

> 本檔為實作層任務計畫，不重述 PRD spec；spec 衝突以 PRD-0003 為準。

## 範圍

**做**：FastAPI 骨架、ADR-017 雙連線池、`/healthz`、X-API-Key 三通道、CRUD + confirm/override/reject、LLMProvider 抽象（含 SanitizedSample / sanitizer / output_validator）、MockProvider、AnthropicProvider（`claude-haiku-4-5`）、OpenAIProvider（程式 + unit，不跑 Ollama E2E）、單元覆蓋率 ≥ 90%。

**不做（後續 Phase）**：MQTT / auto-discovery（1.3）；budget ledger gate、correction loop、L2 guardrail、MCP server、`/ai-feedback`·`/admin/budget`·`/corrections` endpoints、Grafana / alert（1.4）；openapi.yml / 容器速查表同步（§15.C，1.4 完成才觸發）。

## 技術選型

- Async stack：FastAPI + `asyncpg`（對應 ADR-017 雙池）+ pydantic v2 + pydantic-settings + `anthropic` SDK
- DB：asyncpg 兩個 pool（per-role login DSN，`device_service_ai` / `device_service_ops`）；**只用參數化查詢**；OPS 的 confirm/override/reject 在交易開頭 `SET LOCAL device_service.freeze_override = $request_id`（打通 migration 010/011 的 freeze trigger）
- AnthropicProvider：`claude-haiku-4-5`（PRD §14 待釐清的 haiku vs sonnet 抽樣比較，留待接真 API 時做）；structured output + prompt caching；unit test 注入 fake client，不需真 API key
- 測試 runtime：throwaway `python:3.11-slim` 接 `ems_default` 網路 / `timescaledb` service（見 reference：EMS integration test runtime）

## 檔案結構 `services/device-service/`

```
Dockerfile, requirements.txt
src/
  main.py            FastAPI app + lifespan(初始化雙池) + router
  config.py          pydantic-settings；LLM_BASE_URL allowlist 驗證(FR-342)
  db.py              asyncpg get_ai_pool/get_ops_pool；freeze_override helper；healthz ping
  auth.py            X-API-Key 三通道 dependency + §8.6.1 權限矩陣
  models.py          pydantic DeviceIn/Out, SignalIn/Out, ClassifyResult schemas
  repositories/device_repo.py, signal_repo.py    參數化 CRUD（寫走 ops、ai_* 走 ai）
  llm/
    types.py         FieldSummary/CorrectionContext/SanitizedSample/SignalSuggestion/ClassificationResult (frozen dataclass)
    provider.py      LLMProvider Protocol（入參強制 SanitizedSample）
    mock_provider.py / anthropic_provider.py / openai_provider.py / factory.py
  sanitizer.py       白名單 + PII 剝除 + 欄位/樣本上限 (FR-328)
  output_validator.py 長度 + 黑名單字 + raw payload substring (FR-333)
  routes/devices.py, signals.py, health.py
tests/unit/test_device_service_*.py          （無 DB，衝 90%）
tests/integration/test_device_service_*.py   （throwaway container 連 DB）
docker-compose.yml + ems-device-service（REST :8002）
```

## TDD 任務順序（每項 RED → GREEN，先測後做）

1. `llm/types.py` + `provider.py` — dataclass + Protocol（合約測試）
2. `sanitizer.py` — FR-328：字串 / PII 剝除、欄位 ≤ 64、樣本 ≤ 20、property test（substring 不外洩）
3. `output_validator.py` — FR-333：長度截斷、黑名單字、raw payload 反射
4. `mock_provider.py` — deterministic heuristic（topic + fields → device_type / signals / confidence）
5. `config.py` — env 載入 + LLM_BASE_URL allowlist 驗證（FR-342）
6. `anthropic_provider.py`（haiku-4-5）+ `openai_provider.py` — mock client unit test；prompt caching
7. `factory.py` — `LLM_PROVIDER` 切換（mock / anthropic / openai / local）
8. `db.py` — 雙池 + healthz + freeze_override helper（integration）
9. `auth.py` — 三通道 + 權限矩陣（unit 矩陣 + integration 403/401）
10. routes（CRUD + confirm/override/reject + healthz）— integration；驗證 OPS token 能合法改凍結裝置、AI 通道不能
11. Dockerfile + requirements + compose 服務，整鏈跑通
12. 覆蓋率 ≥ 90%（pytest --cov，純函數模組為主）

## 驗證

- `pytest tests/unit/test_device_service_*.py --cov=services/device-service/src`（≥ 90%）
- `pytest tests/integration/test_device_service_*.py`（throwaway container）
- `docker compose up -d ems-device-service` → `curl :8002/healthz` 兩池綠
- 既有 schema / pipeline 測試不受影響

## 建議起步

#1~#4（純函數核心，TDD、不依賴 DB），做完一批 review 後再往 DB / 路由推進。