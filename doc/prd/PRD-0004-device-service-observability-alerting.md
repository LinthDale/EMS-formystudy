# PRD-0004：Device-Service 營運可觀測性 — 預算告警與分類健康度 Dashboards

| 欄位 | 內容 |
|------|------|
| 狀態 | **Draft v2**（2026-06-09；已過 architect + security 審視，APPROVE-WITH-CHANGES 修正完成）|
| 起案日期 | 2026-06-09 |
| 最後修訂 | 2026-06-09（v2：比例分母改取 ledger `budget_usd`、index/receiver 更正、FR-408 latency 移 Open Q、Telegram 揭露界線 + chatid 殘留風險）|
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

> **比例分母來源（architect HIGH-1，關鍵）**：所有預算比例一律取 ledger **row 自身的 `budget_usd`** 欄位（`SUM(cost_usd) / budget_usd`），**不**用 env 常數 `LLM_MONTHLY_BUDGET_USD` / `GUARDRAIL_MONTHLY_BUDGET_USD`。原因：`llm_budget_ledger`（migration 006）每 `(period_start, provider)` row 存 `budget_usd`，且 PRD-0003 FR-334 `/admin/budget/extend` 會**就地調高該 row 的 budget**；若用 env 常數，緊急加額度後常數與真實上限漂移，告警門檻即算錯。以 ledger 為單一真相，使告警與 `evaluate_budget`（fail-closed gate）定義一致。

- **FR-400 L1 預算 80% warn**：對 `llm_budget_ledger` 當期 `provider != 'guardrail'` row，`SUM(cost_usd) / budget_usd` ≥ `BUDGET_WARN_RATIO`(0.8) 且 < 1.0 時，發 Telegram warn。
- **FR-401 L1 預算 100% exhausted**：同比例 ≥ 1.0 時，發**高優先**告警，訊息標明「分類已 fail-closed 降級為 system_fallback」。warn 與 exhausted 為**互斥區間**（[0.8,1.0) vs [1.0,∞)），同一時點僅一條成立，不重複發。
- **FR-402 guardrail 預算告警**：對 `provider='guardrail'` row，`SUM(cost_usd) / budget_usd`，同樣 80% warn / 100% exhausted（100% 時連 L1 一起停，訊息載明）。**相依**：本 FR 的正確性依賴 guardrail row 的 `cost_usd` 被正確計量；若日後 ADR-019 啟用 Anthropic L2 而未補定價（cost=0），此告警將永不觸發 → 見 ADR-019 之 pricing 前置條件。
- **FR-403 低基數聚合**：告警 SQL 以 `GROUP BY period_start, provider … HAVING` 取得「跨閾值之 provider 數」單一 scalar；`provider` / 金額**不進 Grafana label**（沿用 FR-339 樣式；訊息 body 的揭露見 §8/§9）。
- **FR-404 noData/execErr 韌性**：`noDataState=OK`、`execErrState=Error`；ledger 無當期 row（月初）視為 0% 不誤觸。**`for` 視窗**：warn 用 `for=5m`（避免邊界抖動重發；cost 當期單調遞增，5m 去抖足夠），exhausted 用 `for=0s`（觸頂即報，比照既有安全規則）。
- **FR-405 provisioned**：新增 alert group `EMS-預算告警` 於 `infra/grafana/provisioning/alerting/rules.yaml`，`receiver: Telegram`（沿用既有 contact point，名稱即 `Telegram`），可重啟重建、無 provisioning error。

### Dashboards（Panels）

- **FR-406 待人工佇列 panel**：`devices` 中 `status='candidate'`（或 `ai_confidence < LLM_CONFIDENCE_THRESHOLD`）之計數時序，含當前值 stat。
- **FR-407 裝置狀態分布 panel**：`devices` 依 `status`（candidate/confirmed/retired）分組計數（pie / bar）。
- **FR-408 分類 error rate panel**：以 `device_audit_log`（分類 / guardrail BLOCK / fallback 事件）近窗計 error rate。**latency 暫不納入**——PRD-0003 §7 未確立 per-classification latency 欄位，無資料來源；latency 移至 §14 Open Questions（待確認是否新增量測欄位，否則此 panel 僅 error rate）。
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
| 查詢成本 | 單次 alert SQL | 以 `period_start = 當期` 選 row，命中 `UNIQUE (period_start, provider)`（migration 006）；表極小，< 50 ms on dev DB（注意：另有 `(active, provider)` 索引供 active 過濾，alert 以 period_start 為主述詞）|
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

> Guideline §3.1 要求 C4 L1/L2 + Data Flow 三圖；本 PRD 為**單一容器之上的 read-only 變更（零新元件）**，故 C4-L2 容器圖以例外省略，僅保留 §6.1 context + §6.3 data flow。

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

