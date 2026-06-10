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

> **MCP `:8766` 不是前端 / 瀏覽器 API**（architect MED-6 / security HIGH）：MCP 綁 `127.0.0.1:8766`（loopback）、是 **AI agent（Claude Code）通道**、帶 `AI_API_KEY`，非產品 UI API。**前端絕不得直接呼叫 MCP**（否則與「API key 不入 bundle」原則直接衝突）。人工確認所需資料一律以 REST `/devices?status=candidate` + `/human-review` 取得；**若日後確有 AI 協作需求，只能透過 BFF / server-side bridge 在伺服器側中介**（MCP 維持 loopback、key 留伺服器側），不開瀏覽器直連路徑。

### 1.5 後端相依 / 前置條件（architect MED-5 — 誠實列出，非「零後端」）

本 PRD 雖以「消費既有契約」為原則，但 review 揭露數項**真實後端相依**。**2026-06-10 已查 device-service 實作（`routes/devices.py` + `repositories/device_repo.py` + `models.py`）逐項定論**：

| # | 相依 | 調查結論（2026-06-10）|
|---|------|------|
| D1 | **特權營運讀取面**：`GET /devices` 回傳 candidate/retired + ai_confidence + 狀態 | **部分滿足，有缺口**。`GET /devices`（OPS-keyed，走 ops_pool 特權，**非** `api.devices` 白名單）`?status=&stale=` 篩選 → ✅ candidate/retired/status/classified_by 都拿得到。**但 `DeviceOut`/`_COLS` 不含 `ai_confidence`**（也無 metadata/ai_provider/stale_marked_at）→ ❌ **清單 / 信心佇列無法顯示信心值**。信心值僅在 `GET /devices/{id}/human-review` 的 `digest` dict 內（per-device）。→ **後端缺口**：信心佇列（FR-510）若要按信心排序/顯示，需把 `ai_confidence` 加進 `_COLS`+`DeviceOut`，否則前端只能 N+1 打 human-review |
| D2 | **量測契約**：`api.electricity_measurements` / `api.factory_measurements` view | **不存在（確認）**——migration 000/001 僅 `public.*` 表 GRANT `web_anon`，無 `api.*` 量測 view。→ **後端缺口**：FR-520/521 需確認直接以 PostgREST 曝露 `public.*` 量測（+CORS/網路隔離 §9.3）或另立後端 view |
| D3 | **分頁 / 排序參數**：`GET /devices` page/sort | **不足（確認）**。`list_devices` 僅 `status` + `stale` 兩個 filter，**無分頁（page/limit/offset）**、**排序硬編 `ORDER BY device_id`**。→ **後端缺口**：產品級清單（FR-500）需後端補 `page/limit/sort` 參數（裝置數一多，無分頁不可行）|
| D4 | **即時推播 transport**：realtime-service（原計畫未實作）| **不存在（確認）**——無 WebSocket/SSE 服務。→ P2 預設**輪詢** REST/PostgREST（§14 Q3）；WebSocket 需另立 realtime-service |

> **D1~D4 結論對 P1 的影響**：P1（設備管理 + 人工確認工作流）所需的 **特權讀取面骨架已存在**（OPS REST 給 status/candidate/retired），但有 **3 個明確後端小缺口需先補**才完整可用：(a) **`ai_confidence` 進 device list 回應**（信心佇列）、(b) **`GET /devices` 分頁 + 排序參數**、(c) 量測契約（屬 P2）。三者皆為 device-service REST 的小增量（非大改），可在 P1 前以 PRD-0003 後續工項補；補齊後 P1 即可估算。**這正是 §12 GATE-2 的具體內容。**

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

**前端不擁有資料模型**，全部消費後端既有契約：**主**為 device-service REST DTO（特權讀寫；含 status/ai_confidence 等 `api.*` 白名單藏起來的欄位 — 見 §8.1），`api.*` view 僅供「公開 confirmed 設備唯讀」面。前端僅有 client-side view-model / 狀態管理（不持久化於 DB）。若需新唯讀 view，走 idempotent `CREATE OR REPLACE`、遵 PRD-0003 §7.4 白名單，不破壞既有契約。

---

### 8.1 Per-page 資料來源對照（哪些頁吃 REST、哪些吃 PostgREST read view）

> 規則：**任何需要 status / classified_by / ai_confidence / metadata / signal 狀態 / candidate / retired 的頁面，一律走 device-service REST（經 BFF）**；PostgREST `api.*` 只能服務「公開的 confirmed 設備唯讀」需求。

