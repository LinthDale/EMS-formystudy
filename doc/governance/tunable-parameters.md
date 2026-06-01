# 可調參數表（Tunable Parameters Registry）

> 依 `project_rules.md` §19。列出 device-service 所有運行期可調 / spec 鎖定的參數。
> **operational** 應落於 `config.Settings`（env 可覆寫）；**spec-locked** 由 PRD/ADR 鎖定，放寬走 ADR。
>
> 狀態圖例：✅ 已在 Settings（env 可覆寫）｜🟧 目前硬編，**待遷移** Settings｜🔒 spec-locked（改走 ADR）

## A. Operational（應 env 可覆寫）

| 參數 | env var | 預設 | 單位 | 模組 | FR/ADR | 狀態 | 備註 |
|------|---------|------|------|------|--------|------|------|
| LLM provider | `LLM_PROVIDER` | mock | — | config | FR-305 | ✅ | mock/anthropic/openai/local |
| LLM model | `LLM_MODEL` | (provider default) | — | config | — | ✅ | 須在 pricing 表內否則 budget 不計 |
| LLM API key | `LLM_API_KEY` | "" | — | config | — | ✅ | secret |
| LLM base URL | `LLM_BASE_URL` | None | — | config | FR-342 | ✅ | allowlist 驗證 |
| Provider domain allowlist | `LLM_PROVIDER_DOMAIN_ALLOWLIST` | api.anthropic.com,api.openai.com,localhost,127.0.0.1,host.docker.internal | — | config | FR-342 | ✅ | |
| 月預算 | `LLM_MONTHLY_BUDGET_USD` | 20.0 | USD | config | FR-319/NFR | ✅ | |
| MQTT host/port/enabled | `MQTT_HOST`/`MQTT_PORT`/`MQTT_ENABLED` | mosquitto/1883/false | — | config | §8.5 | ✅ | |
| DB host/port/name/passwords | `DB_HOST`/`DB_PORT`/`DB_NAME`/`DB_AI_PASSWORD`/`DB_OPS_PASSWORD` | timescaledb/5432/ems | — | config | ADR-017 | ✅ | |
| API keys (OPS/INGEST/AI) | `OPS_API_KEY`/`INGEST_API_KEY`/`AI_API_KEY` | "" | — | config | FR-310 | ✅ | secret |
| LLM 輸出 max_tokens | — | 1024 | tokens | anthropic_provider `_MAX_CLASSIFY_TOKENS` / openai_provider `_MAX_OUTPUT_TOKENS` | — | 🟧 | **耦合**：須 == RESERVE_OUTPUT_TOKENS |
| Reservation 估算（輸入） | — | 4000 | tokens | budget_ledger `RESERVE_INPUT_TOKENS` | FR-329 | 🟧 | budget reservation 上界 |
| Reservation 估算（輸出） | — | 1024 | tokens | budget_ledger `RESERVE_OUTPUT_TOKENS` | FR-329 | 🟧 | **耦合**：== max_tokens |
| Provider/model pricing | — | (內建表) | USD/1M tok | budget_ledger `_PRICING` | FR-329 | 🟧 | 未定價 model→cost 0（僅 warn） |
| 信心門檻 | — | 0.9 | ratio | classifier `CONFIDENCE_THRESHOLD` | FR-303 | 🟧 | PRD: >0.9；default 鎖 spec |
| LLM retry 次數 | — | 3 | 次 | classifier `DEFAULT_RETRIES` | FR-312 | 🟧 | |
| classifier cache 上限 | — | 4096 | entries | classifier `cache_max` | FR-316 | 🟧 | |
| Budget warn ratio | — | 0.8 | ratio | budget_ledger `WARN_RATIO` | FR-319 | 🟧 | 80% alert |
| Dedupe 視窗 | — | 60 | s | discovery `DEDUPE_WINDOW` | FR-326 | 🟧 | |
| Rate limit / 視窗 | — | 60 / 60 | /min, s | discovery `RATE_LIMIT`/`RATE_WINDOW` | FR-325 | 🟧 | |
| MQTT reconnect 延遲 | — | 5.0 | s | mqtt_subscriber `RECONNECT_DELAY` | — | 🟧 | |

## B. Security / spec-locked（登錄但放寬走 ADR）

| 參數 | 值 | 模組 | FR/ADR | 狀態 |
|------|----|------|--------|------|
| MQTT payload 上限 | 16 KB | topic_parser `MAX_PAYLOAD_BYTES` | FR-323 | 🔒 |
| 欄位數上限 | 64 | topic_parser / sanitizer `MAX_FIELDS` | FR-324/328 | 🔒 |
| 樣本筆數上限 | 20 | sanitizer `MAX_SAMPLES` | FR-328 | 🔒 |
| reasoning 字元上限 | 500 | output_validator `MAX_REASONING` | FR-333 | 🔒 |
| device_id / signal_name regex | `^[a-zA-Z0-9_-]{1,64}$` | topic_parser / models | FR-322 | 🔒 |

## 待辦（§19 合規遷移）

A 區標 🟧 的參數目前為模組硬編，待遷移至 `config.Settings`（env 可覆寫，spec 值為 default）。遷移時保持 max_tokens == RESERVE_OUTPUT_TOKENS 的耦合（建議共用一個 setting）。spec-locked（0.9 / 0.8 / 60 / 3 等 FR 鎖定者）遷移後 env 可覆寫但放寬須有 ADR 依據。