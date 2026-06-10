# PRD-0006：通用量測管線與動態可視化 — 窄表儲存、AI 識別升格、Registry 驅動儀表板

| 欄位 | 內容 |
|------|------|
| 狀態 | **Draft**（2026-06-10 起案）|
| 起案日期 | 2026-06-10 |
| 最後修訂 | 2026-06-10 |
| 對應決策紀錄 | 承接 PRD-0003「識別已 AUTO、儲存/可視化未通用化」之斷點分析（本檔 §1）|
| 取代 / 補充 | **補充** PRD-0001/0002/0003；不修改其主體。與 [PRD-0004](PRD-0004-device-service-observability-alerting.md)（ops 觀測）、[PRD-0005](PRD-0005-ems-frontend.md)（產品 UI）分工並存 |
| 相依 ADR | [ADR-020](../adr/ADR-020-db-migration-governance.md)（migration 治理）；**ADR-021**（device_type 閉集政策，本批新開）；**ADR-022**（窄表 `signal_measurements` 決策，本批新開）|

---

## 1. Overview & Context

### 業務背景（總體判斷）

EMS 的端到端鏈路 = **採集 → topic → ingest/儲存 → 識別 → 可視化**。盤點現況：

- **識別（PRD-0003）已 AUTO**：MQTT 自動發現 → AI 分類（雙層 guardrail + budget fail-closed）→ 信心門檻自動 confirm / 人工佇列，全鏈已 Implemented。
- **儲存是硬斷點**：量測只能落入 **2 張寫死寬表**（`electricity_measurements` / `factory_measurements`，PRD-0001/0002；migration 010 的 GRANT 即以此兩表為全集）。電池 SoC、逆變器 DC 側、EV charger 等新欄位**無處可落**——寬表 schema 寫死，新裝置型別的量測進不了庫。
- **可視化 100% 手寫 JSON**：每個 dashboard 都是手刻 provisioning 檔；新裝置/新訊號不會自動出現。

### 核心策略

**先打通儲存（窄表），再把 AI 識別輸出「升格」進 registry 驅動路由，最後可視化由 registry 決定性生成。**

AI **只在識別站介入**；其餘各站 **BY DESIGN 決定性**。PRD-0003 既有的安全骨架——Two-Layer guardrail、budget fail-closed、最小權限、freeze trigger、append-only audit——**全部不變**，本 PRD 不新增任何 LLM 呼叫（見 §9 / 附錄 AI 價值地圖）。

### 痛點

1. **儲存斷點**：`ems/storage/bat-01/measurements`（Parser Matrix 規則 #3 准入）能被發現、能被 AI 判型，但 SoC/SoH/dc_power **落不了庫**——telegraf 寬表沒有這些欄位。
2. **識別成果閒置**：AI 產出的 `SignalSuggestion`（signal_name/unit/datatype/direction）目前**僅存於 `device_review_digests.digest` JSONB**，confirm 後不會進 `device_signals` registry，下游無從引用。
3. **路由寫死**：`discovery.py` 的 gateway 對映與 `measurements_repo.table_for_gateway`（ems→electricity / kc→factory 兩路寫死）使新領域一律落空。
4. **可視化手工**：新 signal = 手寫 panel JSON，與「自動發現」的設計初衷矛盾。

### 上下游

- 上游：mosquitto（既有 topic 契約 `ems/+/+/measurements`、`factory/sensor/+`，ADR-007/PRD-0003 §8.5，不新增 topic 格式）；device-service 識別輸出（digest）。
- 下游：Grafana（registry 驅動 Device Explorer）；PostgREST（`api.signal_measurements` 唯讀面）；PRD-0005 前端（P2 量測路由決策時消費）。

---

## 2. Goals / Non-Goals

### Goals

