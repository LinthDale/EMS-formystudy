# 可調參數表（Tunable Parameters Registry）

## 量測本地循環容量（2026-11-13，ADR-045）

既有權威為[Delta config](../../services/delta/delta_device/config.py)的delivery與outbox設定；改檔停舊程序備份後重啟。未新增env／調參入口，也不把量測政策寫進device-service.toml。

| 參數／規則 | 預設／單位 | 範圍／性質 |
|---|---|---|
| queue_limit | 10000筆 | 1..1000000，既有operational；wire2時包含quarantine，滿時最舊淘汰 |
| delivery.audit_limit | 600000筆 | 1..6000000，既有operational；滿時最舊audit前綴回收，含對應queue |
| delivery.queue_byte_limit | 4294967296 bytes | 65536..68719476736，既有operational；SQLite主檔pages上限，journal／主機空間另計 |
| 最新優先淘汰規則 | 固定drop_oldest | spec-locked，依[ADR-045](../adr/ADR-045-newest-first-edge-retention.md)，不是可從遠端修改的config key |
| 本地schema／wire | 3／2 | spec-locked；metadata.retention摘要≤4096字元；不是完整缺口歷史；來源奈秒int64且微秒對齊 |

筆數cap調小可能立即淘汰更多舊量測，需維運者核定並備份；bytes上限若小於既有主檔頁數會安全拒開，不自動縮檔或先刪資料。容量淘汰不變成central ACK，中央retention與控制稽核不受這些值支配。

> **人類調參主檔：[`config/device-service.toml`](../../config/device-service.toml)**（有完整註解；改檔後重啟服務生效）。本表為總覽 / 稽核索引。
> 載入優先序（高→低）：環境變數 > `.env` > `device-service.toml` > 程式 default。機密（DB 密碼 / API keys）只放 `.env`。
>
> 依 `project_rules.md` §19。列出 device-service 所有運行期可調 / spec 鎖定的參數。
> **operational** 落於 `config.Settings`（env 可覆寫）；**spec-locked** 由 PRD/ADR 鎖定，放寬走 ADR。
>
> 狀態：✅ 已在 Settings（env 可覆寫）｜🔒 spec-locked（改走 ADR）

## Delta v2 reliable delivery（ADR-043，2026-11-12）

Delta／receiver 為獨立原生服務，沿既有 JSON `load_config/validate_delivery` 與 `receiver.validate_config` 集中載入，不把此服務的參數混入 device-service.toml。人類主檔為 [edge範本](../../services/delta/config/reliable-field.example.json)／[receiver範本](../../services/edge-receiver/deploy/receiver.example.json)，機密僅 env／唯讀私鑰；Owner EMS。改 JSON 後重啟該服務，不能覆寫凍結長測。

