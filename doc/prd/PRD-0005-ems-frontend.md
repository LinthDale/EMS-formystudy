# PRD-0005：EMS 自建前端 — 產品級操作介面（Web Application）

| 欄位 | 內容 |
|------|------|
| 狀態 | **Draft v2**（2026-06-09；已過 architect + security 審視，NEEDS-REWORK 修正完成；Approved 前需解 §1.5 後端相依）|
| 起案日期 | 2026-06-09 |
| 最後修訂 | 2026-06-09（v2：資料路由改 REST、BFF 強制、§9 完整威脅模型、§11 瀏覽器威脅、§1.5 後端相依）|
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

> **資料存取分層（architect HIGH-1，關鍵更正）**：前端**所有特權 / 營運讀取一律走 device-service REST :8002（經 BFF）**，**不**走 PostgREST `api.*`。原因：migration 009 的 `api.devices` 白名單**故意只露 `status IN ('confirmed','active')`、隱藏 `status` / `ai_confidence` / `ai_provider` / `classified_by` / `metadata` / `stale_marked_at`**（防 `web_anon` 看到 OT 偵察與 AI 內部）——而前端核心（candidate/retired 佇列、信心值、狀態流轉 FR-503）正需要這些被隱藏的欄位，故 `api.*` 在設計上**服務不了**這些畫面。`api.*` 僅保留給「公開唯讀的 confirmed 設備 + 量測」面。

| 層 | 端點 | 用途 | 經過 |
|----|------|------|------|
| **device-service REST `:8002`**（主）| `GET /devices?status=&type=`、`/devices/{id}`、`/signals`、`/devices/{id}/human-review`、CRUD、`/confirm`/`/override`/`/reject`、`/ai-feedback`、`/corrections` | **全部特權讀寫 + 人工確認工作流**（含 candidate/retired/信心/狀態）| **BFF**（注入 channel key）|
| PostgREST `api.*` views | `api.devices` / `api.device_signals`（**僅 confirmed/active 白名單欄位**）| 僅「公開唯讀的已確認設備」唯讀面（若有此需求）| 見 §9（公開性 / CORS 決策）|
| 量測資料 | **契約待確認**（見下「後端相依」）| 即時卡片 / 歷史曲線 | BFF or PostgREST |

> **MCP `:8766` 不在前端可消費面**（architect MED-6 / security HIGH）：MCP 綁 `127.0.0.1:8766`、是 **AI agent（Claude Code）通道**、需 `AI_API_KEY`，非產品 API。同樣資料以 REST `/devices?status=candidate` + `/human-review` 取得。前端 / BFF **不得**直連 MCP。

### 1.5 後端相依 / 前置條件（architect MED-5 — 誠實列出，非「零後端」）

本 PRD 雖以「消費既有契約」為原則，但 review 揭露數項**真實後端相依**，逐項標記為「已存在 / 需先確認 / 需前置 PRD」：

| # | 相依 | 狀態 |
|---|------|------|
| D1 | **特權營運讀取面**：`GET /devices` 是否回傳 candidate/retired + ai_confidence + 狀態（前端所需，非 `api.devices` 白名單）| **需確認** device-service REST 是否已涵蓋；若否，需後端補（特權 REST 讀，**不**放 `web_anon`）|
| D2 | **量測契約**：`api.electricity_measurements` / `api.factory_measurements` view | **不存在**——migration 000/001 僅以 `public.*` 表 GRANT `web_anon`；需確認 PostgREST 曝露方式或另立後端 view PRD |
| D3 | **分頁 / 排序參數**：`GET /devices` 的 page/sort 完整度 | **需確認** |
| D4 | **即時推播 transport**：realtime-service（原計畫未實作）| **不存在**——見 §14 Open Q3，P2 預設輪詢 |

---

## 2. Goals / Non-Goals

### Goals

- **G1 設備管理 UI**：設備清單、詳情、CRUD、狀態流轉（candidate→confirmed→retired）視覺化，消費 `api.devices` + device-service REST。
- **G2 人工確認工作流**：低信心候選佇列 → 審閱 digest → 確認 / override / reject / 補 correction（FR-336/330/332），對接 `/human-review` + `/ai-feedback`。（佇列**計數**在 Grafana（PRD-0004 FR-406）給 on-call 看；本 PRD 給的是**可操作的佇列工作流**，兩者鏡像不重工。）
- **G3 即時與歷史量測呈現**：量測即時卡片 + 歷史曲線（消費 PostgREST views / 量測 API；即時機制見 Open Question）。
- **G4 角色化權限 UI**：依 OPS/INGEST/AI 通道差異化操作面與權限邊界。
- **G5 商業級 UX**：對標商用 EMS 的產品門面（品牌、i18n 中文在地化、響應式）。

