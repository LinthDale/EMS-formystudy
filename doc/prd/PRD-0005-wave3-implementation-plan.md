# PRD-0005 Phase-1 Wave 3 實作計畫 — 設備 CRUD / Correction / 量測視覺化 / OIDC 登入 + 設計系統 v2（主題 + GSAP）

| 欄位 | 內容 |
|------|------|
| 對應 PRD | [PRD-0005](PRD-0005-ems-frontend.md) §6（FR-502/513/520/521）/ §8.1 / §8.2 / §9.1 / §9.3 / §9.4 / §9.5 |
| 新增 / 影響 ADR | **[ADR-026](../adr/ADR-026-bff-device-create-update-facade.md)（Accepted — BFF create/update facade）**；**規劃中：ADR-027（GSAP 動畫庫，取代 §6.4 Motion for React，待寫）+ ADR-028（使用者可切換多主題 token 架構，待寫）**（設計系統 v2）；沿用 [ADR-023](../adr/ADR-023-bff-session-and-role-channel-key-authz.md) / [ADR-024](../adr/ADR-024-bff-auth-oidc-first-argon2id-fallback.md) / [ADR-025](../adr/ADR-025-measurement-product-facade.md) |
| 狀態 | Planned（2026-06-18）；設計系統 v2 方向 owner 加入 2026-06-22 |
| 前置 | Wave 1（`a19fb07`）+ Wave 2（`f732441`）已合併 dev；**`dev` 已推送，= `origin/dev` @ `fd77664`**（R-017 `fd57211` + S1 `4442ff2` + deep-clone `1850a60` + Wave3 docs `fd77664`）|
| 分支 | `dev`（owner-commits；每批 TDD + 合併前 code-review agent）|

> 記錄文件，不重述 spec；衝突以 PRD-0005（**Approved，鎖定** — 變更走 ADR）為準。

## Wave 對應關係

PRD-0005 的上線分期為 **P1 = FR-500~513（設備管理 + 人工確認工作流）**、**P2 = FR-520~521（量測呈現）**。Phase-1 採 **wave-based by dir-ownership** 推進：

- Wave 1（`a19fb07`）：BFF FR-50x proxy + 量測 facade（ADR-025）；前端 product-UI core slice（list/detail/queue/review，mock）。
- Wave 2（`f732441`）：前端 live BFF 接線 + 本地登入 + auth route-guard；OIDC Authorization-Code+PKCE provider（ADR-024）。
- **Wave 3（本計畫）**：收尾 P1 的 FR-502 / FR-513 UI + P2 的 FR-520/521 UI + OIDC 前端登入按鈕；**並納入設計系統 v2（owner 2026-06-22 授權動 §6.4）：S-DS-a 可切換主題為地基級、排在 UI 前；S-DS-b GSAP 動畫與功能線平行 / 延後，不阻塞 FR 功能。**

## 現況基線（Wave 3 起頭已在途）

**S1 已提交 @`4442ff2`**（`feat(frontend): mock client mutating surface for FR-502/513/520-521`）：mock client（P1 唯一資料源）補齊 `createDevice` / `updateDevice`（FR-502）、`createCorrection`（FR-513）、`listDeviceMeasurements(order)` + 24 點電力日線序列（FR-520/521）的樂觀回傳，純函數 `orderMeasurements` / `newDeviceFromCreate`、immutable、深拷貝、對齊 ADR-025 facade 語義。（已推送：`dev` == `origin/dev` @ `fd77664` = `fd57211` R-017 + `4442ff2` S1 + `1850a60` deep-clone + `fd77664` Wave3 docs）。