- **G1 通用儲存（P1）**：任意 `(device_id, signal_name, value)` 可落庫——窄表 `signal_measurements` hypertable + day-one columnstore 壓縮（ADR-022）。
- **G2 通用 ingest（P1）**：新服務 `ingest-generic` 以 deny-by-default parser parity 訂閱既有 topic，型別決定性路由批次寫入；專屬 `ems_ingest` role 僅 INSERT。
- **G3 識別升格（P2）**：confirm（自動/人工）時把 digest 內的 `SignalSuggestion` **決定性**升格進 `device_signals`（`confirmed_by_ai=true`）+ audit，registry 成為下游單一真相。
- **G4 路由 config 化（P2）**：gateway/表名對映自寫死改為 config 對照表（tunable-parameters 治理）；領域擴充 battery/solar_inverter/ev_charger/grid_meter（ADR-021）。
- **G5 決定性可視化（P3）**：Device Explorer dashboard 以變數鏈 `$device_type→$device→$signal` 直查 registry + 窄表，**新裝置/新 signal 自動出現、零 codegen**。

### Non-Goals（明確排除）

- ❌ **採集端 codegen / Modbus register map 自動化** → 另立 **PRD-0007**（vendor 模板庫 + AI 匹配建議，人工核准）。
- ❌ **舊寬表遷移 / 回填 / dual-write**：`electricity_measurements` / `factory_measurements` 與其 telegraf 寫入路徑**原封不動**；歷史資料不搬。
- ❌ AI 排版 / AI 生成 dashboard（可視化一律決定性，AI 僅經已審計之 registry 升格**間接**影響）。
- ❌ 產品級 UI（→ PRD-0005）。
- ❌ 控制下發（→ 待 control-service PRD）。
- ❌ retention 具體數值（→ §14 Open Questions，先量測再定）。

---

## 3. User Stories & Personas

| Persona | 場景 | 需求 |
|---------|------|------|
| **維運工程師** | 接上電池櫃（`ems/storage/bat-01/measurements`）| 不改任何 schema/conf：自動發現 → AI 判 battery → confirm 後 SoC/SoH/dc_power 落庫、儀表板自動出面板 |
| **EMS 開發者** | 新增裝置型別 | 不再為每型別開寬表欄位 / 手寫 telegraf.conf / 手刻 panel JSON |
| **資料治理 / 確認人員** | confirm 候選裝置 | confirm 的同時，AI 建議的 signals 自動進 registry（可審計、可事後 CRUD 修正）|
| **運維值班（Ops on-call）** | 看新裝置健康 | Device Explorer 選 `$device_type=battery` → `$device=bat-01` → 全部 signals 面板即現 |
| **安全負責人** | 審查新攻擊面 | ingest-generic 僅 INSERT 單表、deny-by-default 准入、AI 永不碰量測寫入路徑 |

---

## 4. Functional Requirements

> 編號採 **FR-6xx**（PRD-0006 命名空間）。〔P1/P2/P3〕為 §12 階段歸屬；〔M/S〕為工作量級。

### 儲存（P1）

- **FR-601 窄表 `signal_measurements`**〔P1,M〕：`public.signal_measurements(time TIMESTAMPTZ, device_id TEXT, signal_name TEXT, value_num DOUBLE PRECISION, value_bool BOOLEAN, value_text TEXT)`，CHECK「三個 value 欄**恰一非 NULL**」；hypertable（chunk interval 可調，入 tunable-parameters）；索引 `(device_id, signal_name, time DESC)`。**驗收**：任意合法 (device, signal, num/bool/text) INSERT 成功；違反恰一非 NULL → 23514。
- **FR-602 day-one columnstore 壓縮**〔P1,M〕：`segmentby = (device_id, signal_name)`、`orderby = time DESC`；壓縮 policy 預設 7 天（可調）。**驗收**：`timescaledb_information.jobs` 存在該 policy；壓縮後 chunk 可查。

### Ingest（P1）