### Non-Goals（明確排除）

- **不取代 Grafana 的內部 ops 觀測 / 告警**（PRD-0004 範圍）；兩者分工並存。
- **不在本 PRD 做控制下發（control plane）**：原始 Stage 6 的三路徑回控（AI/直接/規則）依賴尚未實作的 `control-service` + gateway write API → **列為後續 PRD / 待 control-service 立案**（見 §14）。
- 不自建告警引擎（沿用 Grafana / device-service 既有告警）。
- **本 PRD 不直接實作後端**，但**不宣稱零後端相依**——§1.5 已誠實列出 D1~D4 真實相依；其中需新增的後端（量測 view、特權讀面、分頁參數）以 PRD-0003 後續或新後端 PRD 處理，前端不擅改契約。這是 P1 可估算的前提。

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

### 設備管理（特權讀寫一律經 BFF → device-service REST :8002，**非** `api.*`）
- **FR-500** 設備清單頁：分頁/篩選/排序，經 BFF 打 `GET /devices?status=&type=`（含 candidate/retired + ai_confidence，`api.devices` 白名單給不了 → 見 §1 D1/D3）。
- **FR-501** 設備詳情頁：基本資料 + signals（`/signals`）+ 分類來源/信心，經 BFF REST。
- **FR-502** 設備 CRUD：建立/編輯/停用，經 BFF（依使用者 role 注入對應 X-API-Key 通道，前端不持 key — §9.1）。
- **FR-503** 狀態流轉視覺化：candidate/confirmed/retired/stale 狀態與凍結（freeze）呈現（資料源同 FR-500 特權 REST）。

### 人工確認工作流（經 BFF REST；**不**走 MCP）
- **FR-510** 低信心佇列頁：列出待確認候選，經 BFF `GET /devices?status=candidate` + `/human-review`（**不**用 MCP :8766 — §1 / §9）。
- **FR-511** 審閱 digest：呈現 AI 分類理由、signals 建議、信心值；**digest 純文字渲染**（§9.5 XSS）。
- **FR-512** 確認動作：confirm / override（改 device_type + signals）/ reject，經 BFF REST（CSRF 防護 §9.4）。
- **FR-513** Correction 補充：填人工修正（§7.3a 驗證在後端，前端做即時提示），觸發重分類。

### 量測呈現
- **FR-520** 即時量測卡片：依域（electricity / factory）顯示最新值。**量測契約待確認**（§1 D2：`api.*` 量測 view 不存在；P2 預設輪詢，§14 Q3）。
- **FR-521** 歷史曲線：時間範圍查詢，消費量測契約（同 D2 待確認）。

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
   使用者瀏覽器（SPA：React + TS + Vite，候選；持 opaque session cookie，無任何 API key）
        │ HTTPS（CSP / HSTS / X-Frame-Options 等 headers，見 §9）
        ▼
   ┌──────────────────────────────────────────┐
   │  BFF（強制，stateful）                      │  ← session 驗證 + role→channel-key 映射
   │  • 驗 session（每請求）                      │
   │  • 依使用者 role 注入正確 X-API-Key（OPS/...）│
   │  • endpoint 級授權；隱藏內部端點             │
   └──────────┬───────────────────────────────┘
              │  X-API-Key（僅存在於 BFF 伺服器側，永不下放瀏覽器）
        ┌─────┴───────────────┐
        ▼                     ▼
  device-service:8002    (公開唯讀面，若有) PostgREST api.*
  (特權讀寫 + 工作流)       (confirmed 設備白名單；公開性/CORS 見 §9)

  ✗ MCP:8766 不在此圖（127.0.0.1-only，AI 通道，瀏覽器/BFF 皆不連）