| 鍵／介面 | 預設／界線 | 性質與耦合 |
|---|---|---|
| delivery.protocol | 明示2；無此節仍舊v1 | spec-locked；新獨立檔／topic，禁止同樣本雙路 |
| delivery.gateway_id／stream_id／config_revision／profile_version | 無預設，須權威登錄 | spec-locked；與device_id及queue metadata一致，已有queue不可重綁 |
| delivery.queue_byte_limit | 4GiB；64KiB..64GiB | operational；SQLite max_page_count整檔上限，含queue/quarantine/audit，非7天容量保證 |
| queue_limit／delivery.audit_limit | 10000／600000；上限1000000／6000000 | operational；audit不自動清除，任一滿停新採樣、保留pending與quarantine |
| delivery.ack_timeout_seconds | 30；1..120秒 | operational；超時保留樣本，退避後重新握手；不放寬ACK身份／hash驗證 |
| receiver.db_timeout_seconds | 5；1..30秒 | operational；DB連線／命令deadline；逾時只retryable |
| dsn_env／generation_file | 必填 env 名／DB外UUID檔 | deployment；無fallback，PITR換generation並強制重連 |
| receiver.bindings | ≤128 gateway，每個≤8 device | spec-locked；綁stream/revision/profile及半開生效時間，不是已支援8台bus |
| sample／wire／session bytes | 1024／65536／1024 | spec-locked；JSON深度≤8、sample≤32/batch、欄位固定、finite 0..1e15 |
| sender batch／inflight／rate | 1／1／≤2 batch/s | 本階段spec-locked；不宣稱20 samples/s；edge loop另有約1秒等待 |
| receiver batch／sample rate | ≤2 batch/s；40 samples/s，burst64 | spec-locked；各自token bucket，入站queue≤64，超額不回committed |
| session request／retry | ≤1/s；重送退避1..60s含jitter | spec-locked；reconnect先清舊batch/session，SUBACK後握手 |
| source time／receipt retention | DB UTC前90天至後120秒；retention至少max(now,sampled)+91天 | spec-locked；本階段不自動purge，仍須中央磁碟監控 |
| window bucket／rich snapshot | 300秒／≤16KiB | spec-locked；window先持久化，尚未sealed；rich snapshot僅本地保留至ACK，中央四欄canonical不冒稱詳細三相 |


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
| **Budget warn ratio** | `BUDGET_WARN_RATIO` | 0.8 | ratio | config; evaluate_budget; **Grafana alert（PRD-0004 FR-400/402）** | FR-319 | ✅ | 80% Telegram 告警**已接線**（alert group `EMS-預算告警`，L1+guardrail 各 warn/exhausted）。⚠️ Grafana SQL 無法讀 env，0.8 **硬編於 `rules.yaml`**；改 env 須同步該檔 |
| 月預算 | `LLM_MONTHLY_BUDGET_USD` | 20.0 | USD | config | FR-319/NFR | ✅ | |
| **Dedupe 視窗** | `DEDUPE_WINDOW_S` | 60.0 | s | config → mqtt_subscriber → AdmissionGate | FR-326 | ✅ | |
| **Rate limit / 視窗** | `RATE_LIMIT_PER_MIN` / `RATE_WINDOW_S` | 60 / 60.0 | /min, s | config → mqtt_subscriber → AdmissionGate | FR-325 | ✅ | |
| **MQTT reconnect 延遲** | `MQTT_RECONNECT_DELAY_S` | 5.0 | s | config → mqtt_subscriber | — | ✅ | |
| **MQTT 訂閱 topic** | `MQTT_SUBSCRIPTIONS` | ems/+/+/measurements,factory/sensor/+ | csv | config → mqtt_subscriber | §8.5 | ✅ | 逗號分隔；放寬訂閱範圍仍受 parser deny-by-default 約束 |
| **Provider 預設 model（anthropic/openai/local）** | `LLM_DEFAULT_MODEL_ANTHROPIC` / `LLM_DEFAULT_MODEL_OPENAI` / `LLM_DEFAULT_MODEL_LOCAL` | claude-haiku-4-5 / gpt-4o-mini / qwen2.5 | — | config → factory | FR-305 | ✅ | factory 不再是第二 config source；LLM_MODEL 設定時覆寫 |
| **Local provider base URL** | `LLM_LOCAL_BASE_URL` | http://host.docker.internal:11434/v1 | — | config → factory | FR-305 | ✅ | Ollama 端點 |
| **L2 guardrail provider** | `GUARDRAIL_PROVIDER` | mock | — | config → factory → classifier | FR-338 | ✅ | mock/openai/local；獨立於 L1。非 mock 時 L2 成本由 `GUARDRAIL_MONTHLY_BUDGET_USD` 計量（FR-340） |
| **L2 guardrail model** | `GUARDRAIL_MODEL` | (guardrail default) | — | config → factory | FR-338 | ✅ | 留空套 `GUARDRAIL_DEFAULT_MODEL_OPENAI` |
| **L2 guardrail API key** | `GUARDRAIL_API_KEY` | "" | — | config → factory | FR-338 | ✅ | secret；空則沿用 `LLM_API_KEY` |
| **L2 guardrail base URL** | `GUARDRAIL_BASE_URL` | None | — | config → factory | FR-342 | ✅ | allowlist 驗證（同 L1） |
| **L2 guardrail 預設 model** | `GUARDRAIL_DEFAULT_MODEL_OPENAI` | gpt-4o-mini | — | config → factory | FR-338 | ✅ | injection 判斷用最便宜 model |
| **L2 guardrail 輸出 max_tokens** | `GUARDRAIL_MAX_OUTPUT_TOKENS` | 256 | tokens | config → factory → LLMGuardrail | FR-338 | ✅ | verdict JSON 短 |
| **L2 guardrail 月預算** | `GUARDRAIL_MONTHLY_BUDGET_USD` | 10.0 | USD | config → discovery_pipeline → budget_ledger(provider='guardrail') | FR-340 | ✅ | 達 100% → 分類全停（連 L1）走 fallback |
| **L2 guardrail reserve 輸入估算** | `GUARDRAIL_RESERVE_INPUT_TOKENS` | 8000 | tokens | config → discovery_pipeline → budget_ledger | FR-340 | ✅ | 每 call 上界；reserve = ×2（pre+post） |
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

