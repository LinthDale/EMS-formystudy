# PRD-0002：KC Factory 工廠 PLC 整合

| 欄位 | 內容 |
|------|------|
| 狀態 | **Implemented (Phase 1-6)**（追溯式 PRD） |
| 起案日期 | 2026-04-24 |
| PRD 化日期 | 2026-04-29 |
| 原始規劃文件 | `doc/plan/kc_integration_plan.md`（v5，2026-04-27） |
| 取代 / 補充 | 與 PRD-0001 並行；新增 factory 域，不影響 ems 域 |

---

## 1. Overview & Context

### 業務背景
PRD-0001 完成電表（ems 域）端到端管線後，需驗證系統對「異質設備 / 異質協定」的擴展能力。KC（KerberosClaw）團隊提供兩個外部開源 repo（`kc_iot_gateway`、`kc_modbus_mcp`），含工廠 PLC 模擬器、MQTT JSON 感測器模擬器、與 MCP Server。

### 目標重點
1. **驗證可擴展性**：相同管線模式接入完全不同類型的設備
2. **保留電表鏈路**：sim-001 流程不中斷
3. **預留 AI 控制能力**：MCP Server 讓 Claude 用自然語言操作設備
4. **submodule 管理**：上游可獨立更新，本地 build image

---

## 2. Goals / Non-Goals

### Goals

1. **新增 factory 域管線**：kc-modbus-sim → kc-gateway → MQTT → kc-ingest → DB
2. **新增 MQTT JSON 來源**：kc-mqtt-sim 直發 JSON 給 mosquitto，由 kc-ingest parse
3. **新增資料表**：`factory_measurements`（與 `electricity_measurements` 對稱）
4. **新增 MCP Server 容器**：對外 :8765 提供 AI tool calls
5. **Grafana 工廠 panels**：在既有 dashboard 補上 factory 資料視覺化
6. **既有資料表更名**：`measurements` → `electricity_measurements`（命名對稱）

### Non-Goals

- ❌ 接入 KC repo 的 Gateway 主體（與既有 Telegraf gateway 重疊）
- ❌ 接入 KC repo 的 Rules engine（與 Grafana Alerting 重疊）
- ❌ 接入 KC repo 的 Dashboard（與 Grafana 重疊）
- ❌ 採用 kc_iot_gateway 的 Modbus simulator（pressure 不動態，見 plan §2.1）
- ❌ MCP 對外公開（內網限定，待 R-009 處理）

### Constraints

- 不可破壞 ems 域既有資料流
- submodule 需 commit pin（避免上游改動破壞 build）
- Telegraf 兩種輸入格式（ILP from KC modbus、JSON from KC mqtt）需在同一個 ingest 處理

---

## 3. User Stories & Personas

| Persona | Story |
|---------|-------|
| **EMS 開發者** | 我想驗證新場域只需「複製 gateway/ingest pattern」，不需重寫管線 |
| **AI 工程師** | 我想透過 MCP 用自然語言讓 Claude 讀寫設備暫存器 |
| **運維工程師** | 我想在同一個 Grafana dashboard 同時看電表與工廠資料 |
| **整合方（KC）** | 我想保留我的上游 repo，被整合方以 submodule 引用 |

---

## 4. Functional Requirements

| 編號 | 需求 | 驗收 |
|------|------|------|
| FR-101 | 引入 `external/kc_iot_gateway`、`external/kc_modbus_mcp`（一般 clone；submodule 化待 EMS 目錄 git init）| `external/` 下兩 repo 完整、Dockerfile 可 build |
| FR-102 | docker-compose 本地 build kc-modbus-sim、kc-mqtt-sim、kc-mcp-server image | `docker compose build` 全部成功 |
| FR-103 | kc-gateway 讀 kc-modbus-sim Modbus，發 `factory/devices/plc-001/measurements` ILP | `mosquitto_sub -t 'factory/#'` 看到 holding/input/coil 全欄位 |
| FR-104 | kc-mqtt-sim 直發 `factory/devices/sensor-001/measurements` JSON | 同上，看到 JSON payload |
| FR-105 | kc-ingest 同時 parse ILP + JSON，寫入 `factory_measurements` | `SELECT FROM factory_measurements` 同時有 plc-001 與 sensor-001 |
| FR-106 | 既有 `measurements` 表更名為 `electricity_measurements` | `\dt public.*` 看到新名；舊資料保留遷移 |
| FR-107 | `api.electricity_measurements` 與 `api.factory_measurements` 兩個 view 對外曝露 | OpenAPI `/electricity_measurements`、`/factory_measurements` 皆可查 |
| FR-108 | MCP Server 提供 read_register / write_register tool | Claude 透過 MCP client 可呼叫 |
| FR-109 | Grafana dashboard 補上 factory panels：temperature / humidity / motor_speed / pressure / pump_on / valve_open | dashboard 顯示 6 個 panel |
| FR-110 | ems 域既有資料流不中斷 | sim-001 持續寫入 electricity_measurements |