- **FR-603 `services/ingest-generic/`**〔P1〕：aiomqtt 訂閱 `ems/+/+/measurements` + `factory/sensor/+`（**client_id 與 device-service 區隔**，雙消費者並存）；**複製 `topic_parser` 的 deny-by-default 准入 + `parse_fields`（ILP/JSON）並建立 parity 測試**鎖定兩處實作不漂移；型別**決定性**路由（numeric→value_num、bool→value_bool、其餘→value_text）；批次 INSERT。**accept-all 哲學**：通過 topic 准入 + `MAX_PAYLOAD`/`MAX_FIELDS` 界定的訊息照單全收，**未註冊 signal 照收**（registry 升格與否不影響落庫；攻擊面由准入規則界定，見 §9）。**驗收**：pub 規則 #1–#4 訊息→窄表落列；違規 topic/oversize→丟棄+metric。
- **FR-604 `ems_ingest` role 最小權限**〔P1〕：新 DB role **僅** `INSERT ON public.signal_measurements`（+ schema USAGE）；無 SELECT/UPDATE/DELETE、無其他表權限。ingest-generic 用此 role 連線。**驗收**：以該 role SELECT 任表 / INSERT 他表 → permission denied。

### 對外唯讀面（P1）

- **FR-605 `api.signal_measurements` + `measurements_unified`**〔P1〕：(a) `api.signal_measurements` view（白名單欄位，照 **migration 009 模式** + `NOTIFY pgrst, 'reload schema'`；GRANT `web_anon`）——PostgREST 量測 view **先例已存在**（migrations 000/001 的 `api.electricity_measurements` / `api.factory_measurements`），本 FR 為窄表補上同型對外面；(b) `public.measurements_unified` **UNION ALL view**：兩張寬表 **unpivot** 與窄表合併為統一 (time, device_id, signal_name, value…) 形狀，供跨新舊查詢（是否進 PostgREST → §14 Q3）。**注意**：前端 BFF vs 直連 PostgREST + CORS 的**路由策略屬 PRD-0005 P2**，本 PRD 僅交叉引用、不決策。

### AI 識別升格（P2）

- **FR-606 自動 confirm 升格**〔P2,M〕：`discovery_pipeline.persist_outcome` 於**同一交易**內（該路徑已持 §8.6.8 per-device advisory lock），在 status 推進 confirmed 時將 outcome 之 `SignalSuggestion` 升格 INSERT 進 `device_signals`（`confirmed_by_ai=true`、`status='active'`，遵 partial unique index，重複 signal 冪等跳過）。**零新 LLM 呼叫、零預算影響**（純資料搬運自既有 digest）；AI role 對 `device_signals` 之 INSERT/UPDATE 權限 **migration 010 已授**，無須擴權。
- **FR-607 人工 confirm 升格**〔P2,M〕：`routes/devices.py` 之 confirm 路徑改為「**先升格、後 set_lifecycle**」——**順序關鍵**：若先寫 lifecycle（`classified_by` 落入凍結集合），migration 010 的 `device_signals` freeze trigger 會擋下隨後的 signals 寫入；故同一交易內先 INSERT signals、再轉狀態。**驗收**：人工 confirm 後 `device_signals` 有該裝置 suggestion 列、且 freeze 對後續 AI 寫入照常生效。
- **FR-608 升格前夾箝（決定性 clamp）**〔P2〕：`datatype` 夾箝至 `('float','int','bool','enum')`、`direction` 夾箝至 `('read','write','read_write')`——不合法值 → 寫 NULL + `metadata` 註記原值（migration 004 對欄位值域有 CHECK，未夾箝將使整筆升格交易 abort）；`device_type` 不合法 → `'unknown'`（應用層閉集政策，**ADR-021**；DB 維持自由 TEXT）。
- **FR-614 升格 audit**〔P2〕：每次升格寫 `device_audit_log` 事件 `signal_promotion`（append-only，actor=ai/ops、device_id、升格筆數、來源 digest 指紋）。

### 領域擴充與路由（P2）

- **FR-609 領域擴充**〔P2〕：`prompt.py` `DEVICE_TYPES` 閉集 **+= battery / solar_inverter / ev_charger / grid_meter**（ADR-021）；Parser Matrix 規則 #3 的 domain→type 預設由一律 `unknown` 改為**資料驅動對照**（`solar→solar_inverter`、`storage→battery`，未列 domain 仍 `unknown`）。
- **FR-610 路由 config 化**〔P2〕：`discovery.py` 之 gateway 對映（現為 3 路寫死）與 `measurements_repo.table_for_gateway`（現為 2 路寫死：ems→electricity / kc→factory）改為 **config 對照表**（device-service TOML + tunable-parameters 註冊表，env 可覆寫）；`recent_samples` 加**窄表優先**路徑（取 ≤20 個 timestamp、聚合 signal→value dict 還原與寬表同形樣本），查無資料 fallback 寬表。

