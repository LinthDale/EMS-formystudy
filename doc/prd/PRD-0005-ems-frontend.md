# PRD-0005：EMS 自建前端 — 產品級操作介面（Web Application）

| 欄位 | 內容 |
|------|------|
| 狀態 | **Draft**（2026-06-09 起案；骨架待 review） |
| 起案日期 | 2026-06-09 |
| 最後修訂 | 2026-06-09（v1 骨架初稿） |
| 對應決策紀錄 | 還原原始計畫 `doc/archive/plan/EMS實作計畫.md` 之自寫前端（Stage 2~6 React SPA），當時因 ADR-001 開源優先暫以 Grafana 取代、降為「待決策」 |
| 取代 / 補充 | **補充**全線 PRD；消費 PRD-0001/0002/0003 既有後端契約；與 [PRD-0004](PRD-0004-device-service-observability-alerting.md)（Grafana 內部 ops 觀測）**分工並存，非替代** |
| 邊界釐清 | Grafana = 運維內部可觀測性 / 告警；本 PRD = 客戶 / 操作人員的產品 UI |

---

## 1. Overview & Context

### 業務背景

原始 MVP 設計（`archive/plan/EMS實作計畫.md`）規劃了一個自寫 **React + TypeScript + Vite** 前端，涵蓋即時卡片、設備管理、告警列表、需量/電費、控制面板等頁。落地時依 **ADR-001「開源優先」**，Stage 1/2 先以 **Grafana** 取代自寫前端（0 程式碼、同時做告警），自寫前端被**降為「待決策」**（`archive/stage_2/README.md`：「前端設備管理頁：Grafana 還不夠，可能需要簡單 HTML 或 React」）。

至今後端已大幅成熟（PRD-0001/0002/0003 全 Implemented）：device registry、AI 分類、人工確認佇列、correction loop、MCP、稽核、預算守衛皆已就緒，且對外暴露了乾淨的 REST / PostgREST 契約。Grafana 能做監控與告警，但**做不了**產品級的互動操作（設備 CRUD 表單、人工確認工作流、控制下發、角色化權限 UI）。

> decision-log Q14-5 已鎖定：「Grafana panels 鎖 4 個…**不做 device list**」——即設備管理 UI 從一開始就不是 Grafana 的職責，本 PRD 補上這塊。

### 痛點（Grafana 補不了的）

1. **互動操作缺口**：設備新增/編輯、確認候選、override、控制下發都需要表單與工作流，Grafana 是唯讀儀表板，做不到。
2. **人工確認工作流**：FR-336 的低信心佇列 + correction loop 需要一個「審閱 → 修正 → 重分類」的互動介面，目前只能靠 API / MCP。
3. **角色化體驗**：運維 / 採集端 / AI 三通道（OPS/INGEST/AI）需要差異化 UI 與權限邊界呈現。
4. **品牌與商業化**：對標 Schneider PME / Advantech，自有前端是商業產品的門面，Grafana 截圖無法當賣點。

### 上下游（可消費的既有後端契約）

| 層 | 端點 | 用途 |
|----|------|------|
| PostgREST `api.*` views | `api.electricity_measurements` / `api.factory_measurements` / `api.devices` / `api.device_signals` | 唯讀查詢（量測、設備清單）|
| device-service REST `:8002` | `/devices` CRUD、`/confirm`/`/override`/`/reject`、`/devices/{id}/human-review`、`/ai-feedback`、`/corrections`、`/signals` | 控制面 + 人工確認工作流 |
| device-service MCP `:8766` | list_low_confidence_candidates / get_device_digest / classify_with_context | AI 協作通道（前端可選用）|

---

## 2. Goals / Non-Goals

### Goals

- **G1 設備管理 UI**：設備清單、詳情、CRUD、狀態流轉（candidate→confirmed→retired）視覺化，消費 `api.devices` + device-service REST。
- **G2 人工確認工作流**：低信心候選佇列 → 審閱 digest → 確認 / override / reject / 補 correction（FR-336/330/332），對接 `/human-review` + `/ai-feedback`。
- **G3 即時與歷史量測呈現**：量測即時卡片 + 歷史曲線（消費 PostgREST views / 量測 API；即時機制見 Open Question）。
- **G4 角色化權限 UI**：依 OPS/INGEST/AI 通道差異化操作面與權限邊界。
- **G5 商業級 UX**：對標商用 EMS 的產品門面（品牌、i18n 中文在地化、響應式）。

### Non-Goals（明確排除）

- **不取代 Grafana 的內部 ops 觀測 / 告警**（PRD-0004 範圍）；兩者分工並存。
- **不在本 PRD 做控制下發（control plane）**：原始 Stage 6 的三路徑回控（AI/直接/規則）依賴尚未實作的 `control-service` + gateway write API → **列為後續 PRD / 待 control-service 立案**（見 §14）。
- 不自建告警引擎（沿用 Grafana / device-service 既有告警）。
- 不改任何後端契約；若前端需要新端點，另以 PRD-0003 後續或新後端 PRD 處理，不在本 PRD 擅改。

---

## 3. User Stories & Personas

| Persona | 場景 | 需求 |
|---------|------|------|
| **運維（OPS）** | 新裝置上線、日常管理 | 設備 CRUD、確認候選、override 錯誤分類、看狀態總覽 |
| **資料治理 / 確認人員** | 處理 AI 低信心結果 | 佇列 → 審 digest → 一鍵 confirm 或填 correction 重分類 |
| **管理層 / 客戶** | 看整體狀態 | 即時量測、設備數、健康度（唯讀、品牌化呈現）|
| **採集端維運（INGEST）** | 確認資料進得來 | 量測即時值、裝置最後上線時間 |

---

## 4. Functional Requirements

> 編號 FR-5xx（PRD-0005 命名空間）。骨架階段先列範圍，細部互動規格待 review 後逐條展開。

### 設備管理
- **FR-500** 設備清單頁：分頁/篩選/排序，消費 `api.devices`（白名單欄位）。
- **FR-501** 設備詳情頁：基本資料 + signals（`api.device_signals`）+ 分類來源/信心。
- **FR-502** 設備 CRUD：建立/編輯/停用，對接 device-service REST（夾對應 X-API-Key 通道）。
- **FR-503** 狀態流轉視覺化：candidate/confirmed/retired/stale 狀態與凍結（freeze）呈現。

### 人工確認工作流
- **FR-510** 低信心佇列頁：列出待確認候選（對接 `/human-review` / MCP list_low_confidence）。
- **FR-511** 審閱 digest：呈現 AI 分類理由、signals 建議、信心值。
- **FR-512** 確認動作：confirm / override（改 device_type + signals）/ reject，對接既有 REST。
- **FR-513** Correction 補充：填人工修正（§7.3a 驗證在後端，前端做即時提示），觸發重分類。

### 量測呈現
- **FR-520** 即時量測卡片：依域（electricity / factory）顯示最新值。
- **FR-521** 歷史曲線：時間範圍查詢，消費量測 views。

### 平台
- **FR-530** 角色化登入與權限 UI：OPS/INGEST/AI 差異化（金鑰管理見 §9）。
- **FR-531** i18n：中文在地化為主（沿用既有 UI 中文化慣例）。
- **FR-532** 響應式 / 無障礙基本支援。

---

## 5. Non-Functional Requirements（量化，骨架）

| NFR | 指標 | 目標（待 review 確認）|
|-----|------|------|
| 首屏 | LCP | < 2.5s |
| 互動 | 操作回應 | < 200ms（樂觀更新 + 後端確認）|
| 即時刷新 | 量測卡片延遲 | ≤ 5s（沿用既有 Grafana 5s 刷新基準，機制見 Open Q）|
| 安全 | 金鑰不落前端原始碼 | API key 經 BFF / proxy，不嵌 SPA bundle（見 §9）|
| 可用性 | 後端故障降級 | 唯讀資料快取 + 明確錯誤態，不白屏 |
| i18n | 中文覆蓋 | 100% 操作字串 |

---

## 6. System Architecture（骨架）

### 6.1 Context

```
   使用者瀏覽器
        │ HTTPS
        ▼
   ┌─────────────────────┐
   │  EMS Frontend (SPA) │  React + TypeScript + Vite（候選，待 §14 技術選型）
   └──────────┬──────────┘
              │  （金鑰不入 bundle → 經 BFF / reverse proxy 注入）
        ┌─────┴───────────────────────────┐
        ▼                 ▼                ▼
  PostgREST api.*   device-service:8002   (選用) MCP:8766
  (唯讀量測/清單)    (CRUD/確認/correction)  (AI 協作)
```

### 6.2 Container

新增**一個前端容器**（SPA 靜態檔由 nginx 服務）+（可能）一個輕量 **BFF / reverse-proxy**（注入 API key、聚合呼叫、隱藏內部端點）。是否需要獨立 BFF 待 §9 安全評估與 §14 選型決定。

### 6.3 Data Flow

唯讀資料走 PostgREST；變更/工作流走 device-service REST；即時量測機制（WebSocket vs 輪詢 vs SSE）為 Open Question。

---

## 7. Data Model

**前端不擁有資料模型**，全部消費後端既有 schema（`api.devices` / `api.device_signals` / 量測 views / device-service DTO）。前端僅有 client-side view-model / 狀態管理（不持久化於 DB）。若需新唯讀 view，走 idempotent `CREATE OR REPLACE`、遵 PRD-0003 §7.4 白名單，不破壞既有契約。

---

## 8. API Contract

- **消費既有契約**，不新增後端 API（骨架階段假設現有端點足夠；review 時逐 FR 核對缺口）。
- 已知可能缺口（列 Open Question / 後端後續）：即時推播端點、前端用聚合查詢、分頁/排序參數完整度。
- 前端對後端的呼叫經 BFF/proxy 統一加 X-API-Key（不在前端明碼）。

---

## 9. Security & Privacy

- **金鑰絕不入前端 bundle**：SPA 為公開可下載，OPS/INGEST/AI key 必須由 **BFF / server-side proxy** 注入，前端只持短期 session。← 關鍵安全決策，影響架構（是否需 BFF）。
- **AuthN/AuthZ**：使用者登入 → session → 後端通道金鑰映射；前端依角色隱藏/禁用操作，但**真正權限邊界在後端**（前端僅 UX，不可信）。
- **輸入驗證**：前端做即時 UX 提示，§7.3a 等實質驗證以後端為準（前端驗證不可信）。
- **稽核**：所有變更動作經 device-service → 既有 append-only audit（不需前端額外處理）。
- Threat model 與 BFF 設計待 review 細化。

---

## 10. Observability

- 前端錯誤/效能監控（如 Sentry / web-vitals）— 工具待選。
- 後端 ops 觀測仍在 **Grafana（PRD-0004）**，本 PRD 不重做。
- 前端僅補使用者端遙測（互動成功率、頁面延遲），不與 ops 告警混。

---

## 11. Risks & Mitigations

| # | 風險 | 等級 | 對策 |
|---|------|------|------|
| R1 | **金鑰外洩**（嵌入 SPA bundle）| 高 | 強制 BFF/proxy 注入；CI 掃 bundle 不含 key（§9）|
| R2 | 前後端契約漂移 | 中 | 由 openapi.yml 生成 TS client；契約測試 |
| R3 | 即時機制選錯（成本/複雜度）| 中 | §14 先做技術 spike 比較 WebSocket/SSE/輪詢 |
| R4 | 範圍蔓延到控制下發 | 中 | control plane 明列 Non-Goal，待 control-service PRD |
| R5 | 與 Grafana 職責重疊造成重工 | 中 | 邊界已釐清：Grafana=ops 觀測，本 PRD=產品操作 |
| R6 | 商用化品質門檻高（i18n/無障礙/響應式）| 中 | 分階段交付，先 OPS 內部工作流，再對外品牌頁 |

