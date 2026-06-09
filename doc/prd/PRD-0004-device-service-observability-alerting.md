# PRD-0004：Device-Service 營運可觀測性 — 預算告警與分類健康度 Dashboards

| 欄位 | 內容 |
|------|------|
| 狀態 | **Draft**（2026-06-09 起案） |
| 起案日期 | 2026-06-09 |
| 最後修訂 | 2026-06-09（v1 初稿） |
| 對應決策紀錄 | 承接 PRD-0003 Phase 1.4 carried follow-ups（budget alert / Grafana panels） |
| 取代 / 補充 | **補充** PRD-0003；不修改其主體（已 Implemented，依 Guideline §9 變更走新 PRD/ADR） |
| 相依 ADR | ADR-019（跨-provider L2 guardrail；本 PRD 之 Non-Goal，另案處理） |

---

## 1. Overview & Context

### 業務背景

PRD-0003 已把 device-service 的核心做完：可切換 LLM 分類、MQTT 自動發現、雙層 AI 守衛、L1/L2 各自的**預算硬上限**（FR-329 / FR-340，皆 fail-closed）、append-only 稽核、AI 通道 MCP。功能面「設限」已齊備。

但目前是**「設了限、卻看不到也收不到通知」**的狀態：

- `evaluate_budget`（`budget_ledger.py`，`WARN_RATIO=0.8`）只是一個 **read-only 決策 helper**，沒有任何 alert 真的會發出。預算到 80% 沒人知道；到 100% 系統 fail-closed 降級到 `system_fallback`（分類全停、改用預設值）時，**運維是瞎的**。
- guardrail 獨立預算（`provider='guardrail'` ledger row，FR-340）同樣沒有告警。
- 沒有 dashboard 看「待人工確認佇列有多少」「裝置分類狀態分布」「分類錯誤率 / 延遲」「本月花費 vs 預算」。

### 痛點

1. **告警盲區**：budget 觸頂 → fail-closed 降級是「安全」的，但**沒有通知**＝運維只能事後從資料異常反推，無法即時加額度或切 mock。
2. **佇列盲區**：低信心候選累積在人工確認佇列，沒有可視化 → 可能堆積無人處理。
3. **成本盲區**：L1 + guardrail 兩條預算的耗用速率無圖可看，無法預測何時觸頂。

### 上下游

- 上游資料源：`llm_budget_ledger`（FR-329/340 寫入）、`device_review_digests`（FR-336 digest）、`devices`（分類狀態）、`device_audit_log`（FR-339/344 事件，既有告警已接）。
- 下游：Grafana（既有 `EMS` folder + `timescaledb-ems` datasource）+ Telegram contact point（`telegram-main`，FR-339/344 已在用）。
- **不新增任何服務、不改分類熱路徑**：本 PRD 全部是 Grafana 之上的 read-only 查詢與 provisioning。

---

## 2. Goals / Non-Goals

### Goals（first-principles 拆解）

從「device-service 要能被人營運上線」反推，缺的恰好是 closed-loop 的「看得到 + 收得到」：

- **G1 預算告警閉環**：L1 與 guardrail 兩條預算，於 80%（warn）與 100%（fail-closed 降級）各發 Telegram 告警。讓 FR-329/340 的「設限 + 計量」延伸成「設限 + 計量 + **告警**」。
- **G2 分類健康度 Dashboard**：四個 panel —— 待人工佇列、裝置狀態分布、分類 error/latency、成本 vs 預算。
- **G3 低基數**：沿用既有 FR-339/344 告警樣式（SQL `GROUP BY … HAVING` 取跨閾值 scalar，維度不進 label），避免 Grafana 高基數爆量。
- **G4 provisioned & idempotent**：告警與 dashboard 全走 provisioning 檔，重啟可重建，與既有 `rules.yaml` 一致。

### Non-Goals（明確排除）

- **跨-provider L2 guardrail**（L1 OpenAI + L2 Anthropic 的 defense-in-depth）—— 屬安全決策且卡 Anthropic key，**另開 ADR-019** 處理，不在本 PRD。
- 不改 budget 演算法 / reservation 機制（FR-329/340 已定）。
- 不做全鏈路 APM / distributed tracing。
- 不新增分類功能或 REST endpoint。
- 不改 PRD-0003 已 Implemented 的任何契約。