### 可視化（P3）

- **FR-611 Device Explorer — 變數鏈與 timeseries**〔P3.1,S〕：手寫**一次** `infra/grafana/provisioning/dashboards/device-explorer.json`：變數鏈 `$device_type`（查 `devices`）→ `$device`（查 `devices` filtered）→ `$signal`（查 `device_signals`）；timeseries panel **repeat by `$signal`** 直查窄表。
- **FR-612 Device Explorer — bool/明細**〔P3.1,S〕：bool 訊號 state-timeline panel + 該裝置 `device_signals` 明細 table panel。**零 codegen**：新裝置/新 signal 經升格進 registry 後自動出現於變數鏈，無需改 JSON。
- **FR-613（選配）per-type dashboard codegen**〔P3.2〕：`infra/grafana/build_devicetype_dashboards.py` 沿 `infra/grafana/_build_device_health.py` **既有前例**（build script 產 JSON、provisioning 載入 + reload）為各 device_type 生成固定版面 dashboard。**否決** Grafana HTTP API 即時建板（runtime 寫入不可重建、違反 provisioned & idempotent 原則，PRD-0004 G4）。

### 端到端驗收（P2/P3）

- **FR-615 e2e 驗收劇本**：模擬器新增 battery profile 發布 `ems/storage/bat-01/measurements`（SoC/SoH/dc_power）→ 自動發現（規則 #3）→ AI 判 `battery`（FR-609 閉集）→ 信心 >0.9 自動 confirm → 升格 `device_signals`（FR-606）→ 窄表落資料（FR-603）→ Device Explorer 選 battery/bat-01 **自動**出 SoC/SoH/dc_power 面板（FR-611）。全程**無任何手動 schema/conf/JSON 變更**。

---

## 5. Non-Functional Requirements（量化）

| NFR | 指標 | 目標 |
|-----|------|------|
| 寫入吞吐 | 窄表 INSERT | ≥ 2,000 rows/s（設計量級：200 裝置 × 10 signals × 1s ≈ 2,000 rows/s；批次寫入）|
| 查詢延遲 | 單 (device, signal) 時間範圍查詢 | < 500 ms（dev DB，命中 (device_id, signal_name, time DESC) 索引）|
| 壓縮率 | columnstore 壓縮後 | ≥ 5x（segmentby 同質序列；實測回填 §14 Q1 retention 決策）|
| 可視化時效 | confirm → Device Explorer 可見 | ≤ 1 個 dashboard refresh 週期（變數查 registry，無 codegen 延遲）|
| 決定性 | ingest / 升格 / 可視化路徑 LLM 呼叫數 | **0**（AI 僅存在於既有識別站）|
| 隔離性 | 既有寬表路徑 | 零變更、零停機（telegraf/kc-ingest 原封不動）|

---

## 6. System Architecture

### 6.1 Current（斷點所在）

```
simulator ── ems/devices/{id}/measurements ─▶ mosquitto ─▶ telegraf(ingest)    ─▶ electricity_measurements（寬表）
kc-gateway ─ ems/factory/{id}/measurements ─▶ mosquitto ─▶ telegraf(kc-ingest) ─▶ factory_measurements（寬表）
第三方 ───── factory/sensor/{id} ───────────▶ mosquitto ─▶（無通用落庫路徑）
                                                 │
                                                 └─▶ device-service（自動發現＋AI 分類；寫 registry/digest，不寫量測）
Grafana ◀── 手寫 JSON dashboards ◀── 寬表
✗ ems/storage/bat-01 的 SoC/dc_power：可被發現、可被分類，但無欄位可落 → 量測黑洞
✗ SignalSuggestion 只進 digest JSONB，confirm 後不進 device_signals → registry 空轉
```