---

## 5. Non-Functional Requirements

繼承 PRD-0001 的 NFR 表（[`doc/nfr.md`](../nfr.md)），補充：

| 維度 | 目標 |
|------|------|
| factory 域寫入吞吐 | ≥ 10 rows/sec（單 PLC 多欄位）|
| MCP tool call 延遲 (p50) | < 500ms |
| MCP tool call 延遲 (p99) | < 2s |
| factory_measurements 保留期 | 同 electricity_measurements |
| submodule commit 鎖定 | 100%，禁止 floating reference |

---

## 6. System Architecture

### 6.1 Context Diagram
無變動，[`doc/architecture/c4-context.md`](../architecture/c4-context.md) 已含 PLC、Sensors、AI Agent。

### 6.2 Container Diagram
新增 5 個容器（[`doc/architecture/c4-container.md`](../architecture/c4-container.md)）：
- ems-kc-modbus-sim（dev only）
- ems-kc-mqtt-sim（dev only）
- ems-kc-gateway
- ems-kc-ingest
- ems-kc-mcp-server

### 6.3 Data Flow
- 工廠資料上行：[`data-flow.md`](../architecture/data-flow.md) 流程二
- AI 控制：[`data-flow.md`](../architecture/data-flow.md) 流程五

### 6.4 關鍵決策
- ADR-006 KC 鏈路獨立為 kc-gateway / kc-ingest
- ADR-007 MQTT topic v2 引入 `factory/` domain prefix

---

## 7. Data Model

### 新增表：`public.factory_measurements`（hypertable）

| 欄位 | 型別 | 說明 | 設備類型 | PII |
|------|------|------|---------|-----|
| `time` | TIMESTAMPTZ NOT NULL | 量測時間（UTC）；分區鍵 | 全 | 否 |
| `device_id` | TEXT NOT NULL | 設備 ID | 全 | 否 |
| `device_type` | TEXT NOT NULL | `plc` / `sensor` | 全 | 否 |
| `temperature` | DOUBLE PRECISION | 溫度 °C | plc, sensor | 否 |
| `humidity` | DOUBLE PRECISION | 濕度 %RH | plc, sensor | 否 |
| `motor_speed` | DOUBLE PRECISION | 馬達轉速 RPM | plc | 否 |
| `pump_on` | BOOLEAN | 幫浦狀態 | plc | 否 |
| `valve_open` | BOOLEAN | 閥門狀態 | plc | 否 |
| `pressure` | DOUBLE PRECISION | 壓力 kPa | plc | 否 |

- PRIMARY KEY: `(time, device_id)`
- 寫入：append-only
- 對外 view：`api.factory_measurements`

### 既有表更名
- `public.measurements` → `public.electricity_measurements`
- migration：保留歷史資料、view、index、role 權限

---

## 8. API Contract

權威規格：[`api/openapi.yml`](../../api/openapi.yml) v1.1.0

### 新增 / 變更
- 新增 `GET /factory_measurements`（PostgREST 通用語法）
- 既有 `GET /measurements` 改為 `GET /electricity_measurements`
- 新增 MCP Server tools（規格隨 KC 上游）

### 新 MQTT Topic（實際實作，校正於 2026-04-29）
- `ems/factory/plc-001/measurements`（ILP from kc-gateway）— 遵循主規範
- `factory/sensor/temp_01`（JSON from kc-mqtt-sim）— 例外，第三方來源沿用上游格式

詳見 ADR-007 v3。

---

## 9. Security & Privacy

### 資料分級
- 工廠量測資料：**非 PII**
- MCP Server 為控制入口，視為**敏感**

### 認證
- kc-gateway / kc-ingest：與 ems-gateway 同層信任
- MCP Server：當前無 token；風險登記 R-009
- 內網限定 :8765，不對外曝露

