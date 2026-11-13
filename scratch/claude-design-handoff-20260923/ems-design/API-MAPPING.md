# EMS 前端七畫面 × 後端 API 資料綁定對照表（API-MAPPING）

> 版本 v1.0（2026-09-23）。讀者：設計代理（欄位、列舉、單位、時間格式對齊）與後端團隊（缺口與建議介面）。
> 本文件只讀取、不修改 repo；凡非現存的端點或欄位一律標 **proposed**，待後端團隊決策。

## 文件說明

### 來源與引用格式

| 簡稱 | 路徑 |
|---|---|
| repo 根目錄 | `\\wsl.localhost\Ubuntu\home\dalelin\synaiq\EMS\`（下文路徑皆相對於此） |
| ARCH | `doc/architecture/ems-edge-cloud-platform-architecture.md`（狀態 Working Draft，ARCH:5） |
| BESS | `doc/architecture/bess-operating-mode-state-machine.md`（狀態 Draft，BESS:4） |
| PRD5 | `doc/prd/PRD-0005-ems-frontend.md`（Approved，PRD5:5） |
| PRD6 | `doc/prd/PRD-0006-Generic-Measurement-Pipeline-Dynamic-Visualization.md`（Draft v3） |
| W3 | `doc/prd/PRD-0005-wave3-implementation-plan.md` |
| ADR-0xx | `doc/adr/ADR-0xx-*.md` |
| PLAN | 設計端 `scratchpad\ems-design\PLAN.md` §C（PLAN:51-131，逐畫面元件清單，本文件的元件來源） |
| DOMAIN | 設計端 `scratchpad\ems-domain.md` |

引用一律為 `檔案:行號`。E-xx = 已實作端點（Part 1.1）、U-xx = 已存在但瀏覽器不可用的上游端點（Part 1.4）、PL-xx = 規劃中端點（Part 1.5）、G-xx／F-xx = 缺口建議（Part 3）。

### 狀態判定規則

| 狀態 | 定義 |
|---|---|
| **已實作** | 瀏覽器今天即可經 BFF（同源 `/api`；PRD5:269-273 規定 BFF 為唯一瀏覽器通道）以「單次呼叫既有端點」取得；允許對單次回應做簡單運算（平均、加總、計數、比例、時間差）。 |
| **規劃中** | 尚未實作，但 ARCH §10.1、PRD 或 ADR 已明列能提供該資料的端點路徑（附行號）。ARCH 只列路徑、未定回應 schema，建議欄位見 Part 3.4 並逐一標 proposed。 |
| **缺口** | 既無實作、也無明列端點。建議介面見 Part 3.3（proposed）。若上游已有資料但未經 BFF 暴露，仍判缺口並於備註說明。 |

- **計數單位**：一列 = 一個畫面元件中「狀態一致」的一組資料綁定；同一元件內欄位狀態不同時拆列。純靜態文案（不需 API）不列入計數，另於各表下方註明。
- **跨呼叫推導不算已實作**：需多次呼叫、跨頁彙總或含業務規則（需量、電費、可用率）者，不判已實作。

---

## 0. 結論與覆蓋率

| 畫面 | 列數 | 已實作 | 規劃中 | 缺口 |
|---|---:|---:|---:|---:|
| 能源總覽 Main | 15 | 1 | 12 | 2 |
| 即時監控 Monitor | 18 | 7 | 10 | 1 |
| 需量管理 Demand | 9 | 1 | 3 | 5 |
| 儲能管理 Storage | 19 | 0 | 14 | 5 |
| 警報中心 Alarms | 9 | 0 | 7 | 2 |
| 設備分析 Devices | 13 | 11 | 0 | 2 |
| 報表中心 Reports | 10 | 0 | 3 | 7 |
| **七畫面合計** | **93** | **20（21.5 %）** | **49（52.7 %）** | **24（25.8 %）** |
| 共用框架（另計） | 5 | 3 | 2 | 0 |

判讀：
1. 已實作的 20 列中有 11 列在「設備分析」；其餘畫面合計 9／80 列（11 %）。已實作的資料路由全部限 OPS 角色（Part 1.2）；以唯讀角色（管理層／客戶）登入時，七畫面經非 deprecated 路由可取得的列數為 0。
2. 今日唯一的量測資料源是模擬電表 `sim-001`（1 秒取樣）與 KC 工廠模擬器；無 PV、BMS、PCS、負載電表資料（ARCH:50）。
3. 三大缺口：
   - **時序彙總與場域摘要**：唯一的量測 API（E-18）每次最多 1000 筆原始資料（1 秒取樣約 16.7 分鐘），沒有 `until`、沒有彙總粒度；24 小時／15 分鐘趨勢、需量長條與歷史曲線都做不出來。PV／儲能／負載的即時值只在 ARCH 規劃（PL-12、PL-15），尚無資料源。
   - **警報中心**：現行 10 條 Grafana 告警規則只存在於 Grafana，未經 BFF 暴露、告警標籤不含 device_id、無 ACK／擱置；警報生命週期 API 僅在 ARCH 規劃（ARCH:560-562），Runbook 與通知升級連規劃都沒有。
   - **需量、電價、電費與報表**：repo 內沒有契約容量、時間電價時段、費率表、15 分鐘需量彙總或報表產生功能；本文件提出 11 組 proposed 端點（13 條路由）補齊，其中需量摘要、時間電價、匯出、BESS 設定屬首發。

---

## Part 1 API 清單

### 1.1 瀏覽器可呼叫端點（BFF 同源 `/api`，已實作）

路徑前綴 `services/bff/bff/` 以「…/」簡寫。

| ID | 方法 | 路徑 | 角色／認證 | 參數／Body | 回應（schema 見 1.3） | 分頁／包裝 | 出處 |
|---|---|---|---|---|---|---|---|
| E-01 | GET | `/healthz` | 無 | — | `{"status":"ok"}` | 單一物件 | …/routes/health.py:9-11 |
| E-02 | POST | `/api/auth/login` | 不需 session；須帶允許的 Origin | JSON `username`（string 1–64）、`password`（string 1–256） | 200 `{username: string, role: "ops"／"ingest"／"readonly", expires_in: int（秒，=28800）}`＋`Set-Cookie: ems_bff_session`；401 `invalid credentials`；503（OIDC 模式） | 單一物件 | …/routes/auth.py:21-23, 30-54；…/config.py:108-110 |
| E-03 | POST | `/api/auth/logout` | 任一角色 session；Origin | — | 204，清除 cookie | — | …/routes/auth.py:57-62 |
| E-04 | GET | `/api/auth/session` | 任一角色 session | — | `{username, role}`；401（無或過期 session） | 單一物件 | …/routes/auth.py:65-67 |
| E-05 | POST | `/api/auth/role` | 任一角色 session；Origin | JSON `role` | `{session_terminated: bool, role}`；角色一變更即終止 session | 單一物件 | …/routes/auth.py:70-83 |
| E-06 | GET | `/api/auth/oidc/login` | 無（僅 OIDC 模式） | — | 302 至 IdP；503（非 OIDC 模式） | — | …/routes/oidc.py:49-63 |
| E-07 | GET | `/api/auth/oidc/callback` | 無（`state` 作 CSRF 防護） | `code`（≤2048）、`state`（≤512） | 302 至 `/`＋session cookie；401／502 | — | …/routes/oidc.py:66-102 |
| E-10 | GET | `/api/devices` | OPS | `status`、`type`（皆須符 `^[a-zA-Z0-9_-]{1,64}$`）；`stale`（`true`／`false`）；`limit` 1–500；`offset` 0–1,000,000；`sort` ∈ device_id、device_type、status、ai_confidence、created_at、updated_at、last_seen_at（預設 device_id）；`order` asc／desc（預設 asc）；未知或重複參數 → 422 | `DeviceOut[]` | 裸陣列；limit／offset；無 total；不帶 limit 回全部（api/openapi.yml:582）；排序 NULLS LAST、次序鍵 device_id | …/routes/devices.py:36-64, 88-101；services/device-service/device_service/repositories/device_repo.py:44-66 |
| E-11 | GET | `/api/devices/{device_id}` | OPS | path 須符 `^[a-zA-Z0-9_-]{1,64}$` | `DeviceOut`；404 | 單一物件 | …/routes/devices.py:34, 104-117 |
| E-12 | GET | `/api/devices/{device_id}/signals` | OPS | — | `SignalOut[]`（僅 status=active，依 signal_name 排序） | 裸陣列 | …/routes/devices.py:120-133；services/device-service/device_service/repositories/signal_repo.py:9-11 |
| E-13 | GET | `/api/devices/{device_id}/human-review` | OPS | — | `DigestOut`；404（裝置不存在或尚無 digest） | 單一物件 | …/routes/devices.py:136-149；services/device-service/device_service/routes/devices.py:146-158 |
| E-14 | POST | `/api/devices/{device_id}/confirm` | OPS；Origin | 無 body | `DeviceOut`（status→confirmed、classified_by→human）；409（非 candidate） | 單一物件 | …/routes/devices.py:152-165；device-service routes/devices.py:197-209 |
| E-15 | POST | `/api/devices/{device_id}/override` | OPS；Origin | JSON `device_type`（必填）、`signals[]`（SignalCreate） | `DeviceOut`（status→confirmed、classified_by→manual_override；寫稽核 `freeze_override`） | 單一物件 | …/routes/devices.py:168-185；device-service routes/devices.py:212-236 |
| E-16 | POST | `/api/devices/{device_id}/reject` | OPS；Origin | 無 body | `DeviceOut`（status→retired；寫稽核 `freeze_override`） | 單一物件 | …/routes/devices.py:188-201；device-service routes/devices.py:239-256 |
| E-17 | POST | `/api/devices/{device_id}/corrections` | OPS；Origin | JSON `CorrectionCreate`（上游路徑為 `/ai-feedback`） | 201 `CorrectionOut`；400 `{detail:{reason,message}}`；404；409；429（每 key 30 次／小時、每裝置 10 次／小時）；503 | 單一物件 | …/routes/devices.py:204-222；api/openapi.yml:654-674 |
| E-18 | GET | `/api/devices/{device_id}/measurements` | OPS（INGEST、READONLY 回 403，ADR-025:34） | `since`（ISO 8601，含，轉為 `time=gte.`）；`limit` 1–1000（預設 100）；`order` asc／desc（預設 desc）；其他參數 → 422 | 電力裝置 `Measurement[]`；工廠裝置 `FactoryMeasurement[]`（依 `gateway_id` 判定）；404（無量測域） | 裸陣列；無 offset、cursor、until、彙總 | …/routes/device_measurements.py:34-98；…/domain.py:15-19；…/config.py:121-122 |
| E-19 | GET | `/api/measurements/{domain}`（**deprecated／internal，不得擴充**） | OPS、INGEST、READONLY | `domain` ∈ electricity、factory；`device_id`、`time`、`limit`、`offset`、`order`（PostgREST 運算子字串，值須符 `^[A-Za-z0-9_.:,+-]{1,128}$`）；預設 limit 100、上限 1000 | 同 PostgREST（U-10／U-11） | 裸陣列；limit／offset | …/routes/measurements.py:3-9, 31-80 |

### 1.2 現行共通約定

**角色矩陣**（…/roles.py:15-18, 26-36；…/security.py:53-62）

| 端點群 | OPS | INGEST | READONLY |
|---|---|---|---|
| E-02 至 E-07（登入、session） | 可 | 可 | 可 |
| E-10 至 E-17（設備） | 可 | 403 | 403 |
| E-18（量測 facade） | 可 | 403 | 403 |
| E-19（legacy 量測，deprecated） | 可 | 可 | 可 |

- **Session**：cookie `ems_bff_session`，HttpOnly、Secure、SameSite=Strict（…/security.py:18-29）；絕對上限 8 小時（28800 秒）、閒置 30 分鐘（1800 秒）（…/config.py:110-111）。每次請求都會重置閒置計時（…/sessions.py:111-126），輪詢可維持 session，但 8 小時上限不變；UI 必須處理 401 並轉登入（frontend/src/api/liveFetcher.ts:75-86）。
- **CSRF**：`/api` 下 POST、PUT、PATCH、DELETE 須帶允許清單內的 Origin，否則 403 `origin check failed`（…/security.py:65-86）；預設清單 `http://localhost:8003`（…/config.py:118）。
- **回應包裝**：上游 body 原樣透傳，無 envelope（…/upstream.py:53-58）；清單為裸陣列，無 total（PRD5:228, 240-244）。
- **錯誤格式**：FastAPI `{"detail": "<字串>"}`；查詢參數型別錯誤時 `detail` 為陣列；設備修正內容違規 400 為 `{"detail":{"reason","message"}}`（device-service routes/devices.py:47-48）。上游 400／404／409／422／429 透傳（…/upstream.py:21）；上游 401／403／5xx／網路失敗一律 502（…/upstream.py:40-51）；通道 key 未設定 503 `channel key not configured`（…/routes/devices.py:67-71）。
- **快取**：所有 `/api` 回應皆帶 `Cache-Control: no-store`（…/security.py:95-101），每次輪詢都會打到上游；E-18 每次呼叫 BFF 會再打兩個上游（device-service 取 gateway、PostgREST 取資料；ADR-025:46）。
- **時間**：DB 為 `TIMESTAMPTZ`；openapi 標示量測時間為 UTC（api/openapi.yml:995, 1031）；registry 時間欄為 ISO 8601 date-time（api/openapi.yml:802-805）。
- **契約文件**：BFF 關閉自身 OpenAPI（…/main.py:85-87）；`api/openapi.yml`（v1.3.0）只描述 device-service、PostgREST、Grafana、模擬器，**不含任何 BFF 路由**。