### 6.2 Target

```
任何裝置 ── ems/+/+/measurements、factory/sensor/+ ─▶ mosquitto
   ├─▶ telegraf 寬表路徑（原封不動）──────────────▶ electricity/factory_measurements（寬表）
   ├─▶ ingest-generic（新；parser parity；ems_ingest role INSERT-only）─▶ signal_measurements（窄表 hypertable + columnstore）
   └─▶ device-service：發現 → AI 分類（guardrail/budget 不變）→ confirm → 升格 device_signals（FR-606/607 + audit）
                                                                          │
        registry（devices + device_signals）◀─────────────────────────────┘
              │ 決定性驅動
              ├─▶ Grafana Device Explorer（$device_type → $device → $signal repeat；直查窄表）
              └─▶ 路由 config（FR-610）/ recent_samples 窄表優先
寬表 unpivot ＋ 窄表 ──▶ measurements_unified（UNION ALL view）
窄表 ──▶ api.signal_measurements（PostgREST，web_anon 唯讀；照 009 模式）
```

### 6.3 Container

- **新增** `ingest-generic` container（compose；連 mosquitto + timescaledb `ems_ingest` DSN）。
- **不改** device-service container 拓撲（Phase 2 僅程式內升格/路由邏輯）；**不改** telegraf/kc-ingest；Grafana 僅加 provisioning 檔。

### 6.4 Data Flow（新流程）

1. 裝置發布 → mosquitto → ingest-generic 准入（deny-by-default）→ 型別路由 → 批次 INSERT 窄表。
2. device-service 照 PRD-0003 流程發現/分類；confirm 時同交易升格 signals 進 registry + audit。
3. Grafana 變數鏈查 registry → repeat panels 查窄表 → 新裝置自動可見。

---

## 7. Data Model

### 7.1 `public.signal_measurements`（窄表 hypertable，ADR-022）

| 欄位 | 型別 | 說明 |
|------|------|------|
| `time` | TIMESTAMPTZ NOT NULL | 量測時間 |
| `device_id` | TEXT NOT NULL | 對應 `devices.device_id`（**不加 FK**，沿 PRD-0003 G7 原則）|
| `signal_name` | TEXT NOT NULL | 任意 signal（accept-all；未註冊照收）|
| `value_num` | DOUBLE PRECISION | 數值型 |
| `value_bool` | BOOLEAN | 布林型 |
| `value_text` | TEXT | 其餘（enum/string）|

- **CHECK**：`value_num` / `value_bool` / `value_text` **恰一非 NULL**。
- **索引**：`(device_id, signal_name, time DESC)`。
- **columnstore**：day-one `compress_segmentby=(device_id, signal_name)`、`compress_orderby=time DESC`、policy 7 天（可調）；chunk interval 可調（tunable-parameters）。
- **否決替代**（詳 ADR-022）：JSONB payload 欄（壓縮差、無 per-signal 索引）；per-type 動態建表（DDL 自動化違反最小權限 + freeze 哲學）。
- **量級**：200 裝置 × 10 signals × 1s ≈ 2,000 rows/s 單機可承受；1 分鐘 continuous aggregate 留作後備（§14 Q2）。

### 7.2 `public.measurements_unified`（UNION ALL view）

寬表 unpivot（每個寫死欄位 → 一列 (time, device_id, signal_name, value_num)）`UNION ALL` 窄表。**舊寬表原封不動**——無 dual-write、無回填；本 view 只做讀側合併。

### 7.3 `api.signal_measurements`（PostgREST 白名單 view）

照 migration 009 模式：明列欄位、`GRANT SELECT TO web_anon`、`NOTIFY pgrst, 'reload schema'`。先例：migrations 000/001 已建 `api.electricity_measurements` / `api.factory_measurements`。

### 7.4 Roles

| Role | 權限增量 |
|------|---------|
| `ems_ingest`（**新**）| 僅 `INSERT ON public.signal_measurements`；無任何 SELECT |
| `device_service_ai` | **無變更**（migration 010 已有 `device_signals` INSERT/UPDATE，升格夠用；**不**授窄表任何權限）|
| `device_service_ops` | 視需要授 `SELECT ON signal_measurements`（FR-610 recent_samples 窄表優先路徑用）|
| `web_anon` | 僅 `api.signal_measurements` SELECT |

