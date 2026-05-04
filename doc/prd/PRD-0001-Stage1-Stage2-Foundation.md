# PRD-0001：EMS Stage 1 / Stage 2 基礎管線與儀表板

| 欄位 | 內容 |
|------|------|
| 狀態 | **Implemented**（追溯式 PRD） |
| 起案日期 | 2026-04-22 |
| PRD 化日期 | 2026-04-29 |
| 原始規劃文件 | `doc/archive/plan/EMS實作計畫.md` |
| 主要實作 commit 區間 | Stage 1 完成於 2026-04-22；Stage 2 進行中 |

---

## 1. Overview & Context

### 業務背景
台灣商用 EMS（Energy Management System）市場由 Schneider PME、研華 WebAccess/EMS 等成熟產品占據。本系統目標為自建可擴充、可在地化的 EMS，先以「資料管線通路 + 視覺化 + 告警」三件式 MVP 驗證可行性，再逐步往設備管理、業務計算、AI 控制擴展。

### 上下游
- **上游**：Modbus 電表（POC 階段以 simulator 替代）
- **下游**：值班工程師（Telegram 告警）、運維（Grafana 儀表板）、未來業務系統（PostgREST 查詢）

### 現況與動機
- 競品成熟但封閉、難客製
- 開源工具鏈（Telegraf / Mosquitto / TimescaleDB / PostgREST / Grafana）已可組成 90% MVP
- 自建可保留台灣在地化（台電費率、15 分鐘需量）的可插拔空間

---

## 2. Goals / Non-Goals

### Goals

1. **6 個容器一條龍啟動**：`docker compose up -d` 後 30 秒內全部 healthy
2. **資料端到端流通**：模擬電表 → MQTT → TimescaleDB → REST API & Grafana
3. **驗收 4 步全通**：simulator health / MQTT 有訊息 / DB 有資料 / REST 回查（已通過 2026-04-22）
4. **Stage 2：可視化 + 告警**：Grafana 儀表板 + Telegram 告警鏈路
5. **「能用開源就不手搓」原則驗證成功**：自寫程式碼 < 300 行

### Non-Goals

- ❌ 真實電表接入（Stage 3 之後）
- ❌ 多租戶 / 多場域隔離（Stage 5 之後）
- ❌ 前端 SPA（Stage 2 用 Grafana 取代）
- ❌ 寫入 API（query 為 read-only）
- ❌ 高可用 / 災難復原（DR 機制留待 POC 階段）

### Constraints

- 開發者 1 人；時程 ~6 週（Stage 1 + Stage 2）
- 部署環境：WSL Ubuntu + Docker
- 預算：零授權費（純開源）

---

## 3. User Stories & Personas

| Persona | Story |
|---------|-------|
| **維運工程師** | 我想在 Grafana 看即時功率與電壓曲線，異常時能立刻知道 |
| **值班工程師** | 我想接到 Telegram 告警，包含發生時間、設備、超限值 |
| **資料分析師** | 我想用 REST API 拉歷史資料做 Excel / Notebook 分析 |
| **EMS 開發者** | 我想容器化部署、debug 時能看到每層原始資料 |
| **EMS 管理者** | 我想隨時砍掉重練不影響資料、或備份還原 DB |

---

## 4. Functional Requirements

| 編號 | 需求 | 驗收 |
|------|------|------|
| FR-001 | simulator 提供 Modbus TCP slave（4 register）| `pymodbus` client 可讀到 voltage/current/power_kw/energy_kwh |
| FR-002 | simulator 提供 FastAPI（health / config / inject-fault）| `curl localhost:8001/health` 回 `{"status":"ok"}` |
| FR-003 | gateway 每秒輪詢 simulator，發 MQTT | `mosquitto_sub -t 'ems/#'` 每秒看到一筆 |
| FR-004 | ingest 訂閱 MQTT 寫入 TimescaleDB | `SELECT FROM electricity_measurements` 持續成長 |
| FR-005 | PostgREST 對外曝 `api.electricity_measurements` view | `curl :3001/electricity_measurements?limit=1` 回 JSON |
| FR-006 | Grafana 顯示電壓 / 電流 / 功率即時與歷史曲線 | dashboard 有 4 個 panel 正常顯示 |
| FR-007 | Grafana 告警：`power_kw > 100` 持續 30 秒 → Telegram | inject-fault 觸發後 60 秒內收到訊息 |
| FR-008 | 故障注入測試（none / zero / freeze）| POST `/inject-fault?mode=zero` 後 DB 寫入值歸零 |
| FR-009 | 一鍵備份還原 | `pg_dump` / `psql` 還原後資料完整 |
| FR-010 | `docker compose down -v` 後重建可重現 | 相同 commit + .env 重建後驗收全通 |