### 1.3 現行回應 schema（設計須逐字採用的欄位名）

**DeviceOut**（services/device-service/device_service/models.py:31-45；api/openapi.yml:788-805）

| 欄位 | 型別 | 值域／單位 | 出處 |
|---|---|---|---|
| `device_id` | string | `^[a-zA-Z0-9_-]{1,64}$` | models.py:32；…/routes/devices.py:34 |
| `device_type` | string 或 null | DB 自由文字；AI 閉集見 4.1 | infra/timescaledb/migrations/003_create_devices.sql:8；device-service llm/prompt.py:9 |
| `status` | string | `candidate`、`confirmed`、`active`、`maintenance`、`retired` | 003_create_devices.sql:26-27 |
| `protocol`、`vendor`、`model`、`location` | string 或 null | 自由文字；protocol 現值 `modbus_tcp`、`mqtt_json` | 003:10-13；008_backfill_existing_devices.sql:11-13 |
| `gateway_id` | string 或 null | 已知值 `ems-gateway`、`kc-gateway`、`kc-ingest` | 003:14；…/domain.py:15-19 |
| `classified_by` | string 或 null | `ai`、`human`、`manual_override`、`migration_backfill` | 003:28-29 |
| `ai_confidence` | number 或 null | 0–1（NUMERIC(3,2)）；未分類為 null | 003:16, 30-31 |
| `created_at`、`updated_at`、`last_seen_at`、`confirmed_at` | ISO 8601 或 null | `last_seen_at` 於 device-service 收到該裝置 MQTT 訊息時更新 | models.py:42-45；device-service discovery.py:116, 123；device_repo.py:143-147 |
| （不回傳） | — | DB 另有 `activated_at`、`stale_marked_at`、`metadata`、`ai_provider`、`last_error`，刻意不暴露 | device_repo.py:9-10；PRD5:49 |

**SignalOut**（models.py:56-63；api/openapi.yml:815-825）：`id` int；`device_id`；`signal_name`（`^[a-zA-Z0-9_-]{1,64}$`）；`unit` string 或 null（現值 `V`、`A`、`kW`、`kWh`、`degC`、`%RH`、`RPM`、`kPa`、`boolean`，008:21-34）；`datatype`（`float`、`int`、`bool`、`enum`，004_create_device_signals.sql:21）；`direction`（`read`、`write`、`read_write`，004:22）；`status`（`active`、`retired`，004:20）。`source_ref`（位址）刻意不回傳（009_create_api_views.sql:27；models.py:56-63）。

**Measurement**（電力；infra/timescaledb/init.sql:9-16；api/openapi.yml:986-1020）

| 欄位 | 型別 | 單位 | 備註 |
|---|---|---|---|
| `time` | ISO 8601 date-time | UTC | 取樣 1 秒（services/gateway/telegraf.conf:6） |
| `device_id` | string | — | 今日僅 `sim-001` |
| `voltage` | number 或 null | V | 三相線電壓（模擬器 380 V 級，api/openapi.yml:97-99） |
| `current` | number 或 null | A | — |
| `power_kw` | number 或 null | kW | 有效功率；正負號語意未定義（模擬器只產生正值） |
| `energy_kwh` | number 或 null | kWh | 累計計數器 |

**FactoryMeasurement**（infra/timescaledb/migrations/001_add_factory.sql:13-23；api/openapi.yml:1022-1071）：`time`（UTC）、`device_id`、`device_type`（`plc`、`sensor`；此為量測表欄位，與 registry 的 device_type 不同）、`temperature`（°C；signal unit 字串 `degC`）、`humidity`（%RH）、`motor_speed`（RPM）、`pump_on`（bool）、`valve_open`（bool）、`pressure`（kPa）。

**DigestOut**（models.py:71-80；api/openapi.yml:891-902）：`device_id`、`digest`（object）、`summary_source`（`llm`、`system_fallback`；005_create_device_review_digests.sql:14）、`generated_at`、`provider`、`model`、`prompt_version`。`digest` 實際鍵（services/device-service/device_service/digest.py:39-56, 69-86）：`schema_version`（"1.0"）、`device_id`、`first_seen_at`、`generated_at`、`summary_source`、`ai_provider`、`ai_model`、`prompt_version`、`ai_confidence`（0–1）、`suggested_device_type`、`suggested_signals[]`（`signal_name`、`unit`、`datatype`、`direction`）、`summary_zh`、`sample_digest`（`topic`、`field_value_examples`、`sample_count`）、`why_low_confidence`。一律以純文字渲染（PRD5 §9.5；frontend/src/components/ems/ReviewDigestPanel.tsx:1-6）。

**CorrectionCreate／CorrectionOut**（models.py:83-114；api/openapi.yml:836-890）：`verdict` ∈ `wrong_classification`、`wrong_signals`、`wrong_unit`、`missed_signal`、`good_with_note`（007_create_device_corrections.sql:23-24）；`human_explanation` 30–500 字（007:25-26）；`corrected_device_type`、`corrected_signals`、`rerun_classification`、`demote_to_candidate`。

**OverrideRequest**（models.py:66-68）：`device_type`（必填）、`signals[]`（SignalCreate：`signal_name`、`unit`、`datatype`、`direction`、`source_ref`）。

### 1.4 已存在但瀏覽器不可直接使用的上游端點

PRD5:269-273 規定瀏覽器只能經 BFF；下列端點若未經 BFF 暴露，對產品前端等同不存在。

| ID | 服務 | 方法與路徑 | 認證 | 經 BFF | 回應重點 | 出處 |
|---|---|---|---|---|---|---|
| U-01 | device-service :8002 | `POST /devices` | X-API-Key（OPS） | 否（ADR-026 規劃 PL-01，未實作） | `DeviceOut` 201 | api/openapi.yml:560-572 |
| U-02 | 同上 | `PATCH /devices/{id}` | OPS | 否（PL-02） | `DeviceOut`；凍結紀錄 409 | api/openapi.yml:599-610 |
| U-03 | 同上 | `DELETE /devices/{id}` | OPS | 否（刻意不暴露，ADR-026:41） | 204（soft-retire、不寫稽核） | api/openapi.yml:611-619 |
| U-04 | 同上 | `GET /devices/{id}/corrections?active_only=` | OPS | 否 | `CorrectionOut[]` | api/openapi.yml:675-686 |
| U-05 | 同上 | `POST /devices/{id}/corrections/{correction_id}/deactivate` | OPS | 否 | `CorrectionOut` | api/openapi.yml:687-703 |
| U-06 | 同上 | `POST /devices/{id}/signals` | OPS | 否 | `SignalOut` 201 | api/openapi.yml:723-734 |
| U-07 | 同上 | `DELETE /devices/{id}/signals/{signal_name}` | OPS | 否 | 204 | api/openapi.yml:735-747 |
| U-08 | 同上 | `GET /healthz` | 無 | 否 | `{status: "ok"／"degraded", pools}` | api/openapi.yml:551-558, 903-912 |
| U-10 | PostgREST :3001 | `GET /electricity_measurements` | 無（web_anon） | 僅作為 E-18／E-19 的內部上游 | `Measurement[]`；參數 select、device_id、time、power_kw、voltage、current、order（預設 time.desc）、limit 1–10000（預設 100）、offset | api/openapi.yml:210-307 |
| U-11 | 同上 | `GET /factory_measurements` | 無 | 同上 | `FactoryMeasurement[]`；參數 select、device_id、device_type、time、order、limit 1–10000 | api/openapi.yml:310-385 |
| U-12 | 同上 | `GET /devices`（view `api.devices`） | 無 | 否；**openapi 未記載** | 僅 confirmed／active 裝置、白名單欄位 | infra/timescaledb/migrations/009_create_api_views.sql:8-25 |
| U-13 | 同上 | `GET /device_signals`（view `api.device_signals`） | 無 | 否；**openapi 未記載** | 僅 active 訊號，不含 source_ref | 009_create_api_views.sql:28-43 |
| U-20 | Grafana :3000 | `GET /api/alertmanager/grafana/api/v2/alerts` | basicAuth（admin） | 否 | `labels.alertname`、`labels.severity`、`annotations.summary`、`annotations.description`、`startsAt`、`status.state`（`active`、`suppressed`） | api/openapi.yml:462-481, 1106-1139 |
| U-21 | 同上 | `GET /api/prometheus/grafana/api/v1/rules` | basicAuth | 否 | 規則狀態 `inactive`、`pending`、`firing` | api/openapi.yml:443-460, 1073-1104 |
| U-22 | 同上 | `GET /api/datasources/uid/{uid}/health` | basicAuth | 否 | `status`（`OK`、`ERROR`）、`message` | api/openapi.yml:483-508 |
| U-23 | 同上 | `POST /api/admin/provisioning/{alerting,dashboards,datasources}/reload`、`POST …/receivers/test` | basicAuth | 否 | 維運用 | api/openapi.yml:390-441, 510-542 |
| U-30 | 模擬器 :8001 | `GET /health`、`GET /config`、`POST /config`、`POST /inject-fault?mode=` | 無 | 否 | `/config` 含 `power_factor`（0–1）等模擬參數；`fault_mode` ∈ `none`、`zero`、`freeze` | api/openapi.yml:46-205, 925-977 |
| — | MCP :8766 | MCP Streamable-HTTP（非 REST） | AI key，僅 loopback | 否，前端禁止使用 | — | api/openapi.yml:14-15；PRD5:41 |

### 1.5 規劃中端點（未實作）

分期欄依 ARCH §9.1（ARCH:516-529）：MVP 視為「首發」，Pilot／Production 視為「後續」。ARCH §10.1 共通要求：OpenAPI 3.1、cursor 分頁、idempotency、ETag／expected version、error code、rate limit（ARCH:575）。

| ID | 方法與路徑 | 出處 | 資料欄位（出處已列者） | 分期 | 本設計使用 |
|---|---|---|---|---|---|
| PL-01 | BFF `POST /api/devices` | ADR-026:26-33（Accepted）；W3:56, 100-105；ARCH:58 | 同 DeviceCreate | FR-502 | 否 |
| PL-02 | BFF `PATCH /api/devices/{device_id}` | 同上 | 同 DeviceUpdate | FR-502 | 否 |
| PL-03 | `GET /devices` 回應標頭 `X-Total-Count`（條件式） | PRD5:243 | 總筆數 | 視 UX 需要 | 可用於設備 KPI |
| PL-04 | PostgREST `GET /signal_measurements`（內網；P1 不授權 web_anon） | PRD6:97, 230, 294 | 窄表 time、device_id、signal_name、value_* | PRD6 P1 | 間接（仍須經 BFF） |
| PL-05 | BFF 橋接 Grafana 告警狀態（AlarmStrip；無路徑） | PRD5:203 | — | PRD5 元件清單 | 警報過渡方案 |
| PL-06 | 即時推播 SSE／WebSocket（P2 先輪詢） | PRD5:396；ARCH:536 | — | 後續 | 所有即時元件 |
| PL-10 | `GET /api/v1/organizations` | ARCH:553 | id、name、policy（ARCH:600） | — | 否 |
| PL-11 | `GET /api/v1/sites` | ARCH:554 | id、organization、timezone、grid_contract（ARCH:601） | 首發（ARCH:518-519） | 是 |
| PL-12 | `GET /api/v1/sites/{site_id}/summary` | ARCH:555 | 未定義 | 首發（ARCH:519, 521） | 是 |
| PL-13 | `GET /api/v1/sites/{site_id}/assets` | ARCH:556 | id、site、parent、type、lifecycle（ARCH:602） | 首發（ARCH:520） | 是 |
| PL-14 | `GET /api/v1/assets/{asset_id}/signals` | ARCH:557 | profile、name、unit、type、access、range、poll（ARCH:606） | 首發（ARCH:526） | 可選 |
| PL-15 | `GET /api/v1/assets/{asset_id}/measurements?from=&to=&resolution=&cursor=` | ARCH:558 | time、site、device、signal、value、quality、sequence（ARCH:607）；彙總 1 分／15 分／1 小時（ARCH:459） | 首發（ARCH:522） | 是 |
| PL-16 | `GET /api/v1/sites/{site_id}/events` | ARCH:559 | id、site、device、type、severity、times、detail（ARCH:608） | — | 可選 |
| PL-17 | `GET /api/v1/sites/{site_id}/alarms` | ARCH:560 | rule、state、first、last、ack、clear（ARCH:609） | 首發（ARCH:523 active） | 是 |
| PL-18 | `POST /api/v1/alarms/{alarm_id}/ack` | ARCH:561 | — | 首發（ARCH:523） | 是 |
| PL-19 | `POST /api/v1/alarms/{alarm_id}/shelve` | ARCH:562 | 期限、理由、actor、audit（ARCH:473） | 後續（ARCH:523 將 suppress 列 Pilot） | 是 |
| PL-20 | `GET /api/v1/sites/{site_id}/commands` | ARCH:563 | id、site、target、type、requested、final、status、expiry、actor（ARCH:610）；attempts（ARCH:611） | 後續（ARCH:524） | 是 |
| PL-21 | `POST /api/v1/sites/{site_id}/commands` | ARCH:564 | 必填欄位 ARCH:491 | 後續 | 否 |
| PL-22 | `POST /api/v1/commands/{command_id}/approve` | ARCH:565 | — | 後續（dual approval，ARCH:524） | 否 |
| PL-23 | `GET /api/v1/sites/{site_id}/schedules` | ARCH:566 | site、version、window、strategy、status、approved_by（ARCH:612） | 首發（ARCH:525 display） | 是 |
| PL-24 | `POST /api/v1/sites/{site_id}/schedules` | ARCH:567 | — | 後續（ARCH:525） | 否 |
| PL-25 | `POST /api/v1/schedules/{schedule_id}/deploy` | ARCH:568 | — | 後續 | 否 |
| PL-26 | `GET /api/v1/device-profiles` | ARCH:569 | vendor、model、version、schema、hash、status（ARCH:604） | — | 否 |
| PL-27 | `POST /api/v1/sites/{site_id}/config-deployments` | ARCH:570 | hash、targets、ring、status、rollback（ARCH:613） | 後續（ARCH:528） | 否 |
| PL-28 | `GET /api/v1/sites/{site_id}/audit-events` | ARCH:571；PRD5:353（AC-6） | actor、action、resource、outcome、request、time、hash（ARCH:614） | 首發（ARCH:527 query） | 是 |
| PL-29 | `GET /api/v1/stream` | ARCH:572 | SSE（ARCH:536） | 後續 | 可選 |