### 7.5 Migration

新 migration 採**下一個流水號 019**（修正：原規劃文件誤植 016——README 載明 PRD-0003 已用至 **migrations 003–018**；實作時以 `infra/timescaledb/migrations/` 目錄最大號 +1 為準，治理依 **ADR-020**）：窄表 + hypertable + 索引 + columnstore + policy + `ems_ingest` role + `measurements_unified` + `api.signal_measurements`（可依 ADR-020 拆檔）。冪等 + `tests/integration/test_migrations.py` 對應 class（既有義務）。

---

## 8. API Contract

- **Phase 1–3 無新 device-service REST endpoint**（依 [`doc/governance/api-contract-governance.md`](../governance/api-contract-governance.md)：`api/openapi.yml` 無 MAJOR/MINOR bump 需求；升格為 confirm 既有端點之**內部行為增量**，回應 schema 不變）。
- **MQTT**：沿用既有 topic 契約（ADR-007 / PRD-0003 §8.5），不新增格式；ingest-generic 為**新訂閱者**（client_id 區隔），非新發布者。
- **PostgREST**：新增 `/signal_measurements` 唯讀端點（FR-605）；openapi.yml 比照 `/electricity_measurements` 記載方式於實作批次同步（§12 同步義務）。
- **Grafana**：provisioning 檔案契約（dashboard JSON + 可選 builder script），無 runtime API 寫入。

---

## 9. Security & Privacy

- **`ems_ingest` 最小權限**：單表 INSERT-only；ingest-generic 被攻破最壞情況 = 灌垃圾量測列（可由 rate/size 准入 + 壓縮 + retention 治理），**讀不到任何資料、改不了 registry**。
- **AI 不碰量測寫入**：AI role 對 `signal_measurements` **零權限**；AI 對下游的影響**只能**經「已審計的 registry 升格」間接發生（升格本身決定性、零 LLM）。`ems_ingest` 不對 AI 開放。
- **升格走 audit**：每次 `signal_promotion` 寫 append-only `device_audit_log`（FR-614），事後可追溯、可由 OPS signal CRUD 修正。
- **freeze 不變**：凍結紀錄（`classified_by IN ('human','manual_override','migration_backfill')`）的 signals 寫入照常被 migration 010 trigger 擋下；FR-607 的「先升格後 set_lifecycle」正是**在進入凍結前完成合法寫入**，不開任何 override 後門。
- **accept-all 論證**：未註冊 signal 照收**不是**放寬攻擊面——攻擊面由既有 deny-by-default 准入（topic shape / id regex / `MAX_PAYLOAD` 16KB / `MAX_FIELDS` 64）界定，與 device-service 同一套 parser（parity 測試鎖定）；registry 註冊與否只影響「可視化是否自動出現」，不影響「能否寫入」。拒收未註冊 signal 反而會把 registry 變成寫入路徑的 runtime 依賴（耦合 + 失效模式更差）。
- **guardrail / budget / 兩層 AI 防護**：原樣保留，本 PRD 路徑零 LLM 呼叫、零預算影響。

---

## 10. Observability

- ingest-generic：沿 device-service metric 樣式輸出准入丟棄計數（invalid_topic/oversized/…）、批次寫入延遲、INSERT 失敗計數；接入既有 Grafana（PRD-0004 樣式，低基數）。
- 升格：audit row（FR-614）即事件源；Grafana 可對 `signal_promotion` 做 window COUNT（低基數 event_type 維度，沿 FR-339/344 樣式）。
- 壓縮：policy job 狀態由 `timescaledb_information.jobs` 監看（§13 存在性測試 + 操作手冊 SOP）。

---

## 11. Risks & Mitigations