## C. BFF（PRD-0005，`config/bff.toml` / `BFF_*` env；見 ADR-023）

| 參數 | env var | 預設 | 單位 | 狀態 | 備註 |
|------|---------|------|------|------|------|
| device-service URL | `BFF_DEVICE_SERVICE_URL` | http://device-service:8002 | — | ✅ | 上游 REST |
| PostgREST URL | `BFF_POSTGREST_URL` | http://query:3000 | — | ✅ | 量測讀取上游（web_anon view）|
| upstream timeout | `BFF_UPSTREAM_TIMEOUT_S` | 10.0 | s | ✅ | |
| session 絕對壽命 | `BFF_SESSION_MAX_LIFETIME_S` | 28800 | s | ✅ | 8h 硬上限 |
| session 閒置逾時 | `BFF_SESSION_IDLE_TIMEOUT_S` | 1800 | s | ✅ | 30min |
| session 清掃間隔 | `BFF_SESSION_SWEEP_INTERVAL_S` | 300 | s | ✅ | in-memory store 背景清掃過期 session（ADR-023 P1 store；code-review MED）|
| 量測預設 / 上限 limit | `BFF_MEASUREMENTS_DEFAULT_LIMIT` / `BFF_MEASUREMENTS_MAX_LIMIT` | 100 / 1000 | rows | ✅ | 收緊於 openapi 上限 |
| Origin allowlist | `BFF_PUBLIC_ORIGINS` | http://localhost:8003 | csv | ✅ | CSRF 來源白名單；**dev（compose）預設含 `http://localhost:5173`（前端 origin），否則 vite-proxied 的 login/POST 會被擋** |
| log level | `BFF_LOG_LEVEL` | INFO | — | ✅ | |
| 認證模式 | `BFF_AUTH_MODE` | local | — | ✅ | local=argon2id 本地表（fallback）/ oidc=企業 IdP（Phase-1 stub→503）；ADR-024 |
| 帳號資料库 DSN | `BFF_AUTH_DB_DSN` | 空（local 啟動失敗） | — | ✅ | secret，專用 reader；ADR-035；使用者資料不在 env |
| OIDC issuer | `BFF_OIDC_ISSUER` | "" | — | ✅ | auth_mode=oidc 必填；discovery 來源；ADR-024 |
| OIDC client id | `BFF_OIDC_CLIENT_ID` | "" | — | ✅ | 必填(oidc) |
| OIDC client secret | `BFF_OIDC_CLIENT_SECRET` | "" | — | ✅ | **secret，.env only** |
| OIDC redirect URI | `BFF_OIDC_REDIRECT_URI` | "" | — | ✅ | 必填(oidc)；→ `/api/auth/oidc/callback` |
| OIDC scopes | `BFF_OIDC_SCOPES` | openid profile email | — | ✅ | 須含 openid |
| OIDC role claim | `BFF_OIDC_ROLE_CLAIM` | groups | — | ✅ | id-token 角色/群組 claim |
| OIDC role map | `BFF_OIDC_ROLE_MAP` | "" | — | ✅ | csv `claimval:role`；必填(oidc)；unmapped→拒（無預設權限）|
| OIDC state TTL | `BFF_OIDC_STATE_TTL_S` | 300 | s | ✅ | redirect round-trip 時限 |
| OIDC post-login redirect | `BFF_OIDC_POST_LOGIN_REDIRECT` | / | — | ✅ | 登入後導回 SPA 路徑 |
| OPS / INGEST channel key、account DB DSN | `BFF_OPS_API_KEY` / `BFF_INGEST_API_KEY` / `BFF_AUTH_DB_DSN` | "" | — | ✅ | **secret，.env only**；AI key 不進 BFF |
| cookie 屬性（HttpOnly/Secure/SameSite=Strict）| — | — | — | 🔒 | §9.2；放寬走 ADR-023 |
| role→至多一 key 通道、AI 通道禁入 BFF | — | — | — | 🔒 | §9.1；放寬走 ADR-023 |
### 本機歷史監控（PRD-0018）
- API 安全上限：7 天、points 60–1200（預設600）、records 1–1000（預設100）、offset 0–1000000；BFF history.py / migration 017 共同鎖定。
- 預覽：30s 自動刷新預設，可選5s或暫停；自訂區間及翻頁自動暫停；顯示原始頁100列；時間粒度 ceil(span/points) 秒。