---

## Part 2 畫面對照

欄位說明：「更新頻率」為建議值，依據：即時卡片延遲 ≤ 5 秒（PRD5:121）、現行 Grafana 能源儀表板 5 秒刷新（infra/grafana/provisioning/dashboards/ems-overview.json:11）、裝置健康儀表板 30 秒（device-service-health.json:13）、警報與場域摘要後續改 SSE（ARCH:536）。

### 2.0 共用框架（另計，不含於七畫面合計）

| # | 元件 | 所需資料 | 端點＋欄位 | 單位 | 更新頻率 | 狀態 | 備註 |
|---|---|---|---|---|---|---|---|
| C1 | 頁首使用者（名稱＋角色） | 使用者名稱、角色 | E-04 `GET /api/auth/session`（auth.py:65-67）→ `username`、`role` | — | 載入時；遇 401 轉登入 | 已實作 | 角色中文用 `auth.session.role.*`：維運／資料匯入／唯讀（zh-Hant.ts:39-41）；未知角色收斂為 readonly（frontend/src/auth/types.ts:17-21） |
| C2 | 登出 | — | E-03 `POST /api/auth/logout`（auth.py:57-62）→ 204 | — | 動作 | 已實作 | 須同源 Origin（security.py:65-86） |
| C3 | 場域切換 | 場域清單、名稱 | PL-11 `GET /api/v1/sites`（ARCH:554）→ `site_id`、`timezone`（ARCH:601）、`name`（proposed） | — | 載入時 | 規劃中 | 今日 DB／API 無 site 範圍（ARCH:60）；「台北南港展覽館專案」為示意名稱，不存在於任何文件（DOMAIN:78-79） |
| C4 | 通知鈴未讀數 | 進行中且未 ACK 的警報數 | PL-17 `GET /api/v1/sites/{site_id}/alarms`（ARCH:560）依 state 計數 | 則 | 10 秒輪詢，後續 SSE | 規劃中 | 「未讀」= state `ACTIVE`（proposed 定義） |
| C5 | 資料更新時間（「更新 14:32:05」「5 秒前更新」） | 最新樣本時間 | E-18 `?limit=1&order=desc`（device_measurements.py:60-98）→ `time` | UTC，顯示 Asia/Taipei | 5 秒 | 已實作 | 限 OPS；以 PCC 電表最新樣本為準 |

小計：5 列，已實作 3、規劃中 2、缺口 0。

### 2.1 能源總覽 Main（PLAN:61-72）

| # | 元件 | 所需資料 | 端點＋欄位 | 單位 | 更新頻率 | 狀態 | 備註 |
|---|---|---|---|---|---|---|---|
| M01 | 能源流・電網（PCC 受電功率） | 即時輸入功率 | E-18 `GET /api/devices/{device_id}/measurements?limit=1&order=desc`（device_measurements.py:60-98）→ `power_kw` | kW | 5 秒 | 已實作 | 限 OPS（device_measurements.py:67）；唯一電表為模擬器 `sim-001`（008:11）；「哪台是 PCC」無模型（ARCH:602 assets 規劃中），前端需設定常數；`power_kw` 正負號語意未定義 |
| M02 | 能源流・太陽能 | PV 即時功率 | PL-12 `GET /api/v1/sites/{site_id}/summary`（ARCH:555）→ `pv_kw`（proposed） | kW | 5 秒，後續 SSE | 規劃中 | 無 PV 裝置與資料；`solar_inverter` 型別仍為 proposed（ADR-021:22）；無真機 adapter（ARCH:50） |
| M03 | 能源流・儲能（功率＋充放方向） | PCS 有效功率 | PL-12 → `bess_kw`（放電為正、充電為負，proposed） | kW | 5 秒 | 規劃中 | 來源為 PCS P（ARCH:380）；今日無 BESS 資料 |
| M04 | 能源流・廠區負載 | 負載功率 | PL-12 → `load_kw`（proposed，由伺服器以電網＋PV＋儲能放電計算） | kW | 5 秒 | 規劃中 | 無負載電表；前端不宜自行加總三個不同步的來源 |
| M05 | 需量卡・契約容量 | 契約容量 | PL-11 `GET /api/v1/sites`（ARCH:554）→ `grid_contract`（ARCH:601；建議欄名 `contract_kw`，proposed） | kW | 載入時 | 規劃中 | repo 內任何表或 API 皆無契約容量 |
| M06 | 需量卡・本月最高需量＋達約率 | 本月 15 分鐘需量最大值、比率 | G-03 `GET /api/v1/sites/{site_id}/demand?month=`（proposed）→ `month_peak.demand_kw`、`utilisation_pct` | kW、% | 每 15 分（區間結束） | 缺口 | E-18 無彙總、無 `until`，limit ≤ 1000（config.py:122）而取樣 1 秒，單次僅約 16.7 分鐘原始資料 |
| M07 | 系統狀態（系統正常／需注意） | 進行中警報依等級計數 | PL-17（ARCH:560）依 `severity` 計數；或 PL-12 `alarm_counts`（proposed） | — | 10 秒，後續 SSE | 規劃中 | Grafana 告警存在於上游（U-20）但未經 BFF 且需 admin 帳密，瀏覽器不可用 |
| M08 | KPI・即時用電 | 負載功率 | 同 M04 | kW | 5 秒 | 規劃中 | 與 M04 同源 |
| M09 | KPI・太陽能發電 | PV 功率 | 同 M02 | kW | 5 秒 | 規劃中 | 與 M02 同源 |
| M10 | KPI・儲能狀態（SOC、SOH、模式、放電功率） | SOC、SOH、模式、功率 | PL-12 → `bess_soc_pct`、`bess_soh_pct`、`bess_mode`、`bess_kw`（proposed） | %、%、列舉、kW | 5 秒 | 規劃中 | 模式列舉 `STANDBY`、`GRID_TIE`、`ISLAND`、`FAULT`（BESS:46-49，Draft） |
| M11 | KPI・今日節省（估算） | 節省金額 | G-06 `GET /api/v1/sites/{site_id}/savings?date=`（proposed）→ `savings_twd` | TWD（顯示 NT$） | 15 分 | 缺口 | repo 無任何費率資料（DOMAIN:70-75）；屬 PRD-0016（ARCH:754）；畫面須標「估算」 |
| M12 | 本日用電趨勢（00:00 至現在，15 分點） | 負載 15 分鐘平均序列 | PL-15 `GET /api/v1/assets/{asset_id}/measurements?from=&to=&resolution=15m`（ARCH:558）；負載序列由 PL-12 同一口徑計算 | kW | 60 秒或每區間結束 | 規劃中 | 今日 E-18 只能取約 16.7 分鐘原始資料，且只有電網功率 |
| M13 | 趨勢圖・契約容量線 | 契約容量 | 同 M05 | kW | 載入時 | 規劃中 | — |
| M14 | 能源組成（即時） | 三來源占比 | PL-12 → `grid_kw`、`pv_kw`、`bess_kw`（proposed），前端計算占比 | kW、% | 5 秒 | 規劃中 | 儲能僅在放電時計入供給組成（proposed 規則） |
| M15 | 即時警示卡 | 最新進行中警報 | PL-17（ARCH:560）→ `severity`、`title`、`first_at`（proposed） | — | 10 秒，後續 SSE | 規劃中 | 空狀態沿用設計文案「目前無警示事件」 |

小計：15 列，已實作 1、規劃中 12、缺口 2。不計入：標語、流線粗細公式（由 kW 推導）、「前往警報中心」連結。

### 2.2 即時監控 Monitor（PLAN:74-83）

| # | 元件 | 所需資料 | 端點＋欄位 | 單位 | 更新頻率 | 狀態 | 備註 |
|---|---|---|---|---|---|---|---|
| Q01 | 查詢列・量測點 | 電力量測點清單 | E-10 `GET /api/devices?type=electricity`（devices.py:88-101）→ `device_id`、`device_type`、`location` | — | 載入時 | 已實作 | 限 OPS；設計示意「PCC 台電受電點 · M-01」應改以 `location`＋`device_id` 呈現；現有電力裝置僅 `sim-001` |
| Q02 | 查詢列・指標選項（功率、電壓、電流、頻率、功率因數） | 該點可用訊號與單位 | E-12 `GET /api/devices/{device_id}/signals`（devices.py:120-133）→ `signal_name`、`unit`、`datatype` | — | 切換量測點時 | 已實作 | `sim-001` 訊號為 voltage（V）、current（A）、power_kw（kW）、energy_kwh（kWh）（008:21-24）；無頻率、功率因數，選項應依回傳停用 |
| Q03 | 查詢列・時間範圍（近 1 小時、24 小時、7 天、自訂） | 起訖時間 | PL-15（ARCH:558）`from`、`to` | ISO 8601 | — | 規劃中 | E-18 只有 `since`（device_measurements.py:46-57），無 `until`、無 offset，limit ≤ 1000；1 秒取樣下四種範圍都無法單次取得。過渡：近 1 小時可用 `since` 前移分頁 4 次（邊界列會重複，須去重） |
| Q04 | 查詢列・彙總（1 分、15 分、1 小時） | 彙總粒度 | PL-15 `resolution`（ARCH:558；粒度 ARCH:459） | — | — | 規劃中 | 建議對應：近 1 小時用 1m（60 點）、近 24 小時用 15m（96 點）、近 7 天用 1h（168 點） |
| Q05 | 匯出 CSV | 區間原始或彙總資料檔 | G-01 `GET /api/v1/sites/{site_id}/measurements/export`（proposed） | text/csv | 使用者觸發 | 缺口 | ARCH:522 將匯出列為 MVP 必須，但 ARCH §10.1 無對應端點 |
| Q06 | 歷史曲線・有效功率 | 24 小時、15 分點 | PL-15 `resolution=15m` → `power_kw`（沿用現行欄名） | kW | 60 秒 | 規劃中 | 限制同 Q03 |
| Q07 | 歷史小倍數・電壓 | 同上 | PL-15 → `voltage` | V | 60 秒 | 規劃中 | ±5 % 帶由前端依 380 V 基準繪製 |
| Q08 | 歷史小倍數・電流 | 同上 | PL-15 → `current` | A | 60 秒 | 規劃中 | — |
| Q09 | 即時讀值・有效功率（1 分鐘平均） | 最近 60 筆平均 | E-18 `?limit=60&order=desc`（device_measurements.py:60-98）→ `power_kw`，前端平均 | kW | 5 秒 | 已實作 | 對齊 Grafana「目前功率」1 分鐘平均並排除 ≥ 1000 kW 異常值（ems-overview.json:92） |
| Q10 | 即時讀值・電壓 | 最新值 | E-18 → `voltage` | V | 5 秒 | 已實作 | 三相線電壓 |
| Q11 | 即時讀值・電流 | 最新值 | E-18 → `current` | A | 5 秒 | 已實作 | — |
| Q12 | 即時讀值・累計電量 | 最新值 | E-18 → `energy_kwh` | kWh | 5 秒 | 已實作 | 累計計數器；Grafana 取 1 分鐘內最大值（ems-overview.json:280） |
| Q13 | 即時讀值・無效功率 | 最新值 | PL-15（ARCH:558）；PCC 讀取項含 Q（ARCH:381） | kvar | 5 秒 | 規劃中 | 現行量測表無此欄（init.sql:9-16） |
| Q14 | 即時讀值・頻率 | 最新值 | PL-15；PCC 讀取項含 f（ARCH:381） | Hz | 5 秒 | 規劃中 | 同上 |
| Q15 | 即時讀值・功率因數 | 最新值 | PL-15；PCC 讀取項含 PF（ARCH:381） | 無單位（0–1） | 5 秒 | 規劃中 | 今日僅是模擬器設定參數 `power_factor`（U-30，api/openapi.yml:141-149），非逐筆量測、未經 BFF |
| Q16 | 即時讀值・資料品質 | 品質旗標 | PL-15 → `quality`（ARCH:607；列舉 ARCH:435-439） | 列舉 | 5 秒 | 規劃中 | 現行無品質欄位 |
| Q17 | 全點位表・點位清單與 kW、V、A、更新時間 | 各點最新值 | E-10（devices.py:88-101）＋逐點 E-18（device_measurements.py:60-98）→ `power_kw`、`voltage`、`current`、`time` | kW、V、A、時間 | 5 秒 | 已實作 | 每點 1 次呼叫（N 點 N 次，每次 BFF 再打 2 個上游，ADR-025:46）；PV、PCS、分路負載點位今日不存在 |
| Q18 | 全點位表・kvar、Hz、PF、品質欄 | 各點最新值 | PL-15（ARCH:558） | kvar、Hz、—、列舉 | 5 秒 | 規劃中 | 同 Q13 至 Q16 |