| # | 風險 | 等級 | 對策 |
|---|------|------|------|
| R1 | **量級超出**（裝置/頻率成長 > 2,000 rows/s 設計值）| 中 | day-one columnstore 壓縮 + 批次寫入；1 分鐘 cagg 後備（§14 Q2）；chunk interval 可調 |
| R2 | **升格錯誤**（AI suggestion 品質差污染 registry）| 中 | `confirmed_by_ai=true` 標記可篩；OPS signal CRUD 可改/可 soft-delete；FR-614 audit 可追溯；凍結紀錄照擋（人工介入後 AI 不可再寫）|
| R3 | **雙消費者干擾**（ingest-generic 與 device-service 同訂 topic）| 低 | MQTT client_id 區隔（各自獨立 session/queue）；兩者皆冪等消費 |
| R4 | **parser 漂移**（兩處准入實作分叉）| 中 | FR-603 parity 測試鎖定（同一組 fixture 對打兩實作）；長期可抽共用套件（工程 backlog）|
| R5 | **migration 編號衝突**（多 PRD 並行）| 低 | 依 ADR-020：實作當下取目錄最大號 +1（本檔以 019 起算）|
| R6 | **unified view 查詢慢**（寬表 unpivot 無索引優勢）| 低 | unified 僅供跨新舊兼容查詢；熱路徑（Explorer/recent_samples）直查窄表 |

---

## 12. Rollout & Migration Plan

### 階段對照（FR → Phase）

| Phase | FR | 內容 | 觸及 |
|-------|----|------|------|
| **P1 儲存打通** | FR-601~602〔M〕、FR-603~604、FR-605 | 窄表+壓縮、ingest-generic+`ems_ingest`、api view+unified | `infra/timescaledb`（migration **019**，依 ADR-020）+ `services/ingest-generic/` + compose |
| **P2 識別升格** | FR-606~607〔M〕、FR-608、FR-609、FR-610、FR-614、FR-615（e2e 起跑）| 升格雙路徑、夾箝、領域擴充、路由 config 化、audit | `services/device-service`（**GATE-2 批已合入 dev，無衝突**）|
| **P3.1 可視化** | FR-611~612〔S〕、FR-615（驗收完成）| Device Explorer 手寫一次 | `infra/grafana/provisioning/dashboards/` |
| **P3.2 選配** | FR-613 | per-type dashboard codegen | `infra/grafana/`（沿 `_build_device_health.py` 前例）|
| **Phase 4** | — | 採集端 vendor 模板庫 + AI 匹配建議 | → **PRD-0007**（另立）|

### 部署 / 回滾

- P1：套 migration → 起 ingest-generic → 驗窄表落列。回滾 = 停容器（窄表保留，不影響既有路徑；schema 回滾依 ADR-020）。
- P2：device-service 滾更。回滾 = 退版（升格為 confirm 行為增量，舊版行為 = 不升格，無資料風險）。
- P3：provisioning 檔 + `docker compose restart ems-grafana`。回滾 = 移除 JSON。

### EMS 同步義務（Guideline §11.2，實作完成後）

- `api/openapi.yml`：補 PostgREST `/signal_measurements`（比照 `/electricity_measurements`）。
- 容器速查表：新增 ingest-generic 容器 + Device Explorer dashboard。
- 操作手冊：壓縮 policy 監看 SOP、ems_ingest 金鑰管理、Explorer 使用節。
- tunable-parameters 註冊表：chunk interval、壓縮 policy 天數、批次大小、路由對照表。

---

## 13. Test Strategy

| 層級 | 內容 |
|------|------|
| 單元 | ingest-generic parser **parity 測試**（與 device-service `topic_parser` 同 fixture 對打）；型別決定性路由（num/bool/text 三分支 + 邊界）；FR-608 夾箝（合法/不合法/NULL 註記）|
| 整合 | migration 019 冪等（`test_migrations.py` class）；`ems_ingest` 權限矩陣（INSERT 通過、SELECT/他表拒絕）；壓縮 policy **存在性**；升格雙路徑（自動/人工，含 freeze 順序、audit row、冪等重入）；`measurements_unified` 形狀 |
| E2E | **FR-615 劇本**全鏈（throwaway 容器，battery profile → 發現 → 分類 → confirm → 升格 → 落庫 → Explorer 變數可見）|
| 覆蓋率 | 新 Python 模組沿用 **80%** 門檻；測試於 throwaway 容器執行（既有 runtime 慣例）|
| 回歸 | 既有寬表寫入（FR-313 樣式：sim-001/plc-001/sensor-001 持續落庫）與 device-service 全測試不破 |

