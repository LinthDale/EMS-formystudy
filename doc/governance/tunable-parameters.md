# 可調參數表（Tunable Parameters Registry）

> 依 `project_rules.md` §19。列出 device-service 所有運行期可調 / spec 鎖定的參數。
> **operational** 落於 `config.Settings`（env 可覆寫）；**spec-locked** 由 PRD/ADR 鎖定，放寬走 ADR。
>
> 狀態：✅ 已在 Settings（env 可覆寫）｜🔒 spec-locked（改走 ADR）

## A. Operational（env 可覆寫，`config.Settings`）

| 參數 | env var | 預設 | 單位 | 模組 | FR/ADR | 狀態 | 備註 |
|------|---------|------|------|------|--------|------|------|
| LLM provider | `LLM_PROVIDER` | mock | — | config | FR-305 | ✅ | mock/anthropic/openai/local |
| LLM model | `LLM_MODEL` | (provider default) | — | config | — | ✅ | 須在 pricing 表內否則 cost 0（warn） |
| LLM API key | `LLM_API_KEY` | "" | — | config | — | ✅ | secret |
| LLM base URL | `LLM_BASE_URL` | None | — | config | FR-342 | ✅ | allowlist 驗證 |
| Provider domain allowlist | `LLM_PROVIDER_DOMAIN_ALLOWLIST` | api.anthropic.com,api.openai.com,localhost,127.0.0.1,host.docker.internal | — | config | FR-342 | ✅ | |
| **LLM 輸出 max_tokens** | `LLM_MAX_OUTPUT_TOKENS` | 1024 | tokens | config → factory → providers; budget reserve | FR-329 | ✅ | **耦合**：同時為 provider max_tokens 與 budget reservation 輸出上界 |
| **Reservation 輸入估算** | `LLM_RESERVE_INPUT_TOKENS` | 4000 | tokens | config → discovery → budget_ledger | FR-329 | ✅ | budget reservation 輸入估算 |
| **Provider/model pricing 覆寫** | `LLM_PRICING_JSON` | "" | JSON | config → discovery → budget_ledger | FR-329 | ✅ | `{model:[in_per_1M,out_per_1M]}` 合併於內建表 |
| **信心門檻** | `LLM_CONFIDENCE_THRESHOLD` | 0.9 | ratio | config → classifier | FR-303 | ✅ | PRD: >此值自動 confirmed |
| **LLM retry 次數** | `LLM_RETRIES` | 3 | 次 | config → classifier | FR-312 | ✅ | |
| **classifier cache 上限** | `LLM_CACHE_MAX` | 4096 | entries | config → classifier | FR-316 | ✅ | |
| **Budget warn ratio** | `BUDGET_WARN_RATIO` | 0.8 | ratio | config; evaluate_budget | FR-319 | ✅ | 設定就位；80% Telegram alert 串接屬 Phase 1.4 告警（未接） |
| 月預算 | `LLM_MONTHLY_BUDGET_USD` | 20.0 | USD | config | FR-319/NFR | ✅ | |
| **Dedupe 視窗** | `DEDUPE_WINDOW_S` | 60.0 | s | config → mqtt_subscriber → AdmissionGate | FR-326 | ✅ | |
| **Rate limit / 視窗** | `RATE_LIMIT_PER_MIN` / `RATE_WINDOW_S` | 60 / 60.0 | /min, s | config → mqtt_subscriber → AdmissionGate | FR-325 | ✅ | |
| **MQTT reconnect 延遲** | `MQTT_RECONNECT_DELAY_S` | 5.0 | s | config → mqtt_subscriber | — | ✅ | |
| **MQTT 訂閱 topic** | `MQTT_SUBSCRIPTIONS` | ems/+/+/measurements,factory/sensor/+ | csv | config → mqtt_subscriber | §8.5 | ✅ | 逗號分隔；放寬訂閱範圍仍受 parser deny-by-default 約束 |
| **Provider 預設 model（anthropic/openai/local）** | `LLM_DEFAULT_MODEL_ANTHROPIC` / `LLM_DEFAULT_MODEL_OPENAI` / `LLM_DEFAULT_MODEL_LOCAL` | claude-haiku-4-5 / gpt-4o-mini / qwen2.5 | — | config → factory | FR-305 | ✅ | factory 不再是第二 config source；LLM_MODEL 設定時覆寫 |
| **Local provider base URL** | `LLM_LOCAL_BASE_URL` | http://host.docker.internal:11434/v1 | — | config → factory | FR-305 | ✅ | Ollama 端點 |
| MQTT host/port/enabled | `MQTT_HOST`/`MQTT_PORT`/`MQTT_ENABLED` | mosquitto/1883/false | — | config | §8.5 | ✅ | |
| DB host/port/name/passwords | `DB_HOST`/`DB_PORT`/`DB_NAME`/`DB_AI_PASSWORD`/`DB_OPS_PASSWORD` | timescaledb/5432/ems | — | config | ADR-017 | ✅ | |
| API keys (OPS/INGEST/AI) | `OPS_API_KEY`/`INGEST_API_KEY`/`AI_API_KEY` | "" | — | config | FR-310 | ✅ | secret |

> 模組仍保留 `_MAX_CLASSIFY_TOKENS` / `RESERVE_*` / `CONFIDENCE_THRESHOLD` / `WARN_RATIO` / `DEDUPE_WINDOW` / `RATE_LIMIT` / `RATE_WINDOW` / `RECONNECT_DELAY` 等模組常數，作為**函式/建構子的 default**（單元測試與獨立呼叫用）；production 路徑（main lifespan / discovery / mqtt_subscriber）一律以 `Settings` 值覆寫。`config` 為單一真相。

## B. Security / spec-locked（登錄但放寬走 ADR）

| 參數 | 值 | 模組 | FR/ADR | 狀態 |
|------|----|------|--------|------|
| MQTT payload 上限 | 16 KB | topic_parser `MAX_PAYLOAD_BYTES` | FR-323 | 🔒 |
| 欄位數上限 | 64 | topic_parser / sanitizer `MAX_FIELDS` | FR-324/328 | 🔒 |
| 樣本筆數上限 | 20 | sanitizer `MAX_SAMPLES` | FR-328 | 🔒 |
| reasoning 字元上限 | 500 | output_validator `MAX_REASONING` | FR-333 | 🔒 |
| device_id / signal_name regex | `^[a-zA-Z0-9_-]{1,64}$` | topic_parser / models | FR-322 | 🔒 |

> spec-locked 值若未來要調整（放寬），必須開 ADR；不可隨意 env 覆寫降低安全界限。