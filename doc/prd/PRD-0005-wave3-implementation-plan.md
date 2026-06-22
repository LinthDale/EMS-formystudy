# PRD-0005 Phase-1 Wave 3 實作計畫 — 設備 CRUD / Correction / 量測視覺化 / OIDC 登入

| 欄位 | 內容 |
|------|------|
| 對應 PRD | [PRD-0005](PRD-0005-ems-frontend.md) §6（FR-502/513/520/521）/ §8.1 / §8.2 / §9.1 / §9.3 / §9.4 / §9.5 |
| 新增 / 影響 ADR | **[ADR-026](../adr/ADR-026-bff-device-create-update-facade.md)（本批新開 — BFF create/update facade）**；沿用 [ADR-023](../adr/ADR-023-bff-session-and-role-channel-key-authz.md) / [ADR-024](../adr/ADR-024-bff-auth-oidc-first-argon2id-fallback.md) / [ADR-025](../adr/ADR-025-measurement-product-facade.md) |
| 狀態 | Planned（2026-06-18） |
| 前置 | Wave 1（`a19fb07`）+ Wave 2（`f732441`）已合併 dev；本地 `dev` @ `fd57211`（= `origin/dev` `0d45de7` + R-017 風險 doc，未推送）|
| 分支 | `dev`（owner-commits；每批 TDD + 合併前 code-review agent）|

> 記錄文件，不重述 spec；衝突以 PRD-0005（**Approved，鎖定** — 變更走 ADR）為準。

## Wave 對應關係

PRD-0005 的上線分期為 **P1 = FR-500~513（設備管理 + 人工確認工作流）**、**P2 = FR-520~521（量測呈現）**。Phase-1 採 **wave-based by dir-ownership** 推進：

- Wave 1（`a19fb07`）：BFF FR-50x proxy + 量測 facade（ADR-025）；前端 product-UI core slice（list/detail/queue/review，mock）。
- Wave 2（`f732441`）：前端 live BFF 接線 + 本地登入 + auth route-guard；OIDC Authorization-Code+PKCE provider（ADR-024）。
- **Wave 3（本計畫）**：收尾 P1 的 FR-502 / FR-513 UI + P2 的 FR-520/521 UI + OIDC 前端登入按鈕。

## 現況基線（Wave 3 起頭已在途）

**S1 已提交 @`4442ff2`**（`feat(frontend): mock client mutating surface for FR-502/513/520-521`）：mock client（P1 唯一資料源）補齊 `createDevice` / `updateDevice`（FR-502）、`createCorrection`（FR-513）、`listDeviceMeasurements(order)` + 24 點電力日線序列（FR-520/521）的樂觀回傳，純函數 `orderMeasurements` / `newDeviceFromCreate`、immutable、深拷貝、對齊 ADR-025 facade 語義。本地 `dev` 因此 ahead 3（`fd57211` + `4442ff2` S1 + `1850a60` deep-clone fix，未推送）。

**提交前兩輪 code-review（皆已修）**：
- 第一輪：`npm run build`（tsc -b）紅燈 —— vitest 只轉譯、**不做 typecheck**，故 vitest passed ≠ build 綠。3 個 TS error（型別源自 openapi 生成、單一真相）：`CorrectionCreate` 缺必填 `demote_to_candidate`、`CorrectionOut` 缺必填 `is_active`；另 P2 `createCorrection` 硬寫 `corrected_signals: null` 遺失輸入。已修並補 assertion。
- 第二輪：P2 `corrected_signals` 雖回傳輸入但**未深拷貝**（與輸入共用 reference，違 immutability）→ 改 `clone(body.corrected_signals)` 並補 `not.toBe` reference 斷言；HIGH `updateDevice` `as Partial<DeviceOut>` 寬鬆 cast → 改 DeviceUpdate 契約欄位投影（保 mock↔live 對稱）；MEDIUM `createCorrection` `id:1` 撞 React key → closure 計數器。
- 修後驗證：**`npm run build` 綠 + 209 vitest passed + `npm audit --omit=dev`（prod）= 0**。⚠️ 完整 `npm audit` 仍有 **3 項 dev-only findings（1 low + 2 moderate，`@redocly/openapi-core` openapi 工具鏈）**，由 **R-016** 追蹤（prod 乾淨）。

## 後端就緒度盤點（決定每 FR 是純前端還是要補後端）