### Telegram 示範通知（PRD-0019 / ADR-028）
| 參數 | env | 預設 / 限制 | 儲存 |
|---|---|---|---|
| Bot Token | BFF_TELEGRAM_BOT_TOKEN | 空則不可發送 | SecretStr；Compose 由既有 TELEGRAM_BOT_TOKEN 注入；env only |
| 固定收件者 | BFF_TELEGRAM_CHAT_ID | 空則不可發送 | Compose 由既有 TELEGRAM_CHAT_ID 注入；env only |
| 全域冷卻 | BFF_DEMO_ALARM_COOLDOWN_S | 30 秒；5–3600 | services/bff/config/bff.toml [demo_alarm] |
| Telegram 呼叫上限 | BFF_TELEGRAM_TIMEOUT_S | 8 秒；1–10 | 同上 |
| 去重 TTL / cache / 最近成功紀錄 | 不提供 env | 600 秒 / 64 筆 / 10 筆 | ADR-028 鎖定；記憶體單程序 |

### 展位 QR 綁定訪客（PRD-0024 / ADR-036）
| 參數 | env | 預設 / 限制 | 儲存 / 備註 |
|---|---|---|---|
| 功能開關 | BFF_DEMO_BIND_ENABLED | code false；bff.toml true | `services/bff/config/bff.toml` [demo_binding]；false + 重啟 = PRD-0019 行為 |
| 狀態檔 | BFF_DEMO_BIND_DB | /data/demo-alarm/state.sqlite3 | volume `demo_alarm_state`；單程序鎖 |
| 綁定有效期 | BFF_DEMO_BIND_TTL_S | 600 秒；60–3600 | 自綁定起算；Bot 確認文字的分鐘數跟隨此值 |
| start code 輪替 | BFF_DEMO_BIND_CODE_ROTATE_S | 60 秒；15–600 | 耦合：必須 ≤ code 有效期（啟動時驗證） |
| start code 有效期 | BFF_DEMO_BIND_CODE_TTL_S | 300 秒；15–900 | 拍照 QR 可用的最長時間 |
| long-poll 等待 | BFF_TELEGRAM_POLL_TIMEOUT_S | 25 秒；1–50 | HTTP 逾時 = 此值 + 10 |
| 訊息時效 / 每使用者頻率 / 全域回覆 / batch | 不提供 env | 120 秒 / 3 秒 1 指令 / 20 則每分 / 100 | **spec-locked**（PRD-0024 §5）；放寬須走 ADR |
| 錯誤退避 / 409 重試 / webhook 重查 / 空批次間隔 | 不提供 env | 1→60 秒 / 30 秒 / 300 秒 / 1 秒 | **spec-locked**（ADR-036） |