---

## 3. User Stories & Personas

| Persona | 場景 | 需求 |
|---------|------|------|
| **運維值班（Ops on-call）** | 半夜 LLM 月預算逼近上限 | 80% 時收 Telegram 提早加額度 / 評估切 mock；100% 降級時**立刻**收到通知，知道分類已停用回退值 |
| **成本負責人（Cost owner）** | 月中檢視花費 | 看 dashboard 一眼掌握 L1 + guardrail 兩條花費占比與耗用斜率 |
| **資料治理 / 確認人員** | 處理低信心候選 | dashboard 看待確認佇列長度，避免堆積 |

---

## 4. Functional Requirements

> 編號採 FR-4xx（PRD-0004 命名空間，與 PRD-0003 的 FR-3xx 區隔）。

### 告警（Alerting）

- **FR-400 L1 預算 80% warn**：對 `llm_budget_ledger` 當期 `provider != 'guardrail'` 的 `cost_usd` 加總，相對 `LLM_MONTHLY_BUDGET_USD` ≥ `BUDGET_WARN_RATIO`(0.8) 且 < 1.0 時，發 Telegram warn。
- **FR-401 L1 預算 100% exhausted**：同上比例 ≥ 1.0 時，發**高優先**告警，訊息標明「分類已 fail-closed 降級為 system_fallback」。
- **FR-402 guardrail 預算告警**：對 `provider='guardrail'` row 比例 `GUARDRAIL_MONTHLY_BUDGET_USD`(10.0)，同樣 80% warn / 100% exhausted（100% 時連 L1 一起停，訊息載明）。
- **FR-403 低基數聚合**：告警 SQL 以 `GROUP BY period_start, provider … HAVING` 取得「跨閾值之 provider 數」單一 scalar；`provider` / 金額**不進 Grafana label**（沿用 FR-339 樣式）。
- **FR-404 noData/execErr 韌性**：`noDataState=OK`、`execErrState=Error`、`for=0s`（達門檻即報）；ledger 無當期 row（月初）視為 0% 不誤觸。
- **FR-405 provisioned**：新增 alert group `EMS-預算告警` 於 `infra/grafana/provisioning/alerting/rules.yaml`，contact point 沿用 `telegram-main`，可重啟重建、無 provisioning error。

### Dashboards（Panels）

- **FR-406 待人工佇列 panel**：`devices` 中 `status='candidate'`（或 `ai_confidence < LLM_CONFIDENCE_THRESHOLD`）之計數時序，含當前值 stat。
- **FR-407 裝置狀態分布 panel**：`devices` 依 `status`（candidate/confirmed/retired）分組計數（pie / bar）。
- **FR-408 分類 error & latency panel**：以 `device_audit_log`（分類事件）/ `device_review_digests.generated_at` 推導近窗 error rate 與處理延遲。
- **FR-409 成本 vs 預算 panel**：`llm_budget_ledger` 當期 L1 與 guardrail 兩條 `cost_usd` vs 各自上限的 % gauge + 月內累積斜率時序。
- **FR-410 provisioned dashboard**：以 JSON 置於 `infra/grafana/provisioning/dashboards/`，與既有 dashboard 一致載入；datasource 用 `timescaledb-ems`。

---

## 5. Non-Functional Requirements（量化）

| NFR | 指標 | 目標 |
|-----|------|------|
| 告警延遲 | 觸發到 Telegram | ≤ 1 個 eval interval（1 min）|
| 熱路徑零影響 | 對分類 p99 latency 影響 | 0（純 read-only over ledger/views，不經 device-service）|
| 低基數 | Grafana active series 增量 | 維度不進 label，alert series 數 = O(1) per rule |
| 可重建性 | 重啟 grafana 後 | 告警 + dashboard 100% 由 provisioning 重建，無手動步驟 |
| 查詢成本 | 單次 alert SQL | 走當期 `(period_start, provider)` 索引；< 50 ms on dev DB |
| 安全 | 告警內容 | 不外洩 device_id / key 內容（僅聚合數量與比例）|

---

## 6. System Architecture

### 6.1 Context