小計：18 列，已實作 7、規劃中 10、缺口 1。

### 2.3 需量管理 Demand（PLAN:85-93；首發為唯讀顯示）

| # | 元件 | 所需資料 | 端點＋欄位 | 單位 | 更新頻率 | 狀態 | 備註 |
|---|---|---|---|---|---|---|---|
| D01 | KPI・契約容量 | 契約容量 | PL-11（ARCH:554）→ `grid_contract`（ARCH:601）；建議欄名 `contract_kw`（proposed） | kW | 載入時 | 規劃中 | — |
| D02 | KPI・本月最高需量＋發生區間 | 月最大 15 分鐘需量與時間 | G-03（proposed）→ `month_peak.demand_kw`、`month_peak.interval_start` | kW、ISO 8601 | 每 15 分 | 缺口 | 計費月以 Asia/Taipei 月界劃分（proposed） |
| D03 | KPI・目前 15 分鐘需量（區間） | 進行中區間平均 | E-18 `?since=<區間起點 UTC>&limit=1000&order=asc`（device_measurements.py:60-98）→ `power_kw` 前端平均；區間起訖由前端依 :00、:15、:30、:45 計算 | kW | 60 秒 | 已實作 | 15 分鐘 × 1 秒 = 900 筆，未超過 limit 1000（config.py:122）；限 OPS；前提是該電表 `power_kw` 為 PCC 輸入方向。首發建議改由 G-03 `current_interval` 提供 |
| D04 | KPI・超約風險（距契約 kW） | 餘裕、風險等級 | G-03 → `headroom_kw`、`risk_level`（proposed） | kW、列舉 | 60 秒 | 缺口 | 門檻對齊設計量表：≥ 90 % 警示、> 100 % 危險（PLAN:205） |
| D05 | 96 格 15 分鐘需量長條（今日） | 今日各區間平均 | PL-15 `resolution=15m`（ARCH:558）→ `power_kw`；或 G-03 `intervals_today`（proposed） | kW | 60 秒 | 規劃中 | 區間須對齊 :00、:15、:30、:45（Asia/Taipei），只計輸入方向（DOMAIN:32-33） |
| D06 | 長條圖・契約容量線 | 契約容量 | 同 D01 | kW | 載入時 | 規劃中 | — |
| D07 | 長條圖・本月最高需量線 | 月最大值 | 同 D02 | kW | 每 15 分 | 缺口 | — |
| D08 | 時間電價時段帶（夏月平日、夏月週六、非夏月平日、週日及離峰日） | 各日型時段 | G-04 `GET /api/v1/sites/{site_id}/tariff/tou-calendar?date=`（proposed） | HH:MM、列舉 | 每日 | 缺口 | repo 無任何電價資料（DOMAIN:70-75）；未核對前 `verified=false`，畫面維持「以台電公告為準」 |
| D09 | 本月電費估算（基本、流動、功率因數、超約附加、合計） | 估算金額 | G-05 `GET /api/v1/sites/{site_id}/billing/estimate?month=`（proposed） | TWD | 1 小時 | 缺口 | 後續（PRD-0016，ARCH:754）；超約部分加倍計收規則見 DOMAIN:73；功率因數今日無量測（Q15） |

小計：9 列，已實作 1、規劃中 3、缺口 5。

### 2.4 儲能管理 Storage（PLAN:95-105）

| # | 元件 | 所需資料 | 端點＋欄位 | 單位 | 更新頻率 | 狀態 | 備註 |
|---|---|---|---|---|---|---|---|
| S01 | SOC 環 | 電池 SOC | PL-12 → `bess_soc_pct`（proposed）；或 PL-15 BMS SOC（ARCH:379） | % | 5 秒 | 規劃中 | 無 BMS adapter（ARCH:50） |
| S02 | SOC 分帶刻度（95、30、25、10 %） | 門檻設定 | G-09 `GET /api/v1/sites/{site_id}/bess/settings`（proposed）→ `soc.*` | % | 載入時 | 缺口 | 數值見 BESS:94-97, 159-162（可調參數，未對外暴露） |
| S03 | SOH | 健康度 | PL-12 → `bess_soh_pct`（proposed）；或 PL-15（ARCH:379） | % | 60 秒 | 規劃中 | — |
| S04 | 充放電功率（放電 58 kW） | PCS 有效功率與方向 | PL-12 → `bess_kw`（放電為正，proposed）；或 PL-15（ARCH:380） | kW | 5 秒 | 規劃中 | — |
| S05 | 容量與可用能量（額定 kWh、可用 kWh、距備援下限小時數） | 額定能量、額定功率 | F-01：PL-13 `GET /api/v1/sites/{site_id}/assets`（ARCH:556）新增 `rated_energy_kwh`、`rated_power_kw`（proposed） | kWh、kW、h | 60 秒 | 缺口 | ARCH:602 assets 無額定欄位；可用能量 = SOC × 額定能量，距備援下限 = (SOC − 備援 %) × 額定能量 ÷ 放電功率，前端計算 |
| S06 | 運轉模式狀態機 | 目前模式 | PL-12 → `bess_mode`（proposed）；或 PL-15 PCS mode（ARCH:380；BESS:144） | 列舉 | 5 秒 | 規劃中 | 列舉見 4.1（BESS:46-49，Draft） |
| S07 | 充放電排程（時段、動作、目標 SOC） | 排程時窗 | PL-23 `GET /api/v1/sites/{site_id}/schedules`（ARCH:566；欄位 ARCH:612）；缺口欄位 F-02 `label`、`action`、`target_soc_pct`、`power_kw`（proposed） | HH:MM、%、kW | 載入時 | 規劃中 | 首發僅顯示（ARCH:525） |
| S08 | 排程執行率（目標 ≥ 80 %） | 實際／計畫 | G-10 `GET /api/v1/sites/{site_id}/schedules/{schedule_id}/runs`（proposed）→ `execution_pct` | % | 15 分 | 缺口 | 後續（ARCH:525 Pilot；WP-23，ARCH:809）；目標值見 DOMAIN:50-51 |
| S09 | 逐時實際 P（充電為負）＋ SOC 曲線 | 1 小時彙總序列 | PL-15 `resolution=1h`（ARCH:558） | kW、% | 5 分 | 規劃中 | — |
| S10 | BMS 電芯電壓 Vmax、Vmin | 極值 | PL-15（ARCH:379「cell min/max」） | V | 5 秒 | 規劃中 | BMS 摘要 1 秒、全電芯 5–10 秒（ARCH:455-456） |
| S11 | BMS 電芯溫度 Tmax、Tmin | 極值 | PL-15（ARCH:379「T」） | °C | 5 秒 | 規劃中 | — |
| S12 | BMS 絕緣阻抗 | 絕緣值 | PL-15（ARCH:379「絕緣」） | kΩ（顯示可換算 MΩ） | 10 秒 | 規劃中 | 建議 API 單位 kΩ（DOMAIN:34） |
| S13 | BMS 允許充、放電流 | 允許電流 | PL-15（ARCH:379；BESS:143） | A | 5 秒 | 規劃中 | 為功率命令的最高夾箝（BESS:119） |
| S14 | PCS P、Q | 有效、無效功率 | PL-15（ARCH:380「P/Q」） | kW、kvar | 5 秒 | 規劃中 | — |
| S15 | PCS 交流電壓、頻率 | V、f | PL-15（ARCH:380「V/f」） | V、Hz | 5 秒 | 規劃中 | — |
| S16 | PCS 直流電壓、電流 | 直流量 | PL-15（ARCH:380「DC/AC」） | V、A | 5 秒 | 規劃中 | — |
| S17 | PCS 能力上限（200 kW） | capability | PL-15（ARCH:380「capability」） | kW | 載入時 | 規劃中 | — |
| S18 | 保護門檻表（溫度 45、55、65 °C，電芯電壓，絕緣，L1–L4） | 門檻設定 | G-09（proposed）→ `temperature_c.*`、`cell_voltage_v.*`、`insulation_kohm.*`、`protection_levels[]` | °C、V、kΩ | 載入時 | 缺口 | 溫度 BESS:115-117；電芯硬限 3.65 V、2.5 V 見 BESS:112-113；3.55–3.60 V 預警、2.80 V 低壓、1 MΩ／500 kΩ 不在 EMS repo，出處為 Windows 側 `自建EMS專案\12_執行計畫說明書\_work\bms-spec-source.md:289-309`；BMS 門檻屬 BMS 本地權威（ARCH:119），EMS 僅唯讀顯示 |
| S19 | 時間電價時段底圖 | 今日時段 | G-04（proposed） | HH:MM、列舉 | 每日 | 缺口 | 同 D08 |

小計：19 列，已實作 0、規劃中 14、缺口 5。不計入：調度優先序文案（BESS:127-132，靜態）。

### 2.5 警報中心 Alarms（PLAN:107-114）

| # | 元件 | 所需資料 | 端點＋欄位 | 單位 | 更新頻率 | 狀態 | 備註 |
|---|---|---|---|---|---|---|---|
| A01 | 等級摘要（P0、P1、P2、資訊） | 依等級計數 | PL-17 `GET /api/v1/sites/{site_id}/alarms`（ARCH:560）→ 依 `severity`（proposed）計數 | 則 | 10 秒，後續 SSE | 規劃中 | ARCH 只提 P0、P1（ARCH:480）；Grafana 現行 severity 只有 `warning`、`critical`（rules.yaml:74, 151）；等級對照為 proposed（4.1） |
| A02 | 進行中清單（等級、來源設備、訊息、狀態、起始時間） | 警報實例 | PL-17 → `rule_id`、`state`、`first_at`、`last_at`（ARCH:609）＋`severity`、`device_id`、`title`、`message`（proposed） | — | 10 秒，後續 SSE | 規劃中 | 過渡方案 PL-05（PRD5:203）橋接 Grafana 只能取得 alertname、severity、summary、startsAt（api/openapi.yml:1106-1139），無 device_id（rules.yaml:228-229）、無 ACK |
| A03 | 分頁篩選（進行中、已擱置、全部） | 狀態篩選 | PL-17 查詢參數 `state`（proposed） | — | — | 規劃中 | — |
| A04 | 動作・確認（ACK） | 確認警報 | PL-18 `POST /api/v1/alarms/{alarm_id}/ack`（ARCH:561） | — | 動作 | 規劃中 | 首發（ARCH:523）；ACK 不等於清除（ARCH:472, 479）；權限 `alarm.ack`（ARCH:635） |
| A05 | 動作・擱置（SHELVE） | 擱置期限與理由 | PL-19 `POST /api/v1/alarms/{alarm_id}/shelve`（ARCH:562）；body 期限、理由（ARCH:473） | — | 動作 | 規劃中 | 後續（ARCH:523 將 suppress 列 Pilot） |
| A06 | 詳情・生命週期時間（NORMAL→PENDING→ACTIVE→ACKED→CLEARED） | 各轉換時間 | PL-17 → `first_at`、`last_at`、`acked_at`、`cleared_at`（ARCH:609 的 first、last、ack、clear） | ISO 8601 | 選取時 | 規劃中 | 逐筆轉換紀錄（含 PENDING 時間與 actor）屬 G-07 `transitions[]` |
| A07 | 詳情・Runbook | 處置步驟 | G-07 `GET /api/v1/sites/{site_id}/alarms/{alarm_id}`（proposed）→ `rule.runbook` | — | 選取時 | 缺口 | runbook 為規則屬性（ARCH:476）；P0、P1 必備（ARCH:480） |
| A08 | 詳情・通知升級（Telegram 維運群組 → 值班主管） | 通知送達狀態 | G-07 → `notifications[]`（proposed） | — | 選取時 | 缺口 | outbox 與送達狀態（ARCH:478）；現行只有 Grafana → Telegram 聯絡點 `Telegram`（contact-points.yaml:5-8）；升級屬 Pilot（ARCH:523） |
| A09 | 歷史（近 7 天） | 已清除警報 | PL-17 `?from=&to=&state=CLEARED`（proposed 參數）；或 PL-16 `GET /api/v1/sites/{site_id}/events`（ARCH:559） | — | 載入時 | 規劃中 | 保存 ≥ 12 個月（ARCH:458） |

小計：9 列，已實作 0、規劃中 7、缺口 2。

### 2.6 設備分析 Devices（PLAN:116-123）