**提交前兩輪 code-review（皆已修）**：
- 第一輪：`npm run build`（tsc -b）紅燈 —— vitest 只轉譯、**不做 typecheck**，故 vitest passed ≠ build 綠。3 個 TS error（型別源自 openapi 生成、單一真相）：`CorrectionCreate` 缺必填 `demote_to_candidate`、`CorrectionOut` 缺必填 `is_active`；另 P2 `createCorrection` 硬寫 `corrected_signals: null` 遺失輸入。已修並補 assertion。
- 第二輪：P2 `corrected_signals` 雖回傳輸入但**未深拷貝**（與輸入共用 reference，違 immutability）→ 改 `clone(body.corrected_signals)` 並補 `not.toBe` reference 斷言；HIGH `updateDevice` `as Partial<DeviceOut>` 寬鬆 cast → 改 DeviceUpdate 契約欄位投影（保 mock↔live 對稱）；MEDIUM `createCorrection` `id:1` 撞 React key → closure 計數器。
- 修後驗證：**`npm run build` 綠 + 209 vitest passed + `npm audit --omit=dev`（prod）= 0**。⚠️ 完整 `npm audit` 仍有 **3 項 dev-only findings（1 low + 2 moderate，`@redocly/openapi-core` openapi 工具鏈）**，由 **R-016** 追蹤（prod 乾淨）。

## 設計系統 v2 方向（owner 2026-06-22）