---

## 12. Rollout & Migration Plan（骨架）

分階段（對齊原始 Stage 思路，但聚焦現有後端能力）：

1. **P1 設備管理 + 人工確認工作流**（FR-500~513）— 對接最成熟的 device-service REST，OPS 內部先用。
2. **P2 量測呈現**（FR-520~521）— 即時卡片 + 歷史曲線。
3. **P3 角色化 / i18n / 商業化門面**（FR-530~532）。
4. **（後續 PRD）控制下發** — 待 control-service 立案。

每階段：可獨立部署、Grafana 並行不下線（漸進取代而非斷崖切換）。回滾 = 前端容器下線，後端與 Grafana 不受影響。

### EMS 同步義務（實作完成後）
- `doc/API.yaml`：若前端促成任何新後端端點才更新（本 PRD 預設不新增）。
- Container Cheat Sheet：新增前端（+ 可能 BFF）容器。
- Operations Manual：前端部署/登入/角色操作節。

---

## 13. Test Strategy（骨架）

| 層級 | 內容 |
|------|------|
| 單元 | 元件 / view-model（Vitest + Testing Library）|
| 整合 | 對 mock 後端契約（MSW）驗工作流 |
| E2E | 關鍵流程：新增設備、確認候選、override、查歷史（Playwright）|
| 契約 | 由 openapi.yml 生成 client，契約測試防漂移 |
| 覆蓋率 | 沿用專案 80% 門檻 |

---

## 14. Open Questions（骨架階段重點）

1. **技術選型**：React+TS+Vite（原始計畫）vs 其他？UI library（MUI / Ant / shadcn）？狀態管理（TanStack Query + Zustand）？
2. **是否需要獨立 BFF**：金鑰注入 + 聚合 + 隱藏內部端點 → 多一個服務 vs reverse-proxy 注入即可？（安全 §9 主導）
3. **即時量測機制**：新增 realtime/WebSocket 服務（原始計畫的 realtime-service，未實作）vs SSE vs 純輪詢 PostgREST？成本/複雜度 spike。
4. **程式碼位置**：是否獨立 repo（原始計畫傾向獨立），或 monorepo `services/frontend`？（影響 CI/部署）
5. **控制下發何時做**：依賴 control-service + gateway write API（原始 Stage 6，未實作）→ 另立 PRD 還是併入本 PRD 後期？
6. **i18n 範圍**：僅中文，或中英雙語（商業外銷考量）？
7. 設計系統 / 品牌規範來源？

---

## 15. Appendix

- **原始前端設計**：`doc/archive/plan/EMS實作計畫.md`（§9 frontend React SPA；Stage 2~6 前端頁清單；決策 4「前端」）。
- **降為待決策的紀錄**：`doc/archive/stage_2/README.md`（Grafana 取代 frontend；設備管理頁待決策）、`PRD-0001`（❌ 前端 SPA，Stage 2 用 Grafana 取代）、簡報（前端形式待定）。
- **可消費後端**：PRD-0003 device-service REST/MCP、PostgREST `api.*`、migrations 009 的 `api.devices`/`api.device_signals` 白名單 view。
- **分工對照**：[PRD-0004](PRD-0004-device-service-observability-alerting.md)（Grafana 內部 ops 觀測/告警）；本 PRD（產品級操作 UI）。

---

> 本文件為 **Draft 骨架**：範圍、Goals、FR 列表、風險、Open Questions 已就位；技術選型、詳細互動規格、即時機制、BFF 設計待 review 後逐節展開。依專案流程，Approved 前需經 architect + security 審視（金鑰注入 §9 為安全審視重點）。