| # | 元件 | 所需資料 | 端點＋欄位 | 單位 | 更新頻率 | 狀態 | 備註 |
|---|---|---|---|---|---|---|---|
| V01 | KPI・裝置總數 | 裝置數 | E-10 `GET /api/devices`（devices.py:88-101；不帶 limit 回全部）→ 陣列長度 | 台 | 30 秒 | 已實作 | 裸陣列無 total（PRD5:228, 240-244） |
| V02 | KPI・通訊正常／資料延遲 | 依最後上線時間分類 | E-10 → `last_seen_at` 與現在的差距（門檻 120 秒，proposed，對齊 Grafana 2 分鐘停滯規則 rules.yaml:93-158） | 台 | 30 秒 | 已實作 | `last_seen_at` 於收到該裝置 MQTT 訊息時更新（discovery.py:116, 123）；不可用 `?stale=`（語意不同，見 4.7） |
| V03 | KPI・維護中 | maintenance 裝置數 | E-10 `?status=maintenance` | 台 | 30 秒 | 已實作 | DB 允許 maintenance（003:26-27），但沒有任何 API 能將裝置轉入，今日恆為 0；前端尚不認得此值（frontend/src/api/types.ts:67-72） |
| V04 | KPI・待人工確認 | candidate 裝置數 | E-10 `?status=candidate` | 台 | 30 秒 | 已實作 | — |
| V05 | KPI・30 天可用率 | 全場可用率 | G-08 `GET /api/v1/sites/{site_id}/devices/availability?window=30d`（proposed）→ `meta.site_availability_pct` | % | 1 小時 | 缺口 | repo 無可用率計算 |
| V06 | 設備清單（類型、協定、位置、生命週期、最後上線；篩選、排序） | 裝置列 | E-10 → `device_type`、`protocol`、`location`、`status`、`last_seen_at`（另有 `vendor`、`model`、`gateway_id`、`classified_by`、`ai_confidence`）；篩選 `status`、`type`；排序 7 欄（devices.py:36-39） | — | 30 秒 | 已實作 | limit 1–500＋offset；排序 NULLS LAST（device_repo.py:66） |
| V07 | 設備清單・通訊欄（GOOD、STALE） | 通訊狀態 | E-10 → `last_seen_at` 推導（同 V02） | 列舉 | 30 秒 | 已實作 | 列舉名稱見 4.1（proposed `comm_state`） |
| V08 | 設備清單・可用率欄 | 各裝置可用率 | G-08 → `availability_pct` | % | 1 小時 | 缺口 | — |
| V09 | AI 確認佇列・清單（來源、建議類型、信心） | candidate 依信心排序 | E-10 `?status=candidate&sort=ai_confidence&order=asc`（devices.py:88-101）→ `device_id`、`device_type`（AI 建議值）、`ai_confidence`、`protocol`、`gateway_id`；來源以 E-13 `digest.sample_digest.topic` 呈現 | 0–1 | 30 秒 | 已實作 | 與現行確認佇列頁同一用法（zh-Hant.ts:141）；IP:port 不對外（009:27；models.py:56-63） |
| V10 | AI 確認佇列・證據訊號 | AI 建議訊號與說明 | E-13 `GET /api/devices/{device_id}/human-review`（devices.py:136-149）→ `digest.suggested_signals[]`、`digest.summary_zh`、`digest.why_low_confidence`、`summary_source` | — | 選取時 | 已實作 | 一律純文字渲染（PRD5 §9.5）；無 digest 時 404 |
| V11 | AI 確認佇列・動作（確認、修正類型、退回） | 狀態轉換 | E-14 `POST …/confirm`、E-15 `POST …/override`（body `device_type`＋`signals[]`）、E-16 `POST …/reject`（devices.py:152-201） | — | 動作 | 已實作 | confirm 僅限 candidate（409，device-service routes/devices.py:204-205）；reject 會把裝置改為 `retired`（退役），不是退回佇列 |
| V12 | 狀態分布・生命週期 | 各狀態數 | E-10 → 依 `status` 分組 | % | 30 秒 | 已實作 | — |
| V13 | 狀態分布・通訊品質 | 各通訊狀態數 | E-10 → `last_seen_at` 推導 | % | 30 秒 | 已實作 | — |

小計：13 列，已實作 11、規劃中 0、缺口 2。

### 2.7 報表中心 Reports（PLAN:125-131）

| # | 元件 | 所需資料 | 端點＋欄位 | 單位 | 更新頻率 | 狀態 | 備註 |
|---|---|---|---|---|---|---|---|
| R01 | 篩選・場域 | 場域清單 | PL-11 `GET /api/v1/sites`（ARCH:554） | — | 載入時 | 規劃中 | — |
| R02 | 篩選・報表類型、期間＋「產生報表」 | 建立報表 | G-12 `POST /api/v1/sites/{site_id}/reports`（proposed） | — | 動作 | 缺口 | 後續（ARCH:522 Production；WP-34，ARCH:825） |
| R03 | 月報 KPI・總用電、市電、太陽能、儲能放電 | 期間電能 | G-11 `GET /api/v1/sites/{site_id}/reports/energy?period=month&month=`（proposed）→ `totals.*_kwh` | kWh | 使用者觸發 | 缺口 | 過渡：市電部分可用 E-18 取期間首、末各 1 筆 `energy_kwh` 相減（2 次呼叫；計數器重置即失真） |
| R04 | 月報 KPI・最高需量（日期、時段） | 月最大需量 | G-03 `?month=`（proposed）→ `month_peak.*` | kW | 使用者觸發 | 缺口 | 與 D02 同端點 |
| R05 | 月報 KPI・電費估算 | 估算金額 | G-05（proposed）→ `total_twd` | TWD | 使用者觸發 | 缺口 | 後續（ARCH:754） |
| R06 | 每日堆疊長條（31 日 × 市電、太陽能、儲能） | 逐日電能 | G-11 → `days[]` | kWh | 使用者觸發 | 缺口 | — |
| R07 | 已產生報表清單＋下載 | 報表清單、檔案 | G-12 `GET /api/v1/sites/{site_id}/reports`、`GET …/reports/{report_id}/download`（proposed） | — | 載入時 | 缺口 | 後續 |
| R08 | 匯出 PDF、CSV（頁首按鈕） | 目前報表檔 | G-12 download `?format=`（proposed） | — | 動作 | 缺口 | — |
| R09 | 稽核紀錄（唯讀） | 稽核事件 | PL-28 `GET /api/v1/sites/{site_id}/audit-events`（ARCH:571）；資料已存在 `device_audit_log`（014_create_device_audit_log.sql:17-33），但無任何讀取 API（audit_repo.py 只有寫入與計數） | — | 60 秒 | 規劃中 | 首發（ARCH:527；PRD5:353 AC-6）；事件列舉見 4.1 |
| R10 | 指令紀錄（唯讀） | 指令與結果 | PL-20 `GET /api/v1/sites/{site_id}/commands`（ARCH:563；欄位 ARCH:610） | — | 60 秒 | 規劃中 | 後續（MVP 無寫入指令，ARCH:524）；首發時此表為空 |

小計：10 列，已實作 0、規劃中 3、缺口 7。

---

## Part 3 缺口總表

### 3.1 建議介面共通約定（2026-09-23 協調決議；僅適用 proposed 端點，現行路由維持原樣）

| 項目 | 約定 |
|---|---|
| 路徑 | BFF 命名空間 `/api/v1/sites/{site_id}/…`；首發為單一場域，`site_id` 由 BFF 設定（例 `site-001`，同 ARCH:415 範例） |
| 成功回應 | `{"success": true, "data": <物件或陣列>, "error": null, "meta": {…}}` |
| 失敗回應 | `{"success": false, "data": null, "error": {"code": "<錯誤碼>", "message": "<訊息>"}, "meta": {}}` |
| 分頁 | 事件與時序清單用 cursor：`?cursor=<不透明字串>&limit=<1–1000>`，回 `meta.next_cursor`（字串或 null）、`meta.limit`；有界集合一次回完，`meta.next_cursor = null` |
| 時間參數 | `from`（含）、`to`（不含），ISO 8601 UTC（`Z`）；回應時間一律 UTC；`meta.timezone` = 場域時區（`Asia/Taipei`，ARCH:449, 601）；日、月、15 分區間依場域時區對齊 |
| 寫入 | 一律帶 `Idempotency-Key`（UUID）；更新既有資源另帶 `If-Match: <ETag>`，不符回 412、缺少回 428；建立型寫入沒有既有版本，`If-Match` 不適用 |
| 角色 | 標示「今日通道角色」（OPS、INGEST、READONLY）＋「目標產品權限」；ARCH:635 已列 `alarm.ack`、`command.pcs.setpoint`、`config.deploy`，其餘權限名稱皆為 proposed |
| 欄位命名 | snake_case；新數值欄帶單位後綴 `_kw`、`_kwh`、`_pct`、`_twd`、`_v`、`_a`、`_c`、`_kohm`、`_s`（proposed）；既有欄位 `voltage`、`current`、`power_kw`、`energy_kwh` 沿用原名 |
| 錯誤碼（proposed） | `VALIDATION_FAILED`（422）、`UNAUTHENTICATED`（401）、`FORBIDDEN`（403）、`NOT_FOUND`（404）、`CONFLICT`（409）、`PRECONDITION_FAILED`（412）、`PRECONDITION_REQUIRED`（428）、`RATE_LIMITED`（429）、`UPSTREAM_UNAVAILABLE`（502）、`NOT_CONFIGURED`（503） |
| 檔案下載 | 本體為檔案（`text/csv`、`application/pdf`），不套 envelope；錯誤仍回 envelope JSON |
| 過渡影響 | 現行路由為裸陣列＋`{detail}`，proposed 為 envelope；前端 liveFetcher 目前只讀 `detail`（frontend/src/api/liveFetcher.ts:69-73），須擴充兩種解析 |

### 3.2 缺口總表（依畫面）

「首發」= ARCH §9.1 MVP 欄（ARCH:516-529；對應 WP-15 site/device/trend/alarm Web，ARCH:796）；「後續」= Pilot 或 Production 欄。

| 畫面 | ID | 端點或變更（proposed） | 服務列 | 優先序 | 分期依據 |
|---|---|---|---|---|---|
| 能源總覽 | G-03 | `GET /api/v1/sites/{site_id}/demand` | M06 | 首發 | ARCH:525（Schedule/demand display，MVP） |
| 能源總覽 | G-06 | `GET /api/v1/sites/{site_id}/savings` | M11 | 後續 | ARCH:754（PRD-0016 Tariff/Demand/Optimization） |
| 即時監控 | G-01 | `GET /api/v1/sites/{site_id}/measurements/export` | Q05 | 首發 | ARCH:522（Trends/query/export，MVP 必須） |
| 需量管理 | G-03 | 同上 | D02、D04、D07 | 首發 | ARCH:525 |
| 需量管理 | G-04 | `GET /api/v1/sites/{site_id}/tariff/tou-calendar` | D08 | 首發 | ARCH:525（display） |
| 需量管理 | G-05 | `GET /api/v1/sites/{site_id}/billing/estimate` | D09 | 後續 | ARCH:754 |
| 儲能管理 | G-09 | `GET /api/v1/sites/{site_id}/bess/settings` | S02、S18 | 首發 | ARCH:521（limits，MVP 必須） |
| 儲能管理 | F-01 | PL-13 `GET /api/v1/sites/{site_id}/assets` 新增 `rated_energy_kwh`、`rated_power_kw` | S05 | 首發 | ARCH:520-521 |
| 儲能管理 | F-02 | PL-23 `GET /api/v1/sites/{site_id}/schedules` 新增 `label`、`action`、`target_soc_pct`、`power_kw` | S07（規劃中列的缺口欄位） | 首發 | ARCH:525 |
| 儲能管理 | G-10 | `GET /api/v1/sites/{site_id}/schedules/{schedule_id}/runs` | S08 | 後續 | ARCH:525（Pilot）；ARCH:809（WP-23） |
| 儲能管理 | G-04 | 同上 | S19 | 首發 | ARCH:525 |
| 警報中心 | G-07 | `GET /api/v1/sites/{site_id}/alarms/{alarm_id}` | A07（首發）、A08（後續） | 分拆 | ARCH:480, 523 |
| 設備分析 | G-08 | `GET /api/v1/sites/{site_id}/devices/availability` | V05、V08 | 後續 | ARCH §9.1 MVP 未列可用率（ARCH:526 僅列 device/profile/connection） |
| 報表中心 | G-11 | `GET /api/v1/sites/{site_id}/reports/energy` | R03、R06 | 後續 | ARCH:522（scheduled report，Production）；ARCH:825（WP-34） |
| 報表中心 | G-12 | `POST`、`GET /api/v1/sites/{site_id}/reports`；`GET …/reports/{report_id}/download` | R02、R07、R08 | 後續 | 同上 |
| 報表中心 | G-03 | 同上（`?month=`） | R04 | 首發 | ARCH:525 |
| 報表中心 | G-05 | 同上 | R05 | 後續 | ARCH:754 |
| 跨畫面 | G-13 | 唯讀角色可讀（授權變更，非新端點） | 所有讀取列 | 首發 | ARCH:518, 529；PRD5:83（管理層／客戶唯讀 persona） |
| 跨畫面（非阻擋） | G-02 | `GET /api/v1/sites/{site_id}/measurements/latest` | Q17（效能） | 後續 | 可由 PL-29 SSE 取代（ARCH:536, 572） |