```
                        ┌────────────────────────────┐
   device-service ──寫──▶│  TimescaleDB (ems)          │
   (FR-329/340 ledger)  │  • llm_budget_ledger        │
                        │  • device_review_digests    │
                        │  • devices                  │
                        │  • device_audit_log         │
                        └──────────────┬──────────────┘
                                       │ read-only (timescaledb-ems datasource)
                                       ▼
                        ┌────────────────────────────┐
                        │  Grafana (EMS folder)       │
                        │  • alert group EMS-預算告警 │──▶ Telegram (telegram-main)
                        │  • dashboard 4 panels       │
                        └────────────────────────────┘
```

### 6.2 Container

無新增 container。沿用既有 `ems-grafana` + `timescaledb`。Provisioning 檔新增：`rules.yaml` 一個 group、`dashboards/` 一個 JSON。

### 6.3 Data Flow

1. device-service 分類時 reserve/settle 寫 `llm_budget_ledger`（既有）。
2. Grafana alert rule 每分鐘查當期 ledger 比例 → 跨門檻 → Telegram。
3. Dashboard panel 直查 ledger / devices / digests view 呈現。

---

## 7. Data Model

**無新表、無 migration。** 全部 read-only 既有結構：

| 來源 | 關鍵欄位 | 用途 |
|------|---------|------|
| `llm_budget_ledger` | `period_start, provider, cost_usd`（UNIQUE period_start+provider）| FR-400~402、409 |
| `devices` | `status, ai_confidence` | FR-406、407 |
| `device_review_digests` | `device_id, generated_at` | FR-408 |
| `device_audit_log` | `event_type, event_time` | FR-408 |

> Dashboard 若需，可加唯讀 `api.*` view（白名單欄位），但優先直查；如新增 view 走 idempotent `CREATE OR REPLACE`，不破壞 PRD-0003 §7.4 白名單原則。

---

## 8. API Contract

- **無新 REST / MQTT 契約**。Grafana 直查 DB。
- **Telegram 訊息格式**（contact point template）：
  - warn：`⚠️ [EMS] {provider} 月預算達 {pct}%（{spent}/{cap} USD）`
  - exhausted：`🛑 [EMS] {provider} 月預算 100% — 分類已 fail-closed 降級 system_fallback，請加額度或切 mock`
- 不含 device_id / 個別裝置資料（低基數 + 隱私）。

---

## 9. Security & Privacy

- 告警與 panel 僅輸出**聚合數量與比例**，不外洩 `device_id`、`key_id`、correction 內容。
- Telegram bot token 為機密，置於 provisioning secret / `.env`，**不進 git**（沿用 FR-339/344 既有 contact point）。
- Grafana datasource 為唯讀帳號；本 PRD 不擴張任何 DB 權限。
- Threat：告警 SQL 注入面 = 0（rawSql 為固定 provisioned 字串，無使用者輸入）。

---

## 10. Observability

本 PRD 即是 device-service 的 observability 補完。Meta 層面：

- **Alert 自我監控**：`execErrState=Error` 使 alert SQL 失敗本身可見（Grafana alert state）。
- **noData=OK**：月初 ledger 空不誤觸。
- 既有 FR-339（guardrail BLOCK 爆量）/ FR-344（mass-deactivate）告警不受影響，本 PRD 與其並列於同一 alerting provisioning。

---

## 11. Risks & Mitigations

| # | 風險 | 等級 | 對策 |
|---|------|------|------|
| R1 | **告警抖動**（比例在門檻附近震盪重複發）| 中 | warn 用 `for=` 視窗或 ledger 月聚合單調遞增特性（cost 只增不減於當期）降低抖動 |
| R2 | **Telegram 投遞失敗**（網路 / token 失效）| 中 | contact point 重試；後續可加備援 channel（Open Question）|
| R3 | （承接 tech-debt）**MQTT subscriber 連續重連失敗後僅 log、不重啟** | 中 | 本 PRD 不解，登錄於此；建議後續以 supervisor / healthcheck 重啟（工程 backlog）|
| R4 | （承接 tech-debt）**`resolve_pricing` 每訊息呼叫**（應移 lifespan）| 低 | 效能清理，非告警範圍；登錄為 backlog |
| R5 | （承接 tech-debt）**`MQTT_SUBSCRIPTIONS` 可設過寬 wildcard 灌爆 handler** | 低 | parser deny-by-default 仍擋；登錄為 backlog |
| R6 | dashboard 查詢拖慢 DB | 低 | 走 `(period_start, provider)` 索引 + 限定當期；panel refresh ≥ 30s |