owner 以 GreenSock 官方 agent-skill 包 [`greensock/gsap-skills`](https://github.com/greensock/gsap-skills)（**該 skill 包為 MIT**；8 個 GSAP 技能）為參考，決定設計系統升級兩件事，且**授權動 PRD-0005 §6.4**（Approved PRD → 走 ADR）：

> ⚠️ **授權釐清（review P1）**：`gsap-skills` 本身為 MIT；但 **GSAP 函式庫本體採 GreenSock / Webflow Standard License**（免費、可商用、含全部 plugin），**並非 MIT / OSI 開源授權**。故對 ADR-001「開源優先」而言，GSAP 屬**明列例外**（免費可商用但非 OSI）——**ADR-027 必須明確記錄此授權例外與採用理由**，不得僅以「100% 免費」帶過視為開源合規。

1. **動畫庫改採 GSAP**（§6.4 **原定（且從未安裝）**的「Motion for React」→ 改選；故 ADR-027 為「**變更原定選型**」，非替換既有 runtime）。理由：EMS 動效本質為「數值 / 狀態 / 圖表」驅動（即時量測滾動、狀態徽章 Flip、圖表 refresh、儀表板進場），正是 GSAP timeline 主場；搭 `@gsap/react` 的 `useGSAP`（自動 cleanup、scope、reduced-motion）。
2. **配色做成使用者可切換主題**（不只選一個定稿）。沿用既有 FontSwitcher 模式：tokens.css 仍是唯一視覺真相、切換只設 `data-ems-theme` 屬性。內建四主題：**石墨電力青（預設）/ 暖琥珀工業 / 藍綠儀表 / 晝間淺色（首個 light mode）**。

**主題切換骨架已 prototype（owner 2026-06-22 透過 dev-mock 旁路看過 running、`目前可以`）**：
- 新增 `styles/themes.ts`（主題註冊表）、`lib/theme-preference.ts`（切換 / 持久化 / 邊界驗證，鏡像 font-preference）、`components/ems/ThemeSwitcher.tsx`、`lib/__tests__/theme-preference.test.ts`（9 tests）。
- `tokens.css` 加 3 個 `:root[data-ems-theme="amber|teal|light"]` 覆寫區塊（graphite = 基準 :root）；`test/parse-tokens.ts` + `tokens.test.ts` 升級為「基準區塊單一真相 + 主題只覆寫不引入新 token」契約。
- `main.tsx` 啟動還原、`AppShell` + `LoginPage` 置入切換器、i18n 詞條。
- `App.tsx` 加 **dev-only mock 旁路**（`?mock`、`import.meta.env.DEV` 夾死、prod tree-shake；prod bundle 經查無 `ems.devMock` / `dev-ops` / mock client 殘留），讓無後端時能逛全部頁審視主題（設計審視工具，定稿時決定保留或移除）。
- **review 修正（2026-06-22）已套用**：WCAG 對比 gate（`contrast.test.ts` 36 tests，四主題 text/bg ≥ 4.5:1；各主題 muted 改深至過標）；`color-scheme: dark|light`（瀏覽器原生控制項配色）；**registry ↔ tokens.css 漂移契約**（`tokens.test.ts` +2：每 registry id 有 CSS 區塊且覆寫必要 semantic tokens、無孤兒 CSS 區塊）；主題名稱改 **i18n labelKey**（文字集中 `zh-Hant.ts`）。
- 驗證：`npm run build` 綠、**257 tests passed**、coverage lines 97% / branches 87.47% / `npm audit --omit=dev`（prod）= 0。**仍為未提交 WIP（受下方提交 gate 約束）。**

**尚未做（待定稿 / 實作）**：GSAP 動畫層本身（app 內尚無 GSAP，只在預覽 widget demo 過）；ECharts 切主題重上色；ADR-027 / ADR-028；§6.4 改寫；deps `gsap`+`@gsap/react`。詳見下方步驟 **S-DS**。

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

### S-DS — 設計系統 v2（dir: `frontend`；owner 2026-06-22 加入）
> 改 §6.4 → 走 **ADR-027（GSAP）/ ADR-028（多主題）**。**S-DS-a 主題系統為地基級、排在 UI 步驟之前；S-DS-b GSAP 不是 FR-502/513/520/521 的必要條件，與功能線平行或延後，不得阻塞 S2/S3。**
>
> **🚧 提交順序 gate（review P1，硬性）**：**ADR-027/028 Accepted 前不得合併 S-DS。** 固定順序：(1) ADR-027/028 寫好 + owner Accept → (2) 更新 PRD §6.4 → (3) 才提交主題實作（GSAP 隨後）。在此之前主題骨架維持未提交 WIP。

**S-DS-a 可切換主題（🟡 已 prototype + review 修正，待 ADR/§6.4 後提交）**
- 觸發 PRD/ADR：§6.4、**ADR-028（待寫）**、FR-532（a11y / 淺色對比）。
- 已完成（WIP，build 綠 + 257 tests）：themes 註冊表（i18n labelKey）+ theme-preference + ThemeSwitcher + tokens.css 四主題（含 `color-scheme`）+ parse-tokens/tokens.test 多主題契約 + **registry↔CSS 漂移契約** + **WCAG 對比 gate（36 tests）** + dev-mock 旁路（見上節）。
- ✅ review 修正（2026-06-22）：WCAG muted 全主題改深過標 + 可執行對比 gate；`color-scheme` dark/light；registry 漂移契約；i18n labelKey。
- 待補：**ECharts 切主題重上色**（`charts/theme.ts` 於切換時重讀 token → `registerEmsChartsTheme` → 圖表 re-render；目前需重整頁面才套色）；**ADR-028 定稿 + §6.4 改寫**（提交前置）。
- 收尾：依上方 gate 順序 commit（frontend 檔；doc 交 owner）。

**S-DS-b GSAP 動畫層（❌ 尚未做；與功能線平行 / 延後，不阻塞 S2/S3）**
- 觸發 PRD/ADR：§6.4、**ADR-027（待寫）**。
- deps：`gsap` + `@gsap/react`；`package.json` + `requirements-inventory.md`（§18）；安裝 `npx skills add greensock/gsap-skills`（往後 agent 照 GSAP 正確 pattern）。
- RED→GREEN：建 `lib/motion/` 集中（useGSAP-based hooks：`useCountUp` / `useStaggerReveal` / `useFlipState`，duration/easing 引用 motion token）；護欄：transform/autoAlpha only、`prefers-reduced-motion` 強制、useGSAP scope+cleanup。先在 S2 量測視覺化試點（即時數字滾動 + 卡片進場）。
- 動效範圍沿用 §6.4「限定 6 類」精神；是否讓動效個性隨主題變列為後續選項。

### S2 — FR-520/521 量測視覺化（dir: `frontend`，純前端；接 S-DS-b 的 GSAP 試點）
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

- **Track A（frontend owner）**：S1 → **S-DS-a（主題地基；ADR-028 Accepted + §6.4 後提交）** → S2 → S3 → S6 →（待 S4 完成解鎖 live）S5。**S-DS-b（GSAP）與功能線平行 / 延後，不阻塞 S2/S3**（可於 S2 量測視覺化試點）。
- **Track B（bff owner）**：S4 獨立，與 Track A 平行；完成後解鎖 S5 的 live 接線。
- 兩 track 各自 commit；S7 合流做文件同步與 PR。

## 已決議的決策點（owner 2026-06-18 拍板）

1. **S4 開新 ADR**：採 **ADR-026**（BFF create/update facade），非僅掛 ADR-025 延伸。**已 Accepted（2026-06-18）**，S4 合併 gate 解除。
2. **手動 create 保留為 FR-502 範圍**：理由 = 自動發現（PRD-0003）出錯 / 漏建時的人工兜底（owner 原話「如果自動發現出錯呢？」）。故 FR-502 完整 create / edit / disable 入列，停用 = reject、不做 hard DELETE。
3. **本計畫落成 repo 文件**（本檔），未提交交 owner review。
4. **（2026-06-22）動畫庫採 GSAP**：§6.4 **原定（從未安裝）**的 Motion for React → 改選（ADR-027 為「變更原定選型」，非替換既有 runtime）；`gsap-skills`（MIT）為 agent 指引、`@gsap/react` useGSAP 為標準。**GSAP 本體 = GreenSock/Webflow Standard License（免費可商用、非 OSI）→ ADR-001 明列例外，ADR-027 須記錄。** 走 **ADR-027**。
5. **（2026-06-22）配色做成使用者可切換主題**：內建四主題（石墨預設 / 琥珀 / 藍綠 / 淺色），沿用 FontSwitcher 模式、tokens.css 單一真相。走 **ADR-028**。owner 已看 prototype running、認可（`目前可以`）。
6. **（2026-06-22）授權動 §6.4**：上兩項屬 Approved PRD 的視覺方向變更，以 ADR-027/028 記錄並改寫 §6.4 對應段。
7. **（2026-06-22，review P1）提交順序 gate（硬性）**：**ADR-027/028 Accepted + §6.4 更新前，不得合併 S-DS**；主題骨架維持未提交 WIP。順序：ADR Accept → §6.4 → 提交主題（+ GSAP）。

## 風險 / 待續

- R（沿用 R-016）：完整 `npm audit` 有 3 項 dev-only findings（1 low + 2 moderate，`@redocly/openapi-core` openapi 工具鏈）；prod（`npm audit --omit=dev`）clean。本批若動前端套件須複查。
- **（S-DS-a）ECharts 切主題重上色**：`charts/theme.ts` 註冊時讀 computed token，切主題後已畫圖表不自動更新 → 需重讀 token + 重註冊 + re-render（現需重整頁面）。ADR-028 處理。
- **（S-DS-b）GSAP / 動效節制**：須強制 `prefers-reduced-motion`、transform/autoAlpha only、useGSAP scope+cleanup，避免過度動畫與效能 / a11y 退化。
- **（S-DS）dev-mock 旁路**（`App.tsx` `?mock`）為設計審視工具、`import.meta.env.DEV` 夾死、prod tree-shake；定稿時決定保留或移除。
- 自動發現 vs 手動 create 的 reconciliation 語意歸 device-service / PRD-0003 狀態機；BFF 僅回穿（ADR-026 已記）。
- OIDC 真實 IdP 需 issuer / client 設於 env（現實作對 mock JWKS 驗證）；S6 僅做前端按鈕，不含真 IdP 上線驗證。

## 流程（不變）
每批 TDD + 合併前 code-review agent；計畫 / 決策落 repo 記錄；測試在 throwaway 容器（後端）/ vitest（前端）跑。

## 覆蓋率 / 測試的保守表述（沿用）
所報覆蓋數字為本機 / 容器 pytest-cov 與 vitest 量測，**非 CI / production 全面保證**；整合測試在 DB / mosquitto / device-service 不可達時會 skip。