合計：11 組新端點（13 條路由）＋ 2 項欄位缺口（F-01、F-02）＋ 1 項授權缺口（G-13）＋ 1 項非阻擋建議（G-02）。

### 3.3 缺口端點建議形狀（全部 proposed）

以下範例為示意形狀；`//` 為說明註解，不屬於回應內容。所有回應皆套 3.1 的 envelope。

**G-01 量測匯出 CSV**（Monitor Q05；首發）

```text
GET /api/v1/sites/{site_id}/measurements/export
    ?device_id=sim-001                 // 必填；首發 = 現行 device_id（ARCH:616 規劃遷移為 asset）
    &from=2026-09-22T16:00:00Z         // 必填，含
    &to=2026-09-23T16:00:00Z           // 必填，不含
    &resolution=raw                    // raw、1m、15m、1h；預設 raw
    &format=csv
200 text/csv; charset=utf-8
    Content-Disposition: attachment; filename="sim-001_20260923.csv"
    欄位列：time,time_local,device_id,voltage,current,power_kw,energy_kwh
    // time = UTC ISO 8601；time_local = Asia/Taipei；單位 V、A、kW、kWh
    // resolution 非 raw 時：voltage、current、power_kw 為區間平均，energy_kwh 取區間末值
錯誤：envelope JSON；區間過大回 VALIDATION_FAILED（建議上限：raw 31 天）
角色：今日 OPS（建議開放 READONLY，見 G-13）；目標權限 measurement.export（proposed）
```

**G-02 批次最新值**（非阻擋；後續）

```text
GET /api/v1/sites/{site_id}/measurements/latest?device_ids=sim-001,plc-001
data: [ { "device_id": "sim-001", "time": "2026-09-23T06:32:05Z",
          "values": { "voltage": 380.4, "current": 307.0, "power_kw": 186.0, "energy_kwh": 1284562.0 },
          "quality": null } ]               // quality 待 ARCH:607 品質模型落地
meta: { "next_cursor": null }
角色：OPS、READONLY；measurement.read（proposed）
```

**G-03 需量摘要**（Main M06；Demand D02、D04、D07；Reports R04；首發）

```text
GET /api/v1/sites/{site_id}/demand?month=2026-09
data: {
  "site_id": "site-001",
  "month": "2026-09",
  "meter_device_id": "sim-001",            // 作為 PCC 受電點的電表
  "contract_kw": 500.0,                    // = sites.grid_contract（ARCH:601）
  "interval_minutes": 15,
  "current_interval": { "start": "2026-09-23T06:30:00Z", "end": "2026-09-23T06:45:00Z",
                        "demand_kw": 186.0, "complete": false },
  "month_peak": { "demand_kw": 428.0, "interval_start": "2026-09-12T08:45:00Z" },
  "utilisation_pct": 85.6,                 // month_peak.demand_kw ÷ contract_kw × 100
  "headroom_kw": 72.0,                     // contract_kw − month_peak.demand_kw
  "risk_level": "low",                     // low < 90 %、medium 90–100 %、high > 100 %
  "intervals_today": [ { "start": "2026-09-22T16:00:00Z", "demand_kw": 0.0, "complete": true } ]   // 最多 96 筆
}
meta: { "timezone": "Asia/Taipei", "as_of": "2026-09-23T06:32:05Z", "next_cursor": null }
定義：需量 = PCC 輸入方向 15 分鐘平均功率，區間對齊 :00、:15、:30、:45（場域時區）；月最高值計費（DOMAIN:72-73）
角色：OPS、READONLY；demand.read（proposed）
```

**G-04 時間電價時段**（Demand D08；Storage S19；首發，僅顯示）

```text
GET /api/v1/sites/{site_id}/tariff/tou-calendar?date=2026-09-23
data: {
  "tariff_plan": "[PLACEHOLDER] 台電時間電價方案",
  "effective_from": "YYYY-MM-DD",
  "verified": false,                       // 未依台電公告核對前一律 false，畫面顯示「以台電公告為準」
  "today": { "date": "2026-09-23", "day_type": "summer_weekday" },
  "day_types": [
    { "day_type": "summer_weekday",     "periods": [ { "start": "HH:MM", "end": "HH:MM", "period": "off_peak" } ] },
    { "day_type": "summer_saturday",    "periods": [ … ] },
    { "day_type": "non_summer_weekday", "periods": [ … ] },
    { "day_type": "sunday_offpeak_day", "periods": [ … ] }
  ]
}
period ∈ peak、mid_peak、off_peak；不含任何費率數字（DOMAIN:70-75）；資料為人工維護的場域設定
角色：OPS、READONLY；tariff.read（proposed）
```

**G-05 電費估算**（Demand D09；Reports R05；後續）

```text
GET /api/v1/sites/{site_id}/billing/estimate?month=2026-09
data: {
  "month": "2026-09", "currency": "TWD", "is_estimate": true,
  "basic_charge_twd": number, "energy_charge_twd": number,
  "pf_avg": number,                        // 0–1
  "pf_adjustment_twd": number,
  "over_contract_surcharge_twd": number,
  "total_twd": number,
  "tariff_plan": string, "computed_at": "ISO 8601"
}
前提：費率表（repo 目前不存在）與 PF 量測（Q15）
角色：OPS、READONLY；billing.read（proposed）
```

**G-06 節省估算**（Main M11；後續）

```text
GET /api/v1/sites/{site_id}/savings?date=2026-09-23
data: { "date": "2026-09-23", "savings_twd": number, "is_estimate": true,
        "method": "tou_arbitrage+peak_shaving+pv_self_consumption", "baseline": string, "computed_at": "ISO 8601" }
角色：OPS、READONLY；billing.read（proposed）
```

**G-07 警報詳情**（Alarms A06 延伸、A07、A08；runbook 首發、通知升級後續）

```text
GET /api/v1/sites/{site_id}/alarms/{alarm_id}
ETag: "<alarm version>"                    // 供 PL-18、PL-19 的 If-Match
data: {
  …PL-17 清單欄位（3.4）…,
  "transitions": [ { "state": "PENDING", "at": "ISO 8601", "actor": "system", "note": null } ],
  "rule": { "rule_id": string, "version": string, "name": string, "severity": "P1",
            "threshold": string, "delay_s": int, "hysteresis": string, "owner": string,      // ARCH:476
            "runbook": { "title": string, "steps": [string], "url": string or null } },
  "notifications": [ { "channel": "telegram", "target": string,
                       "status": "queued",   // queued、sent、failed、dead_letter（ARCH:478）
                       "attempts": int, "sent_at": "ISO 8601 or null" } ]
}
角色：OPS、READONLY；alarm.read（proposed）
```

**G-08 裝置可用率**（Devices V05、V08；後續）

```text
GET /api/v1/sites/{site_id}/devices/availability?window=30d
data: [ { "device_id": "sim-001", "window_start": "ISO 8601", "window_end": "ISO 8601",
          "availability_pct": 99.4, "online_s": int, "expected_s": int,
          "gap_count": int, "longest_gap_s": int } ]
meta: { "site_availability_pct": 99.4, "definition": "1m_bucket_with_data", "next_cursor": null }
定義：窗口內「至少有一筆資料的 1 分鐘區間」比例；無量測表的裝置改以 last_seen_at 心跳估算
角色：OPS、READONLY；device.read（proposed）
```

**G-09 BESS 設定與保護門檻**（Storage S02、S18；首發，唯讀）

```text
GET /api/v1/sites/{site_id}/bess/settings
ETag: "<settings version>"
data: {
  "version": string, "source": "tunable-parameters",
  "soc": { "max_pct": 95, "reserve_pct": 25, "island_floor_pct": 10,
           "blackstart_min_pct": 30, "hysteresis_pct": 3 },                        // BESS:94-97, 159-163
  "temperature_c": { "derate": 45, "pause": 55, "shutdown": 65, "charge_block_below": 0 },   // BESS:114-117, 165
  "cell_voltage_v": { "stop_charge": 3.65, "stop_discharge": 2.50,                  // BESS:112-113
                      "prewarn_high_min": 3.55, "prewarn_high_max": 3.60, "prewarn_low": 2.80 },   // 見 S18 出處
  "insulation_kohm": { "warn": 1000, "trip": 500 },
  "protection_levels": [ { "level": "L1", "action": "alarm" }, { "level": "L2", "action": "derate" },
                         { "level": "L3", "action": "block_charge_discharge" }, { "level": "L4", "action": "emergency_trip" } ],
  "owner": { "soc": "ems_policy", "temperature": "ems_policy", "cell_voltage": "bms", "insulation": "bms" }
}
寫入不在首發（屬 config.deploy，ARCH:635）
角色：OPS、READONLY；bess.settings.read（proposed）
```

**G-10 排程執行紀錄**（Storage S08；後續）

```text
GET /api/v1/sites/{site_id}/schedules/{schedule_id}/runs?from=&to=&cursor=&limit=
data: [ { "run_id": string, "schedule_id": string, "schedule_version": string,
          "window_start": "ISO 8601", "window_end": "ISO 8601",
          "action": "discharge",               // charge、discharge
          "planned_energy_kwh": number, "actual_energy_kwh": number,
          "execution_pct": number,             // actual ÷ planned × 100；夜尖峰目標 ≥ 80 %（DOMAIN:50-51）
          "status": "completed" } ]            // scheduled、running、completed、missed
meta: { "next_cursor": string or null, "limit": int }
角色：OPS、READONLY；schedule.read（proposed）
```

**G-11 電能報表**（Reports R03、R06；後續）

```text
GET /api/v1/sites/{site_id}/reports/energy?period=month&month=2026-08      // 或 period=day&date=2026-09-22
data: {
  "period": "month", "start": "ISO 8601", "end": "ISO 8601",
  "totals": { "load_kwh": number, "grid_import_kwh": number, "grid_export_kwh": number,
              "pv_kwh": number, "bess_charge_kwh": number, "bess_discharge_kwh": number },
  "peak_demand": { "demand_kw": number, "interval_start": "ISO 8601" },     // 與 G-03 同一口徑
  "days": [ { "date": "2026-08-01", "load_kwh": number, "grid_import_kwh": number,
              "pv_kwh": number, "bess_discharge_kwh": number } ]              // 月報最多 31 筆；日報改為 hours[]
}
meta: { "timezone": "Asia/Taipei", "next_cursor": null }
角色：OPS、READONLY；report.read（proposed）
```

**G-12 報表產生、清單、下載**（Reports R02、R07、R08；後續）

```text
POST /api/v1/sites/{site_id}/reports
     Idempotency-Key: <uuid>                  // 建立型寫入，無 If-Match
     body: { "report_type": "energy_monthly",  // energy_daily、energy_monthly
             "period": "2026-08",               // 日報為 YYYY-MM-DD
             "formats": ["pdf", "csv"] }
     202 data: { "report_id": string, "status": "queued" }
GET  /api/v1/sites/{site_id}/reports?cursor=&limit=
     data: [ { "report_id": string, "report_type": string, "period": string,
               "status": "ready",               // queued、ready、failed
               "created_at": "ISO 8601", "created_by": string, "formats": ["pdf", "csv"] } ]
     meta: { "next_cursor": string or null, "limit": int }
GET  /api/v1/sites/{site_id}/reports/{report_id}/download?format=pdf
     200 application/pdf 或 text/csv（檔案，不套 envelope）
角色：讀取 OPS、READONLY（report.read，proposed）；建立 OPS（report.create，proposed）
```

**G-13 唯讀角色讀取授權**（跨畫面；首發）

- 問題：E-10 至 E-18 全部限 OPS（…/routes/devices.py:90；…/routes/device_measurements.py:67；ADR-025:34）；唯讀角色只能使用 deprecated 的 E-19。ADR-025:47 已註明放寬唯讀需另立 ADR。
- 建議：所有 proposed 與規劃中的唯讀端點接受 READONLY；「不需特權即可由 device 解析量測域」依 ADR-025:47 另立 ADR。

**F-01 資產額定欄位**（Storage S05；首發）：PL-13 資產項目新增 `rated_energy_kwh`（kWh）、`rated_power_kw`（kW）。

**F-02 排程顯示欄位**（Storage S07；首發）：PL-23 排程項目新增 `label`（例「夜尖峰放電」）、`action`（`charge`、`discharge`）、`target_soc_pct`（%）、`power_kw`（kW）。

### 3.4 規劃中端點之建議形狀（路徑依 ARCH 原文；除 ARCH 已列欄位外皆為 proposed）