---

## 5. Non-Functional Requirements

> 全量化指標見 [`doc/governance/nfr.md`](../governance/nfr.md)。本節摘錄 Stage 1 / Stage 2（Dev / Demo）範圍：

| 維度 | 目標 |
|------|------|
| MQTT publish → DB 寫入 (p99) | < 15s（Demo） |
| PostgREST 查詢 (p99) | < 1s（Demo） |
| 告警觸發 → Telegram 送達 | < 30s |
| 月度可用性（Demo） | 99.0% |
| RPO / RTO（Dev / Demo） | RPO < 24h、RTO < 24h（手動 pg_dump） |
| Modbus 輪詢週期 | 1s |

---

## 6. System Architecture

### 6.1 Context Diagram
見 [`doc/architecture/c4-context.md`](../architecture/c4-context.md)。

### 6.2 Container Diagram
見 [`doc/architecture/c4-container.md`](../architecture/c4-container.md)（Stage 1 / 2 範圍：simulator / gateway / mosquitto / ingest / timescaledb / query / grafana）。

### 6.3 Data Flow
見 [`doc/architecture/data-flow.md`](../architecture/data-flow.md) 流程一（量測上行）與流程三（告警觸發）。

### 6.4 關鍵決策
- ADR-001 開源優先
- ADR-002 pymodbus 鎖 3.6.9
- ADR-003 Telegraf request 新語法
- ADR-004 PostgREST 連線格式
- ADR-005 DB schema 雙層隔離
- ADR-007 MQTT topic 命名

---

## 7. Data Model

### 主表：`public.electricity_measurements`（hypertable）

| 欄位 | 型別 | 說明 | PII |
|------|------|------|-----|
| `time` | TIMESTAMPTZ NOT NULL | 量測時間（UTC，broker 端產生）；hypertable 分區鍵 | 否 |
| `device_id` | TEXT NOT NULL | 設備 ID（如 sim-001）| 否 |
| `voltage` | DOUBLE PRECISION | 電壓 V | 否 |
| `current` | DOUBLE PRECISION | 電流 A | 否 |
| `power_kw` | DOUBLE PRECISION | 功率 kW | 否 |
| `energy_kwh` | DOUBLE PRECISION | 累計電量 kWh | 否 |

- PRIMARY KEY: `(time, device_id)`
- 寫入模式：append-only（不 UPDATE / DELETE 單筆）
- 保留期：Demo 階段 30 天（POC 階段 90 天，Prod 階段 13 個月）— 見 NFR §5

### 對外 view：`api.electricity_measurements`
- 由 `web_anon` role SELECT，與 `public` 表隔離（ADR-005）

---

## 8. API Contract

權威規格：[`api/openapi.yml`](../../api/openapi.yml) v1.1.0

### 範圍（Stage 1 / 2）
- **Simulator API** (`:8001`)：`GET /health`、`GET /config`、`POST /config`、`POST /inject-fault`
- **Query API** (`:3001`)：`GET /electricity_measurements`（PostgREST 通用語法）
- **Grafana API** (`:3000`)：provisioning reload、alert rules、active alerts、receiver test

### MQTT Topic
- `ems/devices/{device_id}/measurements`（ADR-007）
- Payload：Influx Line Protocol
- QoS：1（at-least-once）

---

## 9. Security & Privacy

### 資料分級
- 量測資料：**非 PII**，無個人可識別性
- Grafana / Telegram bot token：**機密**，走 `.env` + `.gitignore`