> R3~R5 為 PRD-0003 carried caveats，**非本 PRD 交付項**，僅在此集中登錄避免遺失（符合「計畫需有紀錄文件」原則）。

---

## 12. Rollout & Migration Plan

### 部署策略

1. 新增 `rules.yaml` 的 `EMS-預算告警` group + `dashboards/device-service-health.json`。
2. `docker compose restart ems-grafana`。
3. 驗證 `/api/v1/provisioning/alert-rules` 出現新 rule、無 provisioning error；dashboard 載入。
4. **手動觸發驗收**：在 dev DB seed 一筆當期 ledger 至 80% / 100%，確認 Telegram 收到對應訊息，事後還原（snapshot/restore，比照 FR-340 整合測試）。

### 回滾條件 / 計畫

- 觸發：告警誤報風暴、Grafana provisioning error、dashboard 拖慢 DB。
- 回滾：移除新 alert group + dashboard JSON，restart grafana（無 schema 變更，零資料風險）。

### EMS 同步義務（Guideline §11.2，實作完成後）

- `doc/API.yaml`：本 PRD 無新 REST，註明告警/儀表板為 Grafana provisioning（非 REST）。
- Container Cheat Sheet：無新容器，補 Grafana 告警/儀表板說明。
- Operations Manual：新增「預算告警與健康度儀表板」操作節（門檻意義、收到 100% 告警的處置 SOP：加額度 / 切 mock）。

---

## 13. Test Strategy

| 層級 | 內容 |
|------|------|
| 覆蓋率 | 本 PRD 主體為 provisioning（SQL/JSON），無新 Python 邏輯；既有 80% 門檻不適用 |
| SQL 驗證 | 每條 alert SQL 對 dev DB 實跑可執行、回傳預期 scalar |
| Provisioning 驗證 | restart 後 `/api/v1/provisioning/alert-rules` 確認 rule live、dashboard 載入無 error |
| E2E 驗收 | seed ledger → 80%/100% → Telegram 實收（手動，opt-in，保留證據；比照 FR-340 ledger snapshot/restore）|
| 回歸 | 確認 FR-339/344 既有告警不受影響 |

---

## 14. Open Questions

1. 80% warn 是否需 **per-provider 不同門檻**（L1 vs guardrail），或統一 `BUDGET_WARN_RATIO`？（暫採統一）
2. cost panel 取樣 / refresh 頻率？（暫 30s；月聚合資料不需更密）
3. Telegram 投遞失敗的**備援 channel**（email / 第二 bot）是否納入？（暫不，R2 緩解）
4. 跨-provider L2（Non-Goal）何時排程？卡 **Anthropic key** → 待 **ADR-019** 決議。
5. 是否為 dashboard 另立 `api.*` 唯讀 view，或直查？（暫直查，需要再加 view）

---

## 15. Appendix

- **相關 FR**：PRD-0003 FR-329（L1 budget hard cap）、FR-340（L2 guardrail budget metering）、FR-319（budget warn ratio 設定）、FR-339（guardrail BLOCK 告警）、FR-344（mass-deactivate 告警）。
- **既有樣式參照**：`infra/grafana/provisioning/alerting/rules.yaml` 的 `EMS-設備分類安全` group（低基數 `GROUP BY … HAVING` → reduce → threshold → Telegram）。
- **資料源**：`evaluate_budget`（`device_service/budget_ledger.py`，read-only 決策 helper，`WARN_RATIO=0.8`）；`llm_budget_ledger`（migration 006，UNIQUE `period_start+provider`）。
- **後續 ADR**：ADR-019 跨-provider L2 guardrail（defense-in-depth；依賴 Anthropic key）。

---

> 本文件為 Draft。依專案流程，Approved 前需經 architect + security 審視；本 PRD 主體不含可執行程式碼，實作落地時各 FR 以 provisioning 檔 + 對 dev DB 的 SQL 驗證為交付證據。