```

### 6.2 Container

- **前端容器**：SPA 靜態檔由 nginx 服務（強制 security headers，見 §9）。
- **BFF 容器（強制，非選項）**：security review 定調 BFF **不是架構選擇而是安全約束**。原因有二：(1) SPA 公開可下載，三條 X-API-Key 絕不能入 bundle；(2) device-service 為 **channel-keyed**——OPS/INGEST/AI 三 key 對應 PRD-0003 §6.5 的**不同 DB 連線池與權限集**，故需**每請求 session→role→key 的伺服器側映射**，這是 stateful BFF，**純 reverse-proxy 注單一靜態 key 不可行**（會讓唯讀使用者也能觸發 CRUD）。

### 6.3 Data Flow

- 全部讀寫**經 BFF**：BFF 先驗 session → 依 role 選 channel key → 轉發 device-service。
- `api.*` PostgREST 公開唯讀面（若採用）的可達性與 CORS 由 §9 決策（須非公網可達 + CORS 限定來源）。
- 即時量測：P2 預設**輪詢**（現有後端唯一可行）；WebSocket/SSE 為獨立 spike，依賴未實作的 realtime-service，排在 P1/P2 之後（§14 Open Q3）。

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

> 前端是本系統**最大的新攻擊面**（瀏覽器可達 + 消費三條特權 key 通道）。以下為 review 後的完整威脅模型；標 **[必過]** 者為 Approved 前的不可協商前置。

### 9.1 金鑰與 BFF（CRITICAL）

- **[必過] BFF 強制，非選項**：SPA bundle 靜態、公開可下載，**無法保護機密**。三條 X-API-Key 帶寫入 / admin 權限，**絕不可**進 bundle、不可下放瀏覽器、不可由前端傳輸。BFF（或具憑證注入的認證 reverse proxy）為**無條件架構約束**。
- **[必過] role→channel-key 授權契約**：每個 session 標一個 role（OPS / INGEST / read-only）；BFF 將 role 映射到**至多一條** key 通道，並做 **endpoint 級授權**（例：INGEST role 的 session 即使 BFF 持有 OPS key 也**不得**轉發 `POST /devices`）。role 降級時 session 失效。
- 真正權限邊界在**後端 + BFF**；前端依 role 隱藏 / 禁用操作僅為 UX，**不可信**。

### 9.2 Session 安全（CRITICAL）

- **[必過] session token 性質**：以 `HttpOnly; Secure; SameSite=Strict` cookie 簽發（或伺服器側 bearer、僅存記憶體）；**禁用 `localStorage` / `sessionStorage` 存 session 或任何 key 衍生物**。
- **[必過]** 定義最大存活時間 + idle timeout；BFF **每請求**驗 session 後才注入 key。

### 9.3 PostgREST 公開面（CRITICAL）

- `api.devices` / `api.device_signals` GRANT 給 `web_anon` → PostgREST 對**任何未認證 HTTP 請求**回傳。本 PRD 必須**明確定調**其一：
  - **(預設採此) 視為「公開唯讀的 confirmed 設備」面**：接受 unauthenticated 讀，但**[必過]** 以網路層緩解——PostgREST **不對公網開放**（限內網 / 防火牆後），且 **[必過]** `PGRST_SERVER_CORS_ALLOWED_ORIGINS` 僅限前端來源；或
  - 若任何設備讀取需認證 → 一律改走 BFF（session 驗證後轉發），不直連 PostgREST。
- 無論何者，**特權欄位永不經 `api.*`**（見 §1 資料分層）。

### 9.4 BFF mutating 端點防護（HIGH）

- **[必過] CSRF**：cookie-based session 下，BFF 的 POST/PUT/DELETE（CRUD/confirm/override/correction）須 CSRF 防護——`SameSite=Strict` + **origin-header 驗證**，或 double-submit / synchronizer token，擇一明定。
- **[必過] IDOR**：SPA 會以 `device_id` 組 URL；BFF / device-service 須對**每個資源 URL** 重驗該 session 是否有權存取該特定 device（防 INGEST 列舉 OPS-only 裝置）。

### 9.5 瀏覽器 / 內容安全（HIGH + LOW）

- **[必過] Security headers**（nginx，CI 驗存在）：`Content-Security-Policy`（限 `script-src` / `connect-src` 於已知來源）、`X-Frame-Options: DENY`（防 clickjacking 人工確認按鈕）、`X-Content-Type-Options: nosniff`、`Strict-Transport-Security`、`Referrer-Policy: strict-origin-when-cross-origin`。
- **XSS**：React auto-escaping 為底線；**禁用 `dangerouslySetInnerHTML`**；後端來的自由文字（device name/type、correction）顯示前處理。
- **[必過] AI digest 渲染**（FR-511）：`device_review_digests` 為 **LLM 產出**、且寫入端可能被 MQTT payload 注入——前端**僅以純文字渲染**（無 innerHTML、無未消毒的 markdown→HTML；如需 markdown 用 DOMPurify）；digest 渲染元件列入 code-review XSS 檢查。

### 9.6 其他

- **輸入驗證**：前端做即時 UX 提示，§7.3a 等實質驗證**以後端為準**（前端不可信）。
- **稽核**：所有變更經 device-service → 既有 append-only audit（前端無需另處理）。
- **HTTPS 端到端**：強制，配合 `Secure` cookie，防 session 竊取。

---

## 10. Observability

- 前端錯誤/效能監控（如 Sentry / web-vitals）— 工具待選。
- 後端 ops 觀測仍在 **Grafana（PRD-0004）**，本 PRD 不重做。
- 前端僅補使用者端遙測（互動成功率、頁面延遲），不與 ops 告警混。

---

## 11. Risks & Mitigations

| # | 風險 | 等級 | 對策 |
|---|------|------|------|
| R1 | **金鑰外洩**（嵌入 SPA bundle / 瀏覽器 network tab）| **高** | 強制 BFF 注入（§9.1）；SPA 永不持 key；CI 掃 bundle 不含 key |
| R2 | 前後端契約漂移 | 中 | 由 openapi.yml 生成 TS client；契約測試 |
| R3 | 即時機制選錯（成本/複雜度）| 中 | P2 預設輪詢；WebSocket/SSE 獨立 spike（§14 Q3）|
| R4 | 範圍蔓延到控制下發 | 中 | control plane 明列 Non-Goal，待 control-service PRD |
| R5 | 與 Grafana 職責重疊造成重工 | 中 | 邊界已釐清：Grafana=ops 觀測，本 PRD=產品操作 |
| R6 | 商用化品質門檻高（i18n/無障礙/響應式）| 中 | 分階段交付，先 OPS 內部工作流，再對外品牌頁 |
| R7 | **XSS**（device name/type/correction/AI digest 渲染）| **高** | React auto-escape；禁 `dangerouslySetInnerHTML`；digest 純文字 / DOMPurify（§9.5）|
| R8 | **Clickjacking**（劫持人工確認 confirm/override 按鈕）| 中 | `X-Frame-Options: DENY`（§9.5）|
| R9 | **Session 竊取**（網路攔截）| **高** | HTTPS 端到端 + `HttpOnly; Secure` cookie（§9.2）|
| R10 | **IDOR**（以 device_id 列舉越權設備）| **高** | BFF/後端對每個資源 URL 重驗 session 權限（§9.4）|
| R11 | **PostgREST 公開讀**（`web_anon` 未認證可讀 `api.devices`）| 中 | 非公網可達 + CORS 限定來源（§9.3）|
| R12 | **BFF 未實作 → key 暴露於瀏覽器** | **CRITICAL** | BFF 為不可協商前置（§9.1）；無 BFF 不得上線 |

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
2. ~~是否需要 BFF？~~ **已定案：BFF 強制（§9.1）。** 殘留：BFF 技術選型（Node/Fastify vs Python/FastAPI BFF）+ session store。
3. **即時量測機制**：**P2 預設純輪詢**（現有後端唯一可行，無新服務）；WebSocket（依原計畫未實作的 realtime-service）/ SSE 為獨立 spike，排 P1/P2 之後。
4. **程式碼位置**：**暫定 monorepo `services/frontend`**（契約測試 openapi→TS client 就近），除非有 stakeholder 理由改獨立 repo。
5. **控制下發何時做**：依賴 control-service + gateway write API（原始 Stage 6，未實作）→ **另立 PRD**（Non-Goal）。
6. **量測 PostgREST 契約（§1 D2）**：`api.electricity_measurements` 等是否存在，或需新後端 view PRD？
7. **PostgREST 公開性（§9.3）**：confirmed 設備唯讀面是「可接受未認證 + 網路隔離」還是「一律走 BFF」？（預設前者 + CORS 限定）
8. **i18n 範圍**：僅中文，或中英雙語（商業外銷考量）？
9. 設計系統 / 品牌規範來源？

---

## 15. Appendix

- **原始前端設計**：`doc/archive/plan/EMS實作計畫.md`（§9 frontend React SPA；Stage 2~6 前端頁清單；決策 4「前端」）。
- **降為待決策的紀錄**：`doc/archive/stage_2/README.md`（Grafana 取代 frontend；設備管理頁待決策）、`PRD-0001`（❌ 前端 SPA，Stage 2 用 Grafana 取代）、簡報（前端形式待定）。
- **可消費後端**：PRD-0003 device-service REST/MCP、PostgREST `api.*`、migrations 009 的 `api.devices`/`api.device_signals` 白名單 view。
- **分工對照**：[PRD-0004](PRD-0004-device-service-observability-alerting.md)（Grafana 內部 ops 觀測/告警）；本 PRD（產品級操作 UI）。

---

> **Draft v2（2026-06-09，已過 architect + security 審視）**：原 v1 骨架經兩位 reviewer 評為 NEEDS-REWORK，本版已修正——資料存取改走 device-service REST（非 `api.*` 白名單，architect HIGH）、BFF 由「選項」改為**強制**並補完整威脅模型（§9 三項 CRITICAL：BFF/session/PostgREST 公開性）、§11 補瀏覽器威脅（XSS/clickjacking/IDOR/session）、§1.5 誠實列後端相依 D1~D4。**Approved 前剩餘 blocker**：D1~D4 後端相依需確認 / 立案（尤其 D2 量測契約、D1 特權讀面），及 §14 技術選型。控制下發仍為 Non-Goal（待 control-service PRD）。