| 頁面 / FR | 資料來源 | 端點 | Contract gap（PRD-0003 line 387 白名單刻意隱藏）|
|-----------|---------|------|------|
| 設備清單 FR-500 | **REST**（經 BFF）| `GET /devices?status=&type=&page=&sort=` | **gap D3**：分頁 / 排序參數完整度待確認；`api.devices` 給不了 candidate/retired |
| 設備詳情 FR-501 | **REST** | `GET /devices/{id}` + `/signals` | `api.device_signals` 隱藏 signal `status`/`source_ref`/`confirmed_by_ai` → 詳情需 REST |
| 狀態流轉 FR-503 | **REST** | 同上（含 status/classified_by/freeze）| **gap D1**：`api.devices` 隱藏 status/classified_by/ai_confidence/metadata/stale → **白名單不足以支撐**，須特權 REST 讀面 |
| 信心佇列 FR-510 | **REST** | `GET /devices?status=candidate` + `/human-review` | `api.devices` 只露 confirmed/active → **完全看不到 candidate**，必走 REST |
| 審閱 digest FR-511 | **REST** | `/devices/{id}/human-review`（digest）| 純文字渲染（§9.5）|
| 確認/override/reject FR-512 | **REST**（mutating）| `/confirm` `/override` `/reject` | 需 X-API-Key（OPS 通道）→ 強制 BFF |
| Correction FR-513 | **REST**（mutating）| `/ai-feedback` `/corrections` | §7.3a 後端驗證 |
| 量測即時/歷史 FR-520/521 | **待確認** | — | **gap D2**：`api.electricity_measurements`/`api.factory_measurements` **不存在**（migration 000/001 只 GRANT `public.*` 給 web_anon）→ 須確認 PostgREST 曝露或另立後端 view |
| （若有）公開 confirmed 設備唯讀 | PostgREST | `api.devices` / `api.device_signals` | 僅白名單欄位；公開性/CORS 見 §9.3 |

### 8.2 契約原則

- **本 PRD 不新增後端 API**；上表 gap（D1 特權讀面、D2 量測契約、D3 分頁/排序）需以 PRD-0003 後續或新後端 PRD 補齊，前端不擅改。
- 前端→後端呼叫**一律經 BFF**統一注入 X-API-Key（不在前端明碼）。
- 由 `api/openapi.yml` 生成 TS client，做契約測試 + runtime drift test 防漂移（§13.2 / R2）；open-ended enum 須有 unknown/default handling（§13.2）。

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

## 12. Rollout & Migration Plan

### Architecture gates（進實作前必須先定案，否則不開工）

- **GATE-1 BFF 設計定案**：BFF 技術選型 + session 機制 + role→channel-key 映射 + CSRF 策略（§9.1/9.2/9.4）**必須先拍板**。理由：device-service mutating API（confirm/override/reject）需 X-API-Key、SPA 不可持 key → P1 的核心工作流**沒有 BFF 就無法安全實作**。**BFF 未定案前，P1 不進實作。**
- **GATE-2 後端相依 D1~D4 結清**（§1.5 / §8.1）：**2026-06-10 已查明**——特權讀取面骨架已存在，但 P1 前須補 **3 個 device-service REST 小缺口**：(a) `ai_confidence` 加進 device list 回應（`_COLS`+`DeviceOut`；信心佇列 FR-510 需要）、(b) `GET /devices` 補 `page/limit/sort` 參數（FR-500）、(c) 量測契約（D2，屬 P2）。三者為小增量、以 PRD-0003 後續工項補；補齊前 FR-500/503/510 無法估算。

### 分階段

1. **P1 設備管理 + 人工確認工作流**（FR-500~513）— 對接最成熟的 device-service REST，OPS 內部先用。**前置 GATE-1 + GATE-2(D1/D3)**。**P1 同批落地 API 契約治理 enforcement**（§13.2：openapi↔runtime drift test + lint/diff/contract + `api/CHANGELOG.md`）—— 把治理從 policy 升為 enforced。
2. **P2 量測呈現**（FR-520~521）— 即時卡片 + 歷史曲線。**前置 D2（量測契約）**；即時預設輪詢。
3. **P3 角色化 / i18n / 商業化門面**（FR-530~532）。
4. **（後續 PRD）控制下發** — 待 control-service 立案。

每階段：可獨立部署、Grafana 並行不下線（漸進取代而非斷崖切換）。回滾 = 前端容器下線，後端與 Grafana 不受影響。

### P1 驗收條件（可給工程實作與 QA；非僅功能清單）

| # | 驗收項 | 準則 |
|---|--------|------|
| AC-1 | 候選清單來源 | 佇列只來自 `GET /devices?status=candidate`（經 BFF）；非 candidate 不入佇列；空佇列有明確 empty state |
| AC-2 | 排序 / 篩選 | 依 status / type / 信心 / 最後上線時間排序與篩選；參數對應後端（D3 結清後鎖定）|
| AC-3 | 狀態轉移 | confirm：candidate→confirmed；override：改 device_type+signals 並記 classified_by；reject：依後端語義；UI 即時反映新狀態且**以後端回應為準**（樂觀更新失敗要回滾）|
| AC-4 | correction 輸入限制 | 前端即時提示長度 30–500、NFKC、禁控制字元（§7.3a）；**實質驗證在後端**，前端錯誤訊息對應後端 4xx |
| AC-5 | 失敗 / 重試 | 後端 5xx / 網路失敗：明確錯誤態 + 可重試；mutating 重試須**冪等防重複**（避免重複 confirm）|
| AC-6 | audit log 顯示 | 設備詳情可看該裝置的 append-only 稽核事件（override/reject/correction/guardrail BLOCK 時間軸）|
| AC-7 | rate-limit / error UX | 命中後端 429（/ai-feedback per-key 30/h、per-device 10/h；correction 速率）時，UI 顯示「稍後再試 + 剩餘時間」，不靜默失敗 |
| AC-8 | 權限 UX | 依 role 隱藏/禁用無權操作；**且**越權請求被 BFF/後端擋（前端隱藏非安全邊界，§9.1）|