## Delta edge（PRD-0020）
|參數|預設|範圍／限制|位置|
|---|---|---|---|
|poll_interval|10s|整數1..3600|services/delta/config/*.json|
|queue_limit|10000|1..1000000筆；滿時拒新|同上|
|batch_size|100|1..100|同上|
|modbus.timeout|3s|1..30|同上|
|modbus.address_base|1|0或1|同上|
|modbus.unit_id|1|1..247，禁止broadcast0|同上|
|modbus.baudrate|19200|9600/19200/38400；8N1|同上|
|modbus.read_temperature|field false|機型確認後選用|同上|
|mode|必填|demo或field；field強制TLS+身份驗證|同上|
|MQTT ACK wait|5s|程式上限；逾時保留待ACK MID|delta_device/publisher.py|
|outbox payload/snapshot|1KB/16KB|硬上限|delta_device/delivery.py|

## PRD-0022 Simulator control
| Tunable | Default | Bounds / source |
|---|---|---|
| BFF_SIM_CONTROL_ENABLED | false | boolean; Compose env |
| BFF_SIM_CONTROL_TOKEN | empty | env only, >=32 chars when enabled; Compose maps SIM_CONTROL_TOKEN |
| BFF_SIM_CONTROL_DB | /data/sim-control/audit.sqlite3 | dedicated persistent volume; single process |
| BFF_SIM_CONTROL_MAX_COMMANDS | 100000 | 1–1000000; full => reject new commands, preserve UUID |
| HTTP hop | 3s total | code safety bound, GET and POST each bounded |
| agent receipt capacity | 4096 | fixed per instance; full rejects new commands |
各sim設定範圍與sensor發布preset詳 operations/simulator-control.md；不等於Pi採樣策略。

| 管理 DB DSN | BFF_AUTH_ADMIN_DSN | 空（CLI 拒絕） | — | ✅ | secret，只注入 account-admin；主機管理權限 |

## Windows無Pi驗證工具（2026-11-12，僅台架）

對應PRD-0020 §13、ADR-031；不改production設定或API。來源：services/delta/tools/bench_run.py、bench_frames.py、bench_network.py。結果以[逐關紀錄](../../output/delta-no-pi-validation-20261112/README.md)為準，工具存在不代表各關已通過。

| 入口 | 參數／預設 | 限制及耦合 |
|---|---|---|
| bench_run | count必填；interval必填1/5/10/15/30秒；scenario=day | 正整數槽數，總窗≤24h；新目錄、自有SQLite；僅delta-rtu-sim-001、loopback MQTT及RTU |
| bench_run | sim-port=COM3；主站取config(COM4)；outage可重複offset:duration | 埠不可相同，故障窗口不可重疊且須保留重啟後採樣槽 |
| bench_run固定驗收值 | sender settle=5秒；從站恢復≤15秒；ledger queue=10000events | settle不增加採樣分母，超界／帳本寫失敗不能PASS |
| bench_verify | wait-seconds=30秒；固定loopback4178 API | 完整已結束run窗口；DB/API逐筆原時戳與四欄位，還需run summary通過 |
| bench_frames | count=20（1..100）；timeout=3秒（0.5..5） | 固定已確認COM3/COM4；晚回覆依第二請求同步，不把serial timeout當整輪deadline |
| bench_network固定驗收值 | 5秒80槽，第9秒斷300秒，恢復後≤120秒DB/API核對 | private loopback gate到1883；60離線槽、單一Publisher自動重連；不停止共享broker |
| bench_usb | target必填COM3/COM4；5秒60槽；枚舉wait=0.5秒 | 使用者約30秒拔插（驗收觀察28..60秒）；恢復上界以最後absent探測開始時間計算，非固定0.5秒誤差；需原序號與原COM。 |

## RTU simulator串口恢復（ADR-040／FR-2008）

| 參數／env | 預設 | 範圍／單位 | 所屬模組／性質 |
|---|---|---|---|
| DELTA_SIM_RTU_HEALTH_SECONDS | 0.5 | 有限數0.01..60秒 | config.simulator_recovery_settings；operational，監看listener／poll task，不因總線無量測而重開 |
| DELTA_SIM_RTU_RECONNECT_SECONDS | 2 | 有限數0.01..60秒 | 同上；operational，成功啟動後故障重開等待；首次開啟失敗仍立即退出 |

## RTU不確定交易（ADR-041／FR-2003）

| 參數 | 預設 | 範圍 | 用途與核定 |
|---|---|---|---|
| modbus.response_lifetime_seconds | null／省略 | 有限數0.01..120秒，拒絕bool | 舊請求最後一byte可能抵達主站的核定上界，含設備／USB／驅動；不是timeout。field RTU必填；demo未知時，遇錯鎖定且不自動恢復 |
| modbus.response_lifetime_source | null／省略 | 配置上界時必填非空字串，最多256字 | 受信operator提供的機型／韌體／介面核定依據；欄位不驗證來源真實性。台架1秒只屬受控fixture，不可帶到Delta真機 |

field-rtu.example.json刻意保留null，未核定前拒絕啟動；不得為了通過validate填入猜測值。故障從失敗時刻等待完整上界，field也有啟動等待；TCP不可配置非null上界。

只影響RTU模擬器，env改值重啟生效；不改TCP simulator或採集器timeout，不改CRC／站號／長度校驗。現場恢復延遲還包含USB枚舉及查詢排程，不能以此兩設定相加宣稱15秒達標。

## v2公平傳送與私有restore測試限制（2026-11-13，ADR-048）

[ADR-048](../adr/ADR-048-v2-live-backlog-fairness.md)登錄sender最新／最舊成功1:1為本階段spec-locked固定規則，初始latest、只有authenticated committed且本地resolved成功才換；沒有新增JSON/env可調key。原單筆／inflight1、成功間隔≥.5秒與edge1秒loop不變，資料率仍需實測；輪次記憶體不跨程序持久。

僅私有verify_private工具的backup binary cap16MiB、request1024B／proof64KiB／JUnit8MiB均為防護上限，非正式DB備份容量配額；超限中止測試，不放寬production隊列／wire限制。Owner EMS；[證據](../../output/no-pi-restore-load-20261113/README.md)，不新增全域service參數或依賴。

| receiver.ack_durability | receiver JSON | field=sync_wal; demo=local | enum | edge-receiver | ADR-049／FR-2106 | field強制sync_wal spec-locked，demo僅隔離驗證 |
| receiver.wal_standby_name | receiver JSON | ems_archive | named peer | edge-receiver | ADR-049／FR-2106 | 1個[a-z][a-z0-9_]{0,62}；須與FIRST 1完全匹配；不得ANY替代 |
| WAL CLI / slot | systemd / pg_service.conf | --synchronous; ems_archive_slot; interval=1s | flags/s | 維運pg_receivewal | ADR-049 | synchronous spec-locked，slot/peer/cluster需一致；正式獨立儲存＋首份basebackup準入 |

### 2026-11-13 DB TLS／備份預檢

| 參數 | 預設／邊界 | 來源／耦合 |
|---|---|---|
| db_tls.ca_file/cert_file/key_file | field必填，非空檔案路徑；無不驗證選項 | receiver.example.json／database_tls.py；受管CA、hostname與專用登入角色CN對應 |
| WAL peer role | 固定ems_wal_archive，不是runtime可調降級 | migration021／受管LOGIN與client cert，peer名仍受wal_standby_name約束 |
| --expected-system-id | 還原必填外置可信正uint64十進位字串 | backup_preflight；不可取同一bundle自稱值 |
| --max-archive-bytes | 8589934592，正整數；檔案及展開累計上限 | backup_preflight CLI --check-archive；標準未壓縮tar，需與核定備份大小相符 |
| --max-archive-members | 100000，正整數 | backup_preflight CLI；超限拒，不部分放行 |
| QA WAL tmpfs | 固定128MiB，僅隔離測試安全上限 | private_wal_security；不得用於推算正式持久容量 |

### 2026-11-13 還原分支參數

| 參數 | 預設／邊界 | 權威與耦合 |
|---|---|---|
| --expected-timeline | directory預檢必填，正uint32標準十進位字串；拒latest/current/前導0 | backup_preflight.recovery_settings；維運外置核定，與target-name共同固定來源分支 |
| --target-name | directory預檢必填，1–63安全ASCII字元，首字母數字/底線，其餘字母數字/底線/點/減號 | recovery_settings；實際PG recovery須到此named target，輸出需維運套用 |
| QA central quota | 固定16MiB tmpfs，僅自有receipt tablespace | private_critical，非正式容量設定；測後移回pg_default/drop測試tablespace |
| QA pickup gap | 固定3段＋checkpoint | 僅驗base→接手保護空窗，不能視為正式容量／失效域SLA |