| ID | 路徑（ARCH 原文） | 建議查詢參數 | 建議 `data` 欄位 | 權限 |
|---|---|---|---|---|
| PL-11 | `GET /api/v1/sites`（ARCH:554） | — | `site_id`、`organization_id`、`timezone`（ARCH:601）、`name`（proposed）、`contract_kw`（對應 ARCH:601 `grid_contract`，欄名 proposed） | site.read（proposed） |
| PL-12 | `GET /api/v1/sites/{site_id}/summary`（ARCH:555） | — | `as_of`、`grid_kw`（輸入為正）、`pv_kw`、`bess_kw`（放電為正）、`load_kw`、`bess_soc_pct`、`bess_soh_pct`、`bess_mode`、`contract_kw`、`alarm_counts`（`P0`、`P1`、`P2`、`INFO`）、`quality`；全部 proposed；後續以 SSE 推送（ARCH:536） | site.read（proposed） |
| PL-13 | `GET /api/v1/sites/{site_id}/assets`（ARCH:556） | `type`、`cursor` | `asset_id`、`site_id`、`parent_id`、`type`、`lifecycle`（ARCH:602）＋F-01 | site.read（proposed） |
| PL-15 | `GET /api/v1/assets/{asset_id}/measurements`（ARCH:558） | `from`、`to`、`resolution`（raw、1m、15m、1h；ARCH:459）、`cursor`（ARCH:558）、`signals`（逗號分隔，proposed） | `[ { time, values: { <signal>: 數值、布林、字串或 null }, quality: { <signal>: GOOD 等 } } ]`；`meta`：`resolution`、`aggregate`（mean）、`units`、`next_cursor`；首發 `asset_id` = 現行 `device_id` | measurement.read（proposed） |
| PL-17 | `GET /api/v1/sites/{site_id}/alarms`（ARCH:560） | `state`、`severity`、`from`、`to`、`cursor`、`limit` | `alarm_id`、`rule_id`、`state`、`first_at`、`last_at`、`acked_at`、`cleared_at`（ARCH:609）＋`severity`、`device_id`、`title`、`message`、`acked_by`、`shelved_until`、`shelve_reason`、`etag`（proposed） | alarm.read（proposed） |
| PL-18 | `POST /api/v1/alarms/{alarm_id}/ack`（ARCH:561） | 標頭 `Idempotency-Key`、`If-Match` | body `{ "note": 選填 }`；回更新後的警報 | alarm.ack（ARCH:635）；今日對應 OPS |
| PL-19 | `POST /api/v1/alarms/{alarm_id}/shelve`（ARCH:562） | 標頭同上 | body `{ "until": ISO 8601 或 "duration_s": int, "reason": string }`（期限與理由必填，ARCH:473） | alarm.shelve（proposed）；今日對應 OPS |
| PL-20 | `GET /api/v1/sites/{site_id}/commands`（ARCH:563） | `status`、`from`、`to`、`cursor` | `command_id`、`site_id`、`target`、`type`、`requested`、`final`、`status`（ARCH:485-488）、`expires_at`、`issued_by`、`reason`、`issued_at`（ARCH:491, 610） | command.read（proposed） |
| PL-23 | `GET /api/v1/sites/{site_id}/schedules`（ARCH:566） | `status` | `schedule_id`、`site_id`、`version`、`window`、`strategy`、`status`、`approved_by`（ARCH:612）＋F-02 | schedule.read（proposed） |
| PL-28 | `GET /api/v1/sites/{site_id}/audit-events`（ARCH:571） | `event_type`、`device_id`、`actor`、`from`、`to`、`cursor` | 首發直接對應既有表 `device_audit_log`（014:17-28）：`id`、`event_time`、`event_type`、`device_id`、`actor`、`outcome`、`request_id`、`correction_id`、`detail`；`actor_key_id`、`salt_version` 僅給 auditor（proposed）；日後擴為 ARCH:614 欄位 | audit.read（proposed） |
| PL-29 | `GET /api/v1/stream`（ARCH:572） | — | SSE 事件：場域摘要、警報、指令（ARCH:536） | 依事件類型 |

### 3.5 優先序總表

| 優先序 | 項目 |
|---|---|
| 首發（ARCH MVP） | 缺口：G-01 匯出、G-03 需量摘要、G-04 時間電價時段、G-07（transitions、rule、runbook）、G-09 BESS 設定、G-13 唯讀授權、F-01、F-02。規劃中：PL-11、PL-12、PL-13、PL-15、PL-17、PL-18、PL-23、PL-28 |
| 後續（Pilot、Production） | 缺口：G-02、G-05、G-06、G-07（notifications）、G-08、G-10、G-11、G-12。規劃中：PL-19、PL-20、PL-29 |

---

## Part 4 命名對齊（設計須逐字採用）

### 4.1 列舉

| 領域 | 逐字值 | 中文顯示 | 狀態與出處 |
|---|---|---|---|
| 裝置生命週期 `status` | `candidate`、`confirmed`、`active`、`maintenance`、`retired` | 候選、已確認、運轉中、（維護中：proposed）、已退役；未知值顯示「未知狀態」 | 已實作：003:26-27；zh-Hant.ts:48-52。`active` 於現階段保留未用（ADR-010:23），實際資料多為 `confirmed`（008:11-13）；`maintenance` 無轉入 API |
| 候選審閱逾期旗標 `stale` | 查詢參數 `stale=true`／`false` | 過時 | 已實作（僅篩選）：語意為 candidate 逾 30 天未處理（ADR-010:31），目前沒有程式寫入（device_repo.py:55-58 僅讀）；**不是通訊狀態** |
| 通訊狀態 `comm_state` | `GOOD`、`STALE` | 通訊正常、資料延遲 | proposed：前端以 `last_seen_at` 推導（門檻 120 秒） |
| 分類來源 `classified_by` | `ai`、`human`、`manual_override`、`migration_backfill` | — | 已實作：003:28-29；後三者為凍結紀錄（010:44） |
| 裝置類型 `device_type`（AI 閉集） | `electricity`、`temperature`、`pressure`、`motor`、`valve`、`hvac`、`unknown` | — | 已實作：device-service llm/prompt.py:9；DB 為自由文字（ADR-021:16） |
| 裝置類型擴充 | `battery`、`solar_inverter`、`ev_charger`、`grid_meter` | — | proposed：ADR-021:22（ADR 狀態 Proposed）；現行 AI 無法輸出 |
| 不存在的類型字串 | `electricity_meter`、`plc`（registry）、`temperature_sensor`、`humidity_sensor`、消防盤 | — | 只出現在前端 mock（frontend/src/api/fixtures.ts:16, 32, 48, 64），設計勿採用 |
| 工廠量測表 `device_type` | `plc`、`sensor` | — | 已實作：api/openapi.yml:1037-1043（量測表欄位，與 registry 不同） |
| 訊號 `datatype` | `float`、`int`、`bool`、`enum` | 資料型別 | 已實作：004:21 |
| 訊號 `direction` | `read`、`write`、`read_write` | 方向 | 已實作：004:22 |
| 訊號 `status` | `active`、`retired` | — | 已實作：004:20 |
| 修正 `verdict` | `wrong_classification`、`wrong_signals`、`wrong_unit`、`missed_signal`、`good_with_note` | — | 已實作：007:23-24 |
| digest `summary_source` | `llm`、`system_fallback` | AI 產生、系統備援（未知值：來源不明） | 已實作：005:14；zh-Hant.ts:145 |
| 稽核 `event_type` | `freeze_override`、`ai_feedback_create`、`demote`、`deactivate`、`rate_limit_exceeded`、`guardrail_block`、`status_advance` | — | 已實作：014:29-31 |
| 稽核 `actor` | `ops`、`ai`、`system` | 維運、AI、系統 | 已實作：014:32 |
| 稽核 `outcome` | `success`、`blocked`、`rejected`、`rate_limited` 等 | — | 已實作（開放值）：014:27 |
| BESS 運轉模式 | `STANDBY`、`GRID_TIE`、`ISLAND`、`FAULT` | 待機、併網運轉、離網供電、故障保護 | 規劃中（Draft）：BESS:46-49 |
| 警報狀態 | `NORMAL`、`PENDING`、`ACTIVE`、`ACKED`、`SHELVED`、`CLEARED` | 正常、待確立、作用中、已確認（ACK）、已擱置、已清除（中文為 proposed） | 規劃中：ARCH:470-473 |
| 警報等級 | `P0`、`P1`、`P2`、`INFO` | 緊急、重要、一般、資訊 | proposed：ARCH 只列 P0、P1（ARCH:480）；建議對照 Grafana `critical`→`P1`、`warning`→`P2`，`P0` 保留給安全事件（BMS L4、消防） |
| Grafana 告警 severity | `warning`、`critical` | — | 已實作（僅 Grafana 內）：rules.yaml:74, 151, 216, 306, 379, 452, 542, 610, 681, 749 |
| Grafana 規則狀態、告警狀態 | `inactive`、`pending`、`firing`；`active`、`suppressed` | — | 已實作（僅 Grafana 內）：api/openapi.yml:1098-1103, 1134-1138 |
| 資料品質 | `GOOD`、`UNCERTAIN`、`BAD`、`STALE`、`SUBSTITUTED` | 中文待定（proposed） | 規劃中：ARCH:435-439 |
| 指令生命週期 | `CREATED`、`AUTHORIZED`、`VALIDATED`、`DISPATCHED`、`ACKED`、`CONFIRMED`、`REJECTED`、`EXPIRED`、`FAILED`、`UNKNOWN` | — | 規劃中：ARCH:485-488 |
| BMS 保護等級 | `L1`、`L2`、`L3`、`L4` | 警報、降載、禁止充放、緊急跳脫 | 領域定義（DOMAIN:58-59）；API 值為 proposed（G-09） |
| 需量風險 | `low`、`medium`、`high` | 低、中、高 | proposed（G-03） |
| 時間電價時段、日型 | `peak`、`mid_peak`、`off_peak`；`summer_weekday`、`summer_saturday`、`non_summer_weekday`、`sunday_offpeak_day` | 尖峰、半尖峰、離峰；夏月平日、夏月週六、非夏月平日、週日及離峰日 | proposed（G-04） |

**現行 Grafana 告警規則標題（逐字，infra/grafana/provisioning/alerting/rules.yaml）**

| uid | 標題 | severity | 群組 | 行 |
|---|---|---|---|---|
| `ems-power-kw-high` | 功率超限 (power_kw > 100 kW) | warning | EMS-功率告警 | 13-14 |
| `ems-pipeline-electricity-stale` | 電表資料寫入停滯 (>2 分鐘無新資料) | critical | EMS-管線健康 | 93-94 |
| `ems-pipeline-factory-stale` | 工廠資料寫入停滯 (>2 分鐘無新資料) | critical | EMS-管線健康 | 161-162 |
| `ems-guardrail-block-burst` | L2 guardrail BLOCK 爆量 (同 device 1h ≥ 5 次) | warning | EMS-設備分類安全 | 244-245 |
| `ems-mass-deactivate-1h` | 大量 deactivate (同 key 1h ≥ 5) | warning | EMS-設備分類安全 | 316-317 |
| `ems-mass-deactivate-24h` | 大量 deactivate (同 key 24h ≥ 20) | warning | EMS-設備分類安全 | 389-390 |
| `ems-l1-budget-warn` | L1 LLM 月預算達 80% (warn) | warning | EMS-預算告警 | 481-482 |
| `ems-l1-budget-exhausted` | L1 LLM 月預算 100% (exhausted, fail-closed) | critical | EMS-預算告警 | 551-552 |
| `ems-guardrail-budget-warn` | L2 guardrail 月預算達 80% (warn) | warning | EMS-預算告警 | 620-621 |
| `ems-guardrail-budget-exhausted` | L2 guardrail 月預算 100% (exhausted, 連 L1 全停) | critical | EMS-預算告警 | 690-691 |

通知聯絡點名稱 `Telegram`（uid `telegram-main`，contact-points.yaml:5-8）；依 `alertname` 分組、每 4 小時重送（notification-policies.yaml:6-9）。

### 4.2 單位

| 量 | API 欄位或 unit 字串 | 畫面顯示 | 出處 |
|---|---|---|---|
| 電壓 | `voltage`；unit `V` | V | init.sql:12；008:21 |
| 電流 | `current`；unit `A` | A | init.sql:13；008:22 |
| 有效功率 | `power_kw`；unit `kW` | kW | init.sql:14；008:23 |
| 累計電量 | `energy_kwh`；unit `kWh` | kWh | init.sql:15；008:24 |
| 溫度 | `temperature`；unit 字串 `degC` | °C | 008:26, 33 |
| 濕度 | `humidity`；unit `%RH` | %RH | 008:27 |
| 壓力 | `pressure`；unit `kPa` | kPa | 008:29 |
| 轉速 | `motor_speed`；unit `RPM` | rpm | 008:28 |
| 布林 | `pump_on`、`valve_open`；unit `boolean` | 開、關 | 008:30-31 |
| AI 信心 | `ai_confidence` 0–1 | 百分比或兩位小數；分帶 低 < 0.5 ≤ 中 < 0.8 ≤ 高 | 003:16；frontend/src/components/ems/ConfidenceMeter.tsx:3, 14-15 |
| 無效功率 | 規劃中 | kvar | ARCH:380-381 |
| 頻率 | 規劃中 | Hz | ARCH:380-381 |
| 功率因數 | 規劃中；無單位 0–1 | 0.92 | ARCH:381 |
| SOC、SOH | 規劃中；proposed 後綴 `_pct` | % | ARCH:379 |
| 絕緣阻抗 | 規劃中；proposed 單位 kΩ（後綴 `_kohm`） | kΩ 或 MΩ | DOMAIN:34 |
| 需量 | proposed `demand_kw`（15 分鐘平均） | kW | DOMAIN:32-33 |
| 金額 | proposed 後綴 `_twd`，`currency: "TWD"` | NT$，並標「估算」 | DOMAIN:75 |

### 4.3 規劃中訊號（名稱尚未定案）

ARCH 只給出訊號範例 `active_power`（ARCH:424），正式名稱由 device profile（PRD-0007，ARCH:745）與 `signal_definitions`（ARCH:606）決定。設計端不應寫死訊號名，應以 PL-14 回傳的名稱與 `unit` 顯示。既有電表訊號名 `voltage`、`current`、`power_kw`、`energy_kwh`（008:21-24）維持不變。