---

## 14. Open Questions

1. **retention 數值**：窄表 raw 資料保留多久？（Non-Goal 先不定；待壓縮率/容量實測後定，走 tunable-parameters + 操作手冊）
2. **是否需 1 分鐘 cagg**：先量測查詢延遲，超標再建 continuous aggregate（後備已留）。
3. **`measurements_unified` 是否進 PostgREST**：或僅供 Grafana/內部查詢？（涉 web_anon 面擴張，傾向先僅內部）
4. **ingest-generic 日後是否取代 telegraf 寬表路徑**：本 PRD 明確不動寬表；長期單軌化另議（需獨立遷移計畫 + ADR）。

---

## 15. Appendix

### A. AI 價值地圖（各站 AI 介入原則）

| 鏈路站點 | AI 介入 | 說明 |
|---------|--------|------|
| 採集（register map / 模板）| **後期**：vendor 模板庫 + AI 匹配**建議**（人工核准；AI **永不**發明 register map）| → PRD-0007 |
| topic / payload 契約 | ❌ BY DESIGN 決定性 | ADR-007 命名 + deny-by-default parser |
| 識別 | ✅ **唯一 AI 站**（PRD-0003 既有；guardrail/budget 不變）| 本 PRD 零新 LLM 呼叫 |
| 儲存路由 | ❌ 決定性 | AI 僅經已審計 registry 升格**間接**影響；`ems_ingest` 不對 AI 開放 |
| 可視化 | ❌ 決定性（registry 驅動變數鏈 / 選配 codegen）| 否決 AI 排版 |

### B. 引用

- [PRD-0003](PRD-0003-Device-Registry-Auto-Discovery.md)：§8.5 Parser Matrix v3（5 規則 + 7 deny）、§8.6.8 advisory lock、§7.5 migration 010（roles/freeze trigger/AI grants）、§8.3 `SignalSuggestion`、§7.3 digest。
- [PRD-0004](PRD-0004-device-service-observability-alerting.md)：Grafana provisioning 樣式、`_build_device_health.py` builder 前例、低基數告警樣式。
- [PRD-0005](PRD-0005-ems-frontend.md)：§1.5 D2（migrations 000/001 量測 view 已存在）、量測**路由策略**（BFF vs 直連 + CORS）屬其 P2。
- [ADR-020](../adr/ADR-020-db-migration-governance.md)：migration 編號/治理；**ADR-021**（device_type 閉集）、**ADR-022**（窄表決策）本批新開。
- [`doc/governance/api-contract-governance.md`](../governance/api-contract-governance.md)：Phase 1–3 無新 device-service REST 之依據。

### C. 既有事實核對（撰寫時點，2026-06-10）

- 寬表僅 2 張：`electricity_measurements` / `factory_measurements`（migration 010 GRANT 全集）✅
- PostgREST 量測 view 先例：migrations 000/001 ✅（PRD-0005 D2 已於 2026-06-10 更正確認）
- `table_for_gateway` 2 路寫死（ems→electricity / kc→factory）、`recent_samples` ≤20 筆 ✅（Phase 1.4 Slice 1a）
- `SignalSuggestion` 現僅存 digest JSONB、confirm 不寫 `device_signals` ✅（§7.3/§8.4；分類管線僅 persist digest + devices ai_*）
- AI role 對 `device_signals` INSERT/UPDATE：migration 010 已授 ✅
- migration 流水號：PRD-0003 已用至 018 → 本 PRD 自 **019** 起（原規劃草案誤植 016，已更正）✅

---

> 本文件為 Draft。依專案流程，Approved 前需經 architect + security 審視；實作各 Phase 依 §12 順序，每批 TDD + 合併前 code review。