| FR | device-service 本體 | BFF proxy | 前端 client | 結論 |
|----|:---:|:---:|:---:|------|
| FR-513 Correction | ✅ `POST /{id}/ai-feedback` | ✅ `POST /api/devices/{id}/corrections` | ✅ live + mock | **純前端**（做表單）|
| FR-520/521 量測 | ✅ PostgREST 量測面 | ✅ `GET /api/devices/{id}/measurements`（ADR-025）| ✅ live + mock | **純前端**（做頁面；`MeasurementCard`/`PowerTrendChart` 元件已存在）|
| OIDC 登入鈕 | — | ✅ `GET /api/auth/oidc/login`（ADR-024）| authApi 尚無 oidc 方法 | **純前端**（加按鈕 → full-page redirect）|
| FR-502 建立/編輯 | ✅ `POST /devices`、`PATCH /{id}` | ❌ **BFF 缺 create/update 路由** | ✅ live 已對映（接不住）| **補 BFF 兩條 proxy（ADR-026）+ 前端表單**|
| FR-502 停用 | ✅ `reject` | ✅ `POST /api/devices/{id}/reject` | ✅ | 純前端（重用 reject）|

**唯一後端缺口** = BFF 缺 `POST /api/devices` 與 `PATCH /api/devices/{id}`，已由 ADR-026 決議補上（鏡像既有 mutating pattern；不暴露 hard DELETE，停用 = reject）。

## 實作步驟

> 每步動工前依 `project_rules.md §14` 讀對應 PRD/ADR；§9 流程（測試先 RED→GREEN→regression check→四文件同步→commit）；測試在 throwaway 容器 / vitest 跑。覆蓋率：前端 vitest ≥ 80%、BFF endpoint ≥ 80%（§10）。

### S1 — ✅ DONE（`4442ff2`）收斂 WIP 為 Wave 3 起點 commit（dir: `frontend/src/api`）
- 觸發 PRD/ADR：PRD-0005 §8.2、ADR-025。
- 動作：提交現有 mock-client 層為 `feat(frontend): mock client mutating surface for FR-502/513/520-521 (PRD-0005 Wave 3)`。
- **綠燈門檻（全部必過，非僅 vitest）**：`npm run build`（tsc -b typecheck）+ 全 vitest 套件（**209 passed**）+ `npm audit --omit=dev`（prod = 0；完整 audit 3 項 dev-only，R-016）。⚠️ vitest 只轉譯不 typecheck，build 必須一起過（兩輪 review 即因此抓到 TS error + immutability/cast 問題，已修）。已於 `4442ff2` 提交（僅 3 個 frontend 檔；doc 維持未追蹤交 owner review）。

### S2 — FR-520/521 量測視覺化（dir: `frontend`，純前端）
- 觸發 PRD/ADR：FR-520（即時卡片，取最新點）/ FR-521（歷史曲線，整段序列）、ADR-025、§9.3。
- RED：`DeviceDetailPage` 測試斷言 — 即時卡片以 `order=desc` 取最新點、歷史曲線以 `order=asc` 取整段；空序列 fallback。
- GREEN：把既有 `MeasurementCard` + `PowerTrendChart`（目前僅在 `GalleryPage` 展示）接入 `DeviceDetailPage`，資料走 `listDeviceMeasurements`；即時機制 P2 預設輪詢（§14 Q3）。
- 檔案：`frontend/src/pages/DeviceDetailPage.tsx`（+ 測試）。

### S3 — FR-513 Correction 表單（dir: `frontend`，純前端）
- 觸發 PRD/ADR：FR-513、§7.3a（驗證在後端，前端做即時提示）、§9.4（CSRF）、§9.5（XSS — 純文字渲染）。
- RED：Correction 表單元件測試 — `verdict` / `corrected_device_type` / `human_explanation` 必填與即時提示；送出呼叫 `createCorrection`；human_explanation 純文字渲染（無 innerHTML）。
- GREEN：新增 Correction 表單元件，掛入 `ReviewPage`（或 DeviceDetail）；後端違規（400/422）回穿顯示。
- 檔案：`frontend/src/components/ems/CorrectionForm.tsx`（+ 測試）、`ReviewPage.tsx` 接線。