| 設備 | 設計需要的量 | 來源依據 |
|---|---|---|
| PCC 電表 | 有效功率、無效功率、電壓、電流、頻率、功率因數、電能、需量 | ARCH:381 |
| BMS | SOC、SOH、電芯電壓極值、電芯溫度極值、絕緣、允許充放電流、故障 | ARCH:379；BESS:142-143 |
| PCS | 模式、P、Q、交流電壓與頻率、直流電壓與電流、能力上限、故障 | ARCH:380；BESS:144 |

### 4.4 時間與時區

- API 時間一律 ISO 8601 date-time，UTC（api/openapi.yml:995, 1031）；DB 欄位型別 `TIMESTAMPTZ`；docker-compose 未設定 TZ，序列化為 UTC（可能是 `Z` 或 `+00:00`，前端一律以 Date 解析）。
- 顯示一律轉為 Asia/Taipei（ems-overview.json:23；ARCH:449；DOMAIN:91）。現行 `formatDateTime` 未指定 `timeZone`，會以瀏覽器時區顯示（frontend/src/lib/format.ts:19-26），需補 `timeZone: "Asia/Taipei"`（proposed）。
- 欄位命名：量測點時間 `time`；registry 時刻 `*_at`；稽核 `event_time`（014:19）；proposed 區間用 `start`、`end`，查詢用 `from`、`to`。
- E-18 的 `since` 請傳 UTC `Z` 格式；以 `URLSearchParams` 組裝即可正確編碼（frontend/src/api/client.ts:73-82）。若手組字串，`+08:00` 的 `+` 未編碼會被解讀為空白而回 422（device_measurements.py:46-57）。
- 15 分鐘需量區間、日界、月界依場域時區對齊（proposed；ARCH:601 sites.timezone）。

### 4.5 角色與權限

| 層級 | 逐字值 | 中文 | 出處 |
|---|---|---|---|
| 今日 session 角色 | `ops`、`ingest`、`readonly` | 維運、資料匯入、唯讀 | services/bff/bff/roles.py:15-18；zh-Hant.ts:39-41；frontend/src/auth/types.ts:9 |
| 規劃產品角色 | `platform_admin`、`organization_admin`、`site_admin`、`operator`、`dispatcher`、`maintainer`、`auditor`、`viewer` | 中文待定 | ARCH:626-633 |
| 規劃權限（ARCH 範例） | `command.pcs.setpoint`、`alarm.ack`、`config.deploy` | — | ARCH:635 |
| 本文件 proposed 權限 | `site.read`、`measurement.read`、`measurement.export`、`demand.read`、`tariff.read`、`billing.read`、`alarm.read`、`alarm.shelve`、`device.read`、`bess.settings.read`、`schedule.read`、`report.read`、`report.create`、`audit.read`、`command.read` | — | proposed |

Persona 對應（PRD5:79-84）：運維、資料治理確認人員 → `ops`；管理層、客戶 → `readonly`（今日七畫面經非 deprecated 路由無可讀資料，見 G-13）；採集端維運 → `ingest`（今日只能用 deprecated 的 E-19，也讀不到 `last_seen_at`）。

### 4.6 既有 i18n 鍵（frontend/src/i18n/zh-Hant.ts，逐字）

| 鍵 | 字串 | 行 |
|---|---|---|
| `common.appName`、`common.appTagline` | SynaIQ EMS、能源管理平台 | 7-8 |
| `common.loadMore`、`retry`、`noData`、`loading`、`back`、`error`、`cancel` | 載入更多、重試、無資料、載入中…、返回、載入失敗、取消 | 9-15 |
| `nav.devices`、`nav.queue`、`nav.gallery`、`nav.primary` | 設備清單、確認佇列、元件展示、主導覽 | 18-21 |
| `auth.session.roleLabel` | 角色 | 37 |
| `auth.session.role.ops`、`.ingest`、`.readonly` | 維運、資料匯入、唯讀 | 39-41 |
| `auth.session.logout` | 登出 | 43 |
| `device.status.candidate`、`.confirmed`、`.active`、`.retired`、`.unknown`、`.stale` | 候選、已確認、運轉中、已退役、未知狀態、過時 | 48-53 |
| `confidence.label`、`confidence.unclassified` | AI 分類信心、未分類 | 57-58 |
| `confidence.band.low`、`.medium`、`.high` | 低、中、高 | 59 |
| `measurement.updatedAt`、`measurement.noValue` | 更新於、— | 62-63 |
| `measurement.domain.electricity`、`.factory` | 電力、工廠 | 64 |
| `deviceTable.empty` | 目前沒有符合條件的設備 | 87 |
| `deviceTable.headers.deviceId`、`.deviceType`、`.status`、`.aiConfidence`、`.lastSeenAt` | 設備編號、類型、狀態、AI 信心、最後上線 | 90-94 |
| `deviceDetail.fields.deviceType`、`.protocol`、`.vendor`、`.model`、`.location`、`.gatewayId`、`.classifiedBy`、`.aiConfidence`、`.lastSeenAt`、`.createdAt`、`.confirmedAt` | 設備類型、通訊協定、廠牌、型號、位置、Gateway、分類來源、AI 信心、最後上線、建立時間、確認時間 | 112-122 |
| `deviceDetail.signalHeaders.name`、`.unit`、`.datatype`、`.direction`、`.status` | 名稱、單位、資料型別、方向、狀態 | 127-131 |
| `queue.title`、`queue.empty`、`queue.countLabel` | 確認佇列、目前沒有待確認的候選設備、待確認 {{count}} 台 | 136, 138, 139 |
| `review.source.llm`、`.system_fallback`、`.unknown` | AI 產生、系統備援、來源不明 | 145 |
| `review.actions.confirm`、`.override`、`.reject` | 確認分類、覆寫分類、拒絕（退役） | 154-156 |

需新增（proposed）：`nav.overview` 能源總覽、`nav.monitor` 即時監控、`nav.demand` 需量管理、`nav.storage` 儲能管理、`nav.alarms` 警報中心、`nav.analytics` 設備分析、`nav.reports` 報表中心；`device.status.maintenance` 維護中；`device.comm.good` 通訊正常、`device.comm.stale` 資料延遲；`alarm.state.*`、`alarm.severity.*`、`bess.mode.*`（字串見 4.1）。

### 4.7 設計字串須修正處

| # | 設計現況 | 實際情形 | 建議 |
|---|---|---|---|
| 1 | AI 佇列動作「退回」 | `reject` 會把裝置改為 `retired`（device-service routes/devices.py:248），不是退回佇列 | 改用既有 `review.actions.reject`「拒絕（退役）」（zh-Hant.ts:156） |
| 2 | 「修正類型」 | 對應 `override`，body 須含 `device_type` 與 `signals[]`（models.py:66-68） | 改用「覆寫分類」（zh-Hant.ts:155） |
| 3 | 設備「確認」與警報「確認」同字 | 設備為 confirm（確認分類）；警報為 ACK（ACK 不等於清除，ARCH:472） | 警報動作標為「確認（ACK）」（proposed） |
| 4 | 「通訊 GOOD／STALE」、KPI「資料延遲（STALE）」 | API 的 `stale` 是候選逾 30 天未審（ADR-010:31），i18n 為「過時」（zh-Hant.ts:53） | 以 `last_seen_at` 推導，使用 proposed `comm_state` 與新鍵 `device.comm.*` |
| 5 | 佇列來源「10.0.3.27:502」「MQTT sub-07」 | 位址（source_ref）刻意不對外（009:27；models.py:56-63）；自動發現以 MQTT topic 為準 | 改顯示 `digest.sample_digest.topic`（digest.py:28），例 `ems/devices/sim-001/measurements`（services/gateway/telegraf.conf:36） |
| 6 | 類型 `grid_meter`、`battery`、`solar_inverter`、消防盤 | 前三者為 proposed（ADR-021:22），現行 AI 閉集不含（prompt.py:9）；消防盤無對應型別 | 標示為規劃型別，或暫用 `electricity`、`unknown` |
| 7 | 裝置代號「M-01」「PCS-01」「INV-01」等 | 現有 device_id 為 `sim-001`、`plc-001`、`sensor-001`（008:11-13） | 示意資料可保留，但須維持「示意資料」標示 |
| 8 | 稽核事件「command.pcs.setpoint」「schedule run」 | 前者是權限名（ARCH:635），後者不存在；實際事件見 4.1（014:29-31） | 首發稽核表只列既有 7 種事件；指令紀錄另表（R10） |
| 9 | 「freeze_override（雙人覆核）」 | freeze_override 為單一 OPS 以 request_id token 覆寫凍結紀錄（device-service routes/devices.py:212-235；010:36-58）；雙人覆核是指令概念（ARCH:524, 642） | 移除「雙人覆核」 |
| 10 | 警報「HVAC-01 資料中斷超過 2 分鐘」 | 現行規則是整張量測表停滯（電表、工廠），不是逐裝置；告警標籤刻意不含 device_id（rules.yaml:93-223, 228-229） | 首發文案改為規則標題（4.1）；逐裝置停滯需新規則 |
| 11 | 警報等級 P0、P1、P2、資訊 | repo 只有 `warning`、`critical` | 採 4.1 proposed 對照，並於畫面註明 |
| 12 | 生命週期「維護中」 | 前端 `KNOWN_DEVICE_STATUSES` 未含 `maintenance`（types.ts:67-72），會顯示「未知狀態」；也沒有轉入 API | 新增 i18n 鍵與前端列舉；轉入 API 另案補（ADR-010:29-30 定義為 OPS 權限） |
| 13 | 品牌 tAIstro | 既有 `common.appName` 為「SynaIQ EMS」（zh-Hant.ts:7），PLAN:222 已決定不顯示 SynaIQ | 更新 i18n 字串（非 API 事項） |
| 14 | 導覽「設備分析」 | 既有 `nav.devices` 為「設備清單」（zh-Hant.ts:18），另六項導覽鍵不存在 | 依 4.6 新增鍵 |
| 15 | AI 審閱摘要鍵名 | 前端 mock 使用 `proposed_type`、`confidence`、`rationale`、`proposed_signals`、`warnings`（fixtures.ts:128-135），與實際 digest 不符 | 以 digest.py:39-56 的鍵為準（1.3） |

---

## 附錄 A 漂移與限制

1. **BFF 不在契約文件內**：BFF 關閉自身 OpenAPI（services/bff/bff/main.py:85-87），`api/openapi.yml` 不含任何 `/api/*` 路由；ARCH:575 要求 BFF 納入契約漂移檢查。
2. **openapi 與 DB 列舉不一致**：`DeviceOut.status` 說明只列三種狀態（api/openapi.yml:794），DB 允許五種（003:26-27）；`SignalCreate.datatype` 列出 `string`（api/openapi.yml:812），DB CHECK 不允許（004:21）。
3. **前端 client 與 BFF 不一致**：client 已有 `createDevice`、`updateDevice`（frontend/src/api/client.ts:126-133），BFF 尚無對應路由（ADR-026:20；ARCH:58）；`listDeviceMeasurements` 型別固定為 `Measurement[]`，工廠裝置實際回 `FactoryMeasurement[]`（client.ts:110-113）。
4. **`stale` 旗標沒有寫入者**：device-service 只在查詢時讀取 `stale_marked_at`（device_repo.py:55-58），`?stale=true` 目前恆為空。
5. **`maintenance` 無轉入路徑**：DB 允許，但 device-service 只有 confirm、override、reject、delete 會改狀態（device-service routes/devices.py:183-256）。
6. **量測 facade 的容量限制**：limit 上限 1000（config.py:122）、無 offset、無 until、無彙總；電表取樣 1 秒（services/gateway/telegraf.conf:6）→ 單次最多約 16.7 分鐘；工廠 PLC 取樣 2 秒（services/kc-gateway/telegraf.conf:4）→ 約 33 分鐘。
7. **輪詢成本**：`/api` 回應皆 `no-store`（security.py:96），E-18 每次呼叫 BFF 會再打兩個上游（ADR-025:46）；全點位表 N 點、每 5 秒輪詢時，每位使用者每分鐘約 N × 24 次上游呼叫。
8. **Session 上限**：輪詢會重置閒置計時，但 8 小時絕對上限仍會強制登出（config.py:110），畫面需有「登入逾時」狀態。
9. **Grafana 功率規則說明不一致**：查詢視窗為 5 分鐘平均（rules.yaml:19-21, 46），說明文字寫「過去 1 分鐘」（rules.yaml:77）。
10. **資料皆為模擬**：唯一電表 `sim-001` 的功率約 34–78 kW（DOMAIN:4），設計畫面的 186 kW、500 kW 契約等數值均為示意；無真實場域（DOMAIN:78）。
11. **文件狀態**：ARCH 為 Working Draft（ARCH:5）、BESS 為 Draft（BESS:4）、ADR-021 與 ADR-025 為 Proposed（ADR-025 已實作）、ADR-026 為 Accepted 但未實作（ARCH:67-69）。本文件引用的規劃中端點均無回應 schema，實作前需後端正式定義。
12. **PostgREST 有兩個未記載的 view**：`api.devices`、`api.device_signals`（009:8-43）可被未認證讀取，但未列於 openapi；依 PRD5:269-273 不得對瀏覽器開放。