### 認證
- Mosquitto：anonymous（Dev / Demo 內網）— 風險登記 R-003
- PostgREST：read-only via `web_anon`
- Grafana：admin 帳密；對外時強制改強密碼 + viewer-only role
- Cloudflare Access：One-time PIN（ADR-008）

### Threat Model
**待補**（待辦項目 D，由 R-001 追蹤）

---

## 10. Observability

### 現況
- docker compose logs（純文字）
- Grafana dashboard（指標視覺化）
- Telegram 告警

### 缺口（待 POC 階段補強）
- 結構化 JSON log + trace_id
- Prometheus + Loki
- 黃金訊號 4 指標 dashboard

---

## 11. Risks & Mitigations

主要風險（完整見 [`doc/governance/risk-register.md`](../governance/risk-register.md)）：

| ID | 風險 | 等級 | 緩解 |
|----|------|------|------|
| R-001 | Cloudflare demo 期間 Grafana 內網橫向 | P0 | 改強密碼 + viewer-only |
| R-002 | TimescaleDB 單點 | P0 | cron pg_dump + 異地備份 |
| R-003 | Mosquitto anonymous | P1 | 啟密碼 + TLS |
| R-005 | pymodbus 鎖死 CVE | P1 | 訂閱 advisory |
| R-006 | Telegram 告警靜默丟失 | P1 | heartbeat + 副通道 |

---

## 12. Rollout & Migration Plan

### Stage 1 上線（已完成 2026-04-22）
- 部署：`docker compose up -d`（單機）
- 驗收：4 步驗收全通（README §驗收）
- 回滾：`docker compose down`（保留 volume）／ `docker compose down -v`（清空重來）

### Stage 2 上線（進行中）
- Grafana provisioning：dashboard + alert rule + Telegram contact point
- Cloudflare Tunnel demo（ADR-008）
- 回滾：關 tunnel + 移除 DNS record + Access policy

### 回滾條件
- 資料寫入錯誤率 > 5% 持續 5 分鐘 → 人工評估
- DB 容器無法 healthy 超過 10 分鐘 → 立即回滾上一版

---

## 13. Test Strategy

完整規範見 `project_rules.md` §7-13。

### 涵蓋範圍
- **Unit**：`tests/unit/test_float_registers.py`、`test_simulation_math.py`、`test_simulator_api.py`
- **Integration**：`test_db_schema.py`、`test_migrations.py`、`test_pipeline_electricity.py`、`test_postgrest.py`、`test_simulator_rest.py`
- **E2E**：`test_pipeline_electricity.py`（Modbus → DB 端到端）

### 覆蓋率下限
- simulator 純函數：90%
- FastAPI endpoint：80%

### 執行
```bash
make -C tests unit          # 不需 docker
make -C tests integration   # 需 docker compose up -d
make -C tests coverage      # 含覆蓋率報告
```

---

## 14. Open Questions

- [ ] Grafana 對外 demo 的 viewer-only role 是否已 provisioning？（連動 R-001）
- [ ] cron pg_dump 排程是否落地？（連動 R-002）
- [ ] Mosquitto 持久化（`persistence true` + volume）何時啟用？（連動 R-004）
- [ ] PostgREST 寫入 endpoint 啟用時程？是否需要新 PRD？

---

## 15. Appendix

### A. 變更紀錄
- 2026-04-22 Stage 1 完成（資料管線通了）
- 2026-04-23 容器速查表上線
- 2026-04-24 KC factory 整合啟動 → 衍生 PRD-0002
- 2026-04-27 `measurements` 改名 `electricity_measurements`（v5）
- 2026-04-28 Cloudflare Tunnel demo 上線（ADR-008）
- 2026-04-29 PRD-0001 補建（追溯式）

### B. 相關文件
- `doc/archive/plan/EMS實作計畫.md`（原始規劃）
- `doc/archive/stage_1/README.md`（進度紀錄）
- `doc/operations/容器速查表.md`
- `doc/operations/操作手冊.md`
- `自學架構.md`（位於 `Documents/EMS/`）

### C. 對應 ADR
ADR-001、ADR-002、ADR-003、ADR-004、ADR-005、ADR-007、ADR-008