### S4 — FR-502 BFF create/update proxy 補洞（dir: `services/bff`，**後端**，可與 S2/S3 平行）
- 觸發 PRD/ADR：§2（新增 API）、§15（新增 FastAPI endpoint → unit + integration）、**ADR-026**、ADR-023。
- **前置 gate（review P3）**：ADR-026 已由 owner **Accepted（2026-06-18）**，gate 解除，S4 endpoint 可合併。S5 的 mock 表單可先做，live 接線等 S4 合併。
- RED：`services/bff/tests/` 加 — `POST /api/devices`、`PATCH /api/devices/{id}` 的 integration：無 Origin → 403；非 JSON object body → 422；`PATCH` 非法 device_id → 422（FR-322）；OPS key 注入轉發；上游 4xx（409 duplicate / 404 unknown）回穿；非 OPS role → 對應錯誤。
- GREEN：`routes/devices.py` 仿 `override_device` 加兩條 `forward()`（`POST ""` / `PATCH "/{device_id}"`，`_json_body` verbatim 轉發、OPS-gated、CSRF middleware 自動覆蓋）；更新該檔頭 §8.1 surface 清單。
- 文件：`api/openapi.yml` 補 BFF facade 兩路由 + 四文件同步（§3）。

### S5 — FR-502 設備建立/編輯表單（dir: `frontend`；mock 先可開發，live 需 S4）
- 觸發 PRD/ADR：FR-502、§9.1（前端不持 key，經 BFF 注入通道）、ADR-026、ADR-010（狀態機 — 新設備候選態）。
- RED：表單測試 — 建立 → `createDevice`（候選態顯示）、編輯 → `updateDevice`、停用 → `rejectDevice`；必填驗證即時提示。
- GREEN：新增 `DeviceFormPage` / 表單元件 + 路由（如 `/devices/new`、`/devices/:deviceId/edit`，新增至 `app/routes.ts` 單一真相）。
- 檔案：`frontend/src/pages/DeviceFormPage.tsx`、`app/routes.ts`、`app/router.tsx`（+ 測試）。

### S6 — OIDC 前端登入按鈕（dir: `frontend`，純前端，最小）
- 觸發 PRD/ADR：FR-50x 認證、ADR-024。
- RED：`LoginPage` 測試 — 「OIDC 登入」按鈕觸發導向 `/api/auth/oidc/login`（**full-page redirect，非 fetch**；OIDC 走瀏覽器跳轉）。
- GREEN：`LoginPage.tsx` 加按鈕；更新 `LoginPage.tsx:9` 的「Wave 3 不在本批」陳述。
- 檔案：`frontend/src/pages/LoginPage.tsx`（+ 測試）；i18n 文案 `i18n/zh-Hant.ts`。

### S7 — Wave 3 收尾
- 四文件同步總檢（§3）；`requirements-inventory.md`（若動 npm / 套件，§18）；PR checklist（§16）全勾；覆蓋率達 §10 下限；regression：前端全 vitest + BFF 全測試綠。

## 平行化（wave-based by dir-ownership）

- **Track A（frontend owner）**：S1 → S2 → S3 → S6 →（待 S4 完成解鎖 live）S5。彼此檔案不衝突，可連續做。
- **Track B（bff owner）**：S4 獨立，與 Track A 平行；完成後解鎖 S5 的 live 接線。
- 兩 track 各自 commit；S7 合流做文件同步與 PR。

## 已決議的決策點（owner 2026-06-18 拍板）

1. **S4 開新 ADR**：採 **ADR-026**（BFF create/update facade），非僅掛 ADR-025 延伸。**已 Accepted（2026-06-18）**，S4 合併 gate 解除。
2. **手動 create 保留為 FR-502 範圍**：理由 = 自動發現（PRD-0003）出錯 / 漏建時的人工兜底（owner 原話「如果自動發現出錯呢？」）。故 FR-502 完整 create / edit / disable 入列，停用 = reject、不做 hard DELETE。
3. **本計畫落成 repo 文件**（本檔），未提交交 owner review。

## 風險 / 待續

- R（沿用 R-016）：完整 `npm audit` 有 3 項 dev-only findings（1 low + 2 moderate，`@redocly/openapi-core` openapi 工具鏈）；prod（`npm audit --omit=dev`）clean。本批若動前端套件須複查。
- 自動發現 vs 手動 create 的 reconciliation 語意歸 device-service / PRD-0003 狀態機；BFF 僅回穿（ADR-026 已記）。
- OIDC 真實 IdP 需 issuer / client 設於 env（現實作對 mock JWKS 驗證）；S6 僅做前端按鈕，不含真 IdP 上線驗證。

## 流程（不變）
每批 TDD + 合併前 code-review agent；計畫 / 決策落 repo 記錄；測試在 throwaway 容器（後端）/ vitest（前端）跑。

## 覆蓋率 / 測試的保守表述（沿用）
所報覆蓋數字為本機 / 容器 pytest-cov 與 vitest 量測，**非 CI / production 全面保證**；整合測試在 DB / mosquitto / device-service 不可達時會 skip。