### EMS 同步義務（實作完成後）
- **`api/openapi.yml`**（**更正**：專案實際路徑為 `api/openapi.yml`，非 `doc/API.yaml`）：若前端促成任何新後端端點才更新（本 PRD 預設不新增）。
- Container Cheat Sheet：新增前端（+ BFF）容器。
- Operations Manual：前端部署/登入/角色操作節。

---

## 13. Test Strategy

### 13.1 測試層級

| 層級 | 內容 |
|------|------|
| 單元 | 元件 / view-model（Vitest + Testing Library）|
| 整合 | 對 mock 後端契約（MSW）驗工作流 |
| E2E | 關鍵流程：新增設備、確認候選、override、查歷史（Playwright）|
| 契約 | 由 `api/openapi.yml` 生成 client，契約測試防漂移（見 §13.2）|
| 覆蓋率 | 沿用專案 80% 門檻 |

### 13.2 API 契約治理（前端可信賴 openapi.yml 的前提）

> 前端最需要回答的是「**我能相信 `api/openapi.yml` 嗎？**」——治理規則集中於 **[`doc/governance/api-contract-governance.md`](../governance/api-contract-governance.md)**（單一真相）。
>
> ⚠️ **現況：該治理目前為 POLICY，非 ENFORCEMENT**——`api/CHANGELOG.md` 未建、CI gate / drift test 未實作。**本 PRD 的 P1 批次負責把它從 policy 升為 enforced**（下列即 P1 工項）：

- **`api/openapi.yml` 為 REST 唯一真相**；前端 **TS client 一律由它生成，禁止手刻**型別。
- `info.version` 採 **semver**；API 改動須 bump，breaking → MAJOR。
- **[P1 task — drift test，必做]**：CI 自動比對 committed `api/openapi.yml` vs device-service 執行期 `create_app().openapi()`（route/Pydantic 自動產出）→ 不一致 fail。**這是「openapi 是真相」能成立的關鍵**；沒有它，真相宣稱會退回人工維護（PRD-0003 d0f71e6 曾手動比對，此處自動化）。
- **CI gate**（P1 同批）：openapi **lint**（spectral/redocly）+ **diff**（oasdiff，breaking 但未 bump MAJOR → fail）+ **contract test**（生成 client 對服務/mock 驗）+ version-bump check。
- **enum 新增的前端前提**：spec 新增 enum 值在治理上為 non-breaking，但**僅當前端 generated client 對 open-ended enum 有 unknown/default 分支時**才成立；TS exhaustive switch（無 default）會被新 enum 實務破壞 → 前端**必須**有 unknown handling，否則該 enum 變更視為 migration-needed（見 governance §3）。
- 新增 **`api/CHANGELOG.md`** 記每次 API 變更（版本/級別/PR/PRD）。
- **DB schema 遷移治理另屬** [ADR-020](../adr/ADR-020-db-migration-governance.md)，不在前端範圍（避免在前端 PRD 順手換 migration 工具）。

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
- **可消費後端（前端視角）**：**device-service REST :8002（經 BFF，主）** + PostgREST `api.*`（僅公開 confirmed 唯讀面）+ migrations 009 的 `api.devices`/`api.device_signals` 白名單 view。**MCP :8766 不是前端可消費面**——loopback、AI agent 通道、帶 AI key；**瀏覽器不得直連**，僅允許 server-side / BFF / agent bridge 在伺服器側使用（見 §1 / §6.1 圖 / §9）。
- **分工對照**：[PRD-0004](PRD-0004-device-service-observability-alerting.md)（Grafana 內部 ops 觀測/告警）；本 PRD（產品級操作 UI）。

---

> **Draft v2（2026-06-09，已過 architect + security 審視）**：原 v1 骨架經兩位 reviewer 評為 NEEDS-REWORK，本版已修正——資料存取改走 device-service REST（非 `api.*` 白名單，architect HIGH）、BFF 由「選項」改為**強制**並補完整威脅模型（§9 三項 CRITICAL：BFF/session/PostgREST 公開性）、§11 補瀏覽器威脅（XSS/clickjacking/IDOR/session）、§1.5 誠實列後端相依 D1~D4。**Approved 前剩餘 blocker**：D1~D4 已查明（§1.5，2026-06-10）→ 收斂為 **3 個 device-service REST 小增量**（ai_confidence 進 list / 分頁排序 / 量測契約）需以 PRD-0003 後續工項補齊（GATE-2），及 §14 技術選型（BFF/即時機制）。控制下發仍為 Non-Goal（待 control-service PRD）。