### 供應鏈
- submodule commit 鎖定（FR-101）
- KC repo 上游若停更，fork 到自己 org（R-010 緩解）

---

## 10. Observability

無變動，繼承 PRD-0001 §10。新增工廠 panels 後，Grafana dashboard 已涵蓋 factory 主要指標。

---

## 11. Risks & Mitigations

| ID | 風險 | 等級 | 緩解 |
|----|------|------|------|
| R-009 | MCP server 對 AI Agent 無強身份驗證 | P2 | :8765 內網限定；長期 mTLS / OAuth |
| R-010 | KC submodule 上游變更失控 | P2 | commit pin（已執行）；必要時 fork |

---

## 12. Rollout & Migration Plan

### 6 階段（已全部完成）
1. **Phase 1**：external clone 引入 + Dockerfile 建立（submodule 化為後續任務，見 R-010）
2. **Phase 2**：kc-modbus-sim + kc-gateway 上線
3. **Phase 3**：kc-mqtt-sim 上線（驗證 JSON 路徑）
4. **Phase 4**：`factory_measurements` 表 + kc-ingest 上線
5. **Phase 5**：`measurements` → `electricity_measurements` 更名 migration
6. **Phase 6**：Grafana 工廠 panels 補齊

### Migration 步驟（Phase 5 重要）
```sql
ALTER TABLE measurements RENAME TO electricity_measurements;
ALTER VIEW api.measurements RENAME TO electricity_measurements;
-- 確認 PostgREST schema cache 已 reload
```
- 採滾動方式：先建新名 view 兼容，再切換，再刪舊
- 回滾：`ALTER ... RENAME` 反向

### 回滾條件
- factory 寫入錯誤率 > 5% 持續 5 分鐘
- ems 域受到任何影響（PRD-0001 鏈路斷）

---

## 13. Test Strategy

### 新增測試
- **Integration**：
  - `tests/integration/test_pipeline_factory.py`：kc-modbus-sim + kc-mqtt-sim → DB 端到端
  - `tests/integration/test_db_schema.py`：`factory_measurements` schema 與 view
  - `tests/integration/test_migrations.py`：`measurements` → `electricity_measurements` 冪等性

### 觸發規則
依 `project_rules.md` §8 對照表：
- `services/kc-gateway/telegraf.conf` 變更 → 必跑 `test_pipeline_factory.py`
- `services/kc-ingest/telegraf.conf` 變更 → 同上
- `infra/timescaledb/migrations/*.sql` → 必跑 `test_migrations.py`

---

## 14. Open Questions

- [ ] MCP Server 認證強化時程（R-009）？是否新開 PRD？
- [ ] KC 上游若大改，是否切換為 fork？決策標準為何？
- [ ] 未來新場域（solar、storage）是否複用同模式（domain-pipeline）？預期寫成 ADR-XXX？

---

## 15. Appendix

### A. 採用 / 不採用元件對照

| Repo | 元件 | 採用 | 不採用理由 |
|------|------|------|----------|
| kc_iot_gateway | mqtt_simulator.py | ✅ | 唯一 JSON MQTT 來源 |
| kc_iot_gateway | modbus_simulator.py | ❌ | pressure 不動態 |
| kc_iot_gateway | Gateway 主體 | ❌ | 與 Telegraf 重疊 |
| kc_iot_gateway | Rules engine | ❌ | 與 Grafana Alerting 重疊 |
| kc_iot_gateway | Dashboard | ❌ | 與 Grafana 重疊 |
| kc_modbus_mcp | simulator.py | ✅ | 完整動態（含 pressure 隨機） |
| kc_modbus_mcp | server.py (MCP) | ✅ | AI 控制入口 |

### B. 變更紀錄
- 2026-04-24 v1：起草、Phase 1 開始
- 2026-04-25 v2-v3：Phase 2-3 完成
- 2026-04-26 v4：Phase 4-5 完成
- 2026-04-27 v5：表更名、Phase 6 完成、Grafana panels 上線
- 2026-04-29 PRD-0002 補建（追溯式）

### C. 相關文件
- `doc/plan/kc_integration_plan.md`（原始規劃 v5）
- `doc/容器速查表.md`（含 KC 容器）
- `doc/操作手冊.md`

### D. 對應 ADR
ADR-006、ADR-007（v2 修訂）