**決策（原 Open Q5，已定案）**：dashboard **直查** `public.*` 內部表，**不**新增 `api.*` view —— Grafana 走 `timescaledb-ems` datasource（唯讀帳號）讀內部表，是既有樣式；保持 `api.*` 白名單面不變、`web_anon` 權限不擴張。

**DB 權限界線（security LOW）**：Grafana datasource 帳號對 `llm_budget_ledger` / `device_review_digests` / `device_audit_log` / `devices` 僅唯讀 SELECT；**本 PRD 不新增任何 GRANT 給 `web_anon`**，且 `device_review_digests` / `device_audit_log` **永不**經 `api.*` 對外曝露（僅內部 Grafana 可見）。

---

## 8. API Contract

- **無新 REST / MQTT 契約**。Grafana 直查 DB。
- **Telegram 訊息格式**（contact point template）：
  - warn：`⚠️ [EMS] {provider} 月預算達 {pct}%（{spent}/{cap} USD）`
  - exhausted：`🛑 [EMS] {provider} 月預算 100% — 分類已 fail-closed 降級 system_fallback，請加額度或切 mock`
- 不含 device_id / 個別裝置資料（低基數 + 隱私）。
- **揭露界線（security MED）**：訊息 body 含 `{provider}`（揭露 L1/guardrail 內部架構）與 `{spent}/{cap}` 金額——屬**內部 ops 資訊**，故 **Telegram 頻道必須為私有**（非公開群/頻道），不得轉發外部。若未來頻道對客戶開放，template 須改為**只給百分比**、移除 `{provider}` 與絕對金額。

---

## 9. Security & Privacy

- 告警與 panel 僅輸出**聚合數量與比例**，不外洩 `device_id`、`key_id`、correction 內容。
- **Telegram bot token** 為機密，已以 `${TELEGRAM_BOT_TOKEN}` env 注入 contact-points.yaml，**不進 git**（沿用 FR-339/344）；若曾誤 commit，須立即經 BotFather 輪替。
- **`chatid` 硬編於 git（accepted residual risk）**：`contact-points.yaml` 的 `chatid: "7171144544"` 為硬編——因 Grafana 把 numeric 欄位當 JSON number 解析、無法用 env var。chat ID **非憑證**（沒有 bot token 無法發訊），但會在 repo 揭露特定 chat ID（社交工程目標面）；列為已知可接受殘留風險，頻道遷移時舊 ID 留 git 史無獨立風險。
- Grafana datasource 為唯讀帳號（見 §7 權限界線）；本 PRD 不擴張任何 DB 權限、不新增 `web_anon` GRANT。
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
| R1 | **告警抖動**（比例在門檻附近震盪重複發）| 中 | 已定案（FR-404）：warn `for=5m` 去抖 + cost 當期單調遞增 + warn/exhausted 互斥區間（FR-401），三者使同點僅一條成立、不重複發 |
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

- `api/openapi.yml`（實際路徑；非 `doc/API.yaml`）：本 PRD 無新 REST，註明告警/儀表板為 Grafana provisioning（非 REST）。
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
5. ~~是否為 dashboard 另立 `api.*` view？~~ **已定案（§7）：直查 `public.*`，不新增 view。**
6. **分類 latency 是否要計量**（FR-408）？PRD-0003 §7 無 per-classification latency 欄位 → 若要 latency panel，須先在 device-service 落一個 latency 量測欄位 / audit detail；否則 FR-408 僅做 error rate。

---

## 15. Appendix

- **相關 FR**：PRD-0003 FR-329（L1 budget hard cap）、FR-340（L2 guardrail budget metering）、FR-319（budget warn ratio 設定）、FR-339（guardrail BLOCK 告警）、FR-344（mass-deactivate 告警）。
- **既有樣式參照**：`infra/grafana/provisioning/alerting/rules.yaml` 的 `EMS-設備分類安全` group（低基數 `GROUP BY … HAVING` → reduce → threshold → Telegram）。
- **資料源**：`evaluate_budget`（`device_service/budget_ledger.py`，read-only 決策 helper，`WARN_RATIO=0.8`）；`llm_budget_ledger`（migration 006，UNIQUE `period_start+provider`）。
- **後續 ADR**：ADR-019 跨-provider L2 guardrail（defense-in-depth；依賴 Anthropic key）。

---

> 本文件為 Draft。依專案流程，Approved 前需經 architect + security 審視；本 PRD 主體不含可執行程式碼，實作落地時各 FR 以 provisioning 檔 + 對 dev DB 的 SQL 驗證為交付證據。
