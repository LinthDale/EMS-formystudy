# EMS 本機執行、DGX-01 公開入口

狀態：2026-09-23 已上線，正式網址已以真實本機後端驗證。

- 即時監控與歷史：https://synaiq-ai.com/ems/#Monitor
- 能源總覽（示意資料）：https://synaiq-ai.com/ems/#Main
- 原本本機預覽仍在：http://127.0.0.1:4178/#Monitor
- 本機發布檢查入口：http://127.0.0.1:4179/ems/#Monitor

資料留在本機 WSL EMS 專案與既有 Docker volumes，DGX-01 只轉送，不存放 EMS 資料庫、密碼或應用程式。電腦關機、休眠、Tailscale 中斷或 EMS 程序關閉時，公開 EMS 網址會無法使用；Solar 與主站的路由保持獨立。

## 啟動 / 停止

目前發布服務已在背景執行。未新增自動登入、排程工作或開機啟動項目。Windows 重開機後，先啟動既有 WSL Docker EMS 服務與 Tailscale，再執行 `start-public.ps1`。

PowerShell 7 執行（UNC 檔案的執行政策可能要求本次 process 使用 Bypass，不修改系統政策）：

```powershell
& 'C:\Users\User\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\powershell\pwsh.exe' -NoProfile -ExecutionPolicy Bypass -File '\\wsl.localhost\Ubuntu\home\dalelin\synaiq\EMS\output\ems-public-local\start-public.ps1'
```

停止公開轉送服務時，將命令最後的檔案改成 `stop-public.ps1`。只停止本次 Node 發布程序，保留既有後端與 4178 預覽。日誌為同目錄 `server.stdout.log` / `server.stderr.log`；PID 記於 `server.pid`，腳本會檢查命令列，避免誤停重用 PID 的其他程序。

## 登入

使用 `demo`（已依使用者要求更換；舊 `local-ops` 已停用）。密碼保留於 repo 根目錄 `.local/ems-preview-login.json`，沒有放到 public、發布包、DGX 或網址中。其他使用者未登入會收到 API 401。此階段所有設備讀值仍是本機模擬器採集資料，非現場硬體。

## 部署結構

`瀏覽器 HTTPS /ems/ → DGX-01 Nginx → Tailscale 100.114.126.85:4179 → 本機 Node → 127.0.0.1:8003 BFF → 原有 EMS 服務`

發布程序只綁 `100.114.126.85` 與 `127.0.0.1`，只接受 DGX-01 `100.64.84.58` / 本機 loopback 的連線。沒有增加 Windows 防火牆規則，也沒有將資料庫、MQTT、設備管理端點加入公開代理。

`server-config.json` 指向 `releases/20260929-delta-monitor-v1`。公開靜態檔案與 API 均保留 `/ems/` 前綴。API 僅允許 session、登入/登出、設備清單/單筆、量測/歷史/紀錄讀取，以及精確 GET/POST /api/alarms/demo，其餘回 404。寫入設備的 API 不在代理清單中。

- 每個來源 IP 每分鐘 API 最多 120 次、登入最多 5 次。
- 同時最多 4 個 API 請求，BFF 代理逾時 15 秒。
- PostgREST 的 authenticator 登入角色在 `ems` 資料庫設定 statement_timeout=12s；已重啟 query 套用。修改前沒有角色/資料庫設定，上限為 0。
- Cookie 限 `/ems/`，保留 Secure、HttpOnly、SameSite=Strict，登入與登出均實测。
- BFF Origin 白名單追加 `https://synaiq-ai.com` 與 `http://127.0.0.1:4179`；其他設定保留。變更前私有備份在 `.local/env-before-public-ems-20260923`。
- CSP 允許同源 iframe 和已編譯腳本，不允許 unsafe-eval / inline script；Google 字型的樣式與字型來源分別列白名單。
- 固定設計 Component 在 build 階段轉為外部 JS；樣板包在 inert template 內，動態程式匯入停用。4178 使用原始模板執行，發布包另行編譯。

## 新版本

以 Node 執行 `build.mjs <new-release-id>`，只接受英數與連字號，已存在的 release 會拒絕覆寫。輸入來源仍是 `../ems-design-preview-20260923/public`。每版附 `manifest.json`（檔案數、位元組、SHA256）。

更新 `server-config.json` 的 release 前，先以隔離本機 port 驗證新包，再停止/啟動發布程序套用。這次的 20260923-local-v1 已通過正式 URL 驗证；不可在服務運行中直接改動該版本檔案。

## DGX 路由與回復

唯一變更的遠端設定：
`/home/nick/projects/YIYI-Global-Gateway/config/nginx/conf.d/synaiq-ai.com.conf`

新增範圍由 `# BEGIN EMS LOCAL 20260923` / `# END EMS LOCAL 20260923` 標記。`/ems` 轉址 `/ems/`，`/ems/` 代理到 `http://100.114.126.85:4179`（proxy_pass 沒有尾斜線，保留前綴）。已先 `nginx -t` 成功，再 reload；其他原有內容全部保留。

本次備份：
`/home/nick/projects/YIYI-Global-Gateway/config/nginx/backup/ems/synaiq-ai.com.conf.before-ems-20260923-134125`

- 修改前 SHA256：`34981be6a18a548dbc23add60178084528b0bc0563f54aa90d17fd021133d8e6`
- 修改後 SHA256：`6919bec9bcc7fadd930b0d7df241af977028bb3e8d4adc985eab0e4d8474dd54`

回復時先核對是否有同期更動。若有，僅移除 EMS 標記區塊；沒有時才可使用上述備份。`docker exec dgx-gateway-nginx nginx -t` 通過後執行 `docker exec dgx-gateway-nginx nginx -s reload`。不能對整個 gateway Compose 執行 down。

如需撤回資料庫查詢上限，且沒有後續修改，可使用 postgres 執行 `ALTER ROLE authenticator IN DATABASE ems RESET statement_timeout;`，再 restart `ems-query`。不需要改表或刪資料。

## 驗收紀錄

- 主站、Solar、EMS 首頁均為 HTTPS 200；Solar `/api/me` 與 EMS 未登入 API 維持 401。
- `qa/history-public.cjs`：真實登入；量測時間 13:41:52 → 13:41:58；sim/plc/sensor 的 4/6/2 張圖表；24h/7d、自訂空時段、歷史第 2 頁、100 筆 CSV、390px 手機版面全部通過，無 pageerror。
- `qa/boards-public.cjs`：六個示意頁全部渲染，無 console error 與 CSP 錯誤。已人工檢視 Main 與 Monitor 完整畫面。
- `qa/public-security.cjs`：未登入 401、非法來源 403、非白名單 API / 私有檔案 404、正確 Cookie 屬性與登出清除、非 gateway Tailnet 來源拒絕均通過。
- 注意 `..` 若被瀏覽器正規化到 `/ems/` 以外，會到原主站 SPA fallback；該主站 200 HTML 不是 EMS 檔案外洩。本次不改主站 fallback。

限制：目前是本機發布試用環境，沒有高可用、自動開機啟動或完整長時間/多用戶壓力驗收。六個管理/總覽畫面仍為示意，即時監控/歷史頁讀取後端；v7 新增的 Telegram DEMO 面板亦連接後端，既有警報清單仍為示意。

## 2026-09-23：移除預覽外框、更新展示帳號

此步驟當時發布版本 `20260923-local-v3`（前版 v1 保留，v2 為未上線中間建置）。已移除上方「設計預覽」工具列、畫面/縮放/情境控制和底部修訂文字，使用 EMS 內部側欄切換。示意頁原有資料來源標示保留；即時監控仍接後端。

本機 4178 與公開 /ems/ 都已更新。父頁使用 hash 記錄導覽，iframe 使用 location.replace，避免 iframe 額外 history 干擾上一頁。直接 /#Monitor 與重新整理、390px 監控版面均已驗證。

登入更新為 demo，密碼依使用者指定，未寫入本文件。BFF 使用 Argon2id 雜湊；舊 local-ops 從使用者表移除，重啟 BFF 清除原有 session。私有回復資料位於 `.local/env-before-demo-login-20260923` 與 `.local/ems-preview-login.before-demo.json`。發布檔案掃描確認不含新密碼。

驗證：`qa/app-shell.cjs`（本機/正式網址側欄、上一頁、監控直接載入、手機）、`qa/account-change.cjs`（兩個入口新帳號成功、舊帳號拒絕、登出與密碼掃描）、`qa/history-public.cjs`（以 demo 登入的圖表/歷史/CSV）。未登入的 session API 401 為預期行為，不視為頁面錯誤。demo 的正式量測時間由 14:01:39 前進至 14:01:44。

回復畫面版本時可將 server-config.json 的 release 指回 v1，再執行 stop-public/start-public。帳號配置獨立於畫面發布，不隨畫面回復；不應自行重新啟用已停用的 local-ops。

## 2026-09-23：全站響應式版面修正

此 RWD 階段發布版本為 `20260923-local-v6`。來源為 `output/ems-design-preview-20260923/public`；`responsive.css` 統一六頁的流式主內容、卡片排列、手機橫向導覽和可獨立滑動的資料表。`preview.js` 移除整頁固定 1440px 縮放；ResizeObserver 依內容高度調整 iframe，四組示意圖表依卡片寬度重算圖形、刻度及提示。即時監控也取消 1700px 內容上限。

能源流與運轉模式依容器寬度排列；設備 AI 建議窄卡片改為直排，按鈕可換行。手機需量頁的最高值標示移至圖下方，時間電價各區間以完整文字顯示。示意資料標籤保留，未將示意數字偽裝為後端數據。

驗證：
- 正式 URL 六頁在 1920、1366、1024、768、390px 均使用完整視窗寬度，沒有整頁橫向溢出，無 JavaScript 例外；另在來源檢查 320 到 2560px 及各斷點附近尺寸。
- `qa/app-shell.cjs`：正式站六頁導覽、上一頁、直接載入與重新整理 Monitor、手機通過。
- `qa/responsive-interaction.cjs`：實際調整視窗後圖表重畫，日報選擇保留，hover 資料完整可見。
- `qa/history-public.cjs`：demo 登入，量測時間 14:30:48 → 14:30:54；sim/plc/sensor 的 4/6/2 圖表、24h/7d、自訂空時段、歷史分頁、100 筆 CSV、手機均通過。
- v6 在 v5 完整驗證後僅補上 Demand 手機標籤和時段排版；`qa/demand-rwd.cjs` 在來源、隔離本機發布埠及正式 URL 的 320/390/650/1366px 通過。Monitor 程式與 v5 完全相同。
- `qa/verify-release.mjs`：正式 URL 所有 31 個發布檔案的 SHA256 與 v6 manifest 一致。

v3 為此次 RWD 修改前版本；v4 為未上線中間建置，v5 保留首次 RWD 上線版。`server-config.before-v5.json` 指向 v3；需要回復畫面時可將 release 指回 v3 並 stop/start 發布程序。帳號與後端不隨版面回復。隔離 QA 的 4181 程序驗證後已停止；4178 和正式 4179 保持執行。
## 2026-09-23：Telegram 示範警報（v7，已上線）

入口：https://synaiq-ai.com/ems/#Alarms 與 http://127.0.0.1:4178/#Alarms 。警報中心上方新增「觸發警報」、同頁登入、發送狀態及最近十筆成功紀錄；沿用 demo 帳號。BFF 重建使舊 session 失效，需重新登入。只有新通知面板會實際發送，原有設備警報清單仍是示意。

- 正式 release：`20260923-local-v7`，33 個檔案 SHA256 全數吻合；只變更 Alarms 模板及新增 alarm-demo.mjs/css。前版 v6 保留。
- 新 BFF：OPS + Origin + UUID4-only；固定既有 Bot/私人對象與 DEMO 文字，30 秒全域冷卻、10 分鐘去重，無自動重送。最近紀錄為單程序記憶體，重啟清空。
- RED→GREEN：BFF 全部 196 tests 通過，新增 module/routes coverage 94%。併發同 UUID、不同 UUID 只呼叫外部一次；未登入/錯誤角色/CSRF/任意目的地/timeout/失敗/金鑰遮蔽均驗證。
- `qa/alarm-demo.cjs`：來源與隔離編譯版的 mock E2E 通過；登入、成功/失敗、冷卻、無自動重試、React 更新後仍保留面板、320/390/768/1440px，沒有真的發訊息。
- 真實驗證由公開 UI 一次點擊：2026-09-23 15:03:14 +08:00，事件 `78d4e2b8-fe13-4bf5-b2fa-0c77e6e3eb2e`，HTTP 200、Telegram ACK 通過。這不代表收件者已讀。
- 既有近期列表另有一筆 15:02:42 的成功事件；原 QA 對「總列數=1」的假設不成立，改以本次 event_id 驗收，沒有重送。`qa/alarm-demo-live-read.cjs` 僅讀取驗證重整後紀錄/手機，通過。
- `qa/alarm-demo-live-once.cjs` 使用預先寫入的 attempt marker 防止重跑送出；勿刪除 marker 當成測試修復。後續優先跑 mock 或 read-only 測試。
- 正式 320/390px 无整頁溢出；人工檢视 desktop/mobile 圖；pageerror/CSP error 無。BFF log 與發布檔不含 Bot Token，發布檔也不含登入密碼。
- 導覽回歸 `qa/app-shell.cjs` 通過；`qa/history-public.cjs` 三類設備4/6/2圖表、量測15:05:18→15:05:24、24h/7d、分頁/CSV/空區間/手機通過。只有 BFF 容器更新，其餘採集服務未重啟。

回復：UI 設定備份 `server-config.before-v7.json` 指向 v6；套回 `server-config.json` 後用 stop-public/start-public。BFF 舊映像標籤 `ems-bff:before-telegram-20260923` 保留，可重標為 ems-bff:latest 後僅 `docker compose up -d --no-deps --force-recreate bff`；停止 demo 後不用刪量測或更動 DGX。若有後續版本，先核對後續改動，勿盲目回復。4178/4179 保持運行，4181 QA 程序已停止。

## 2026-09-23：Logo A 分頁圖示（v8，已上線）

目前發布 `20260923-local-v8`。沿用 Main Logo 原始兩個金色多邊形，建立透明背景 `favicon-a.svg`、32px PNG 與 180px Apple touch icon；10 個 HTML 入口均使用相對路徑，取代空的 data favicon。原始輪廓與 #cca858 品牌色保留。

本機與隔離發布版已驗證圖示 MIME、尺寸和圖片解碼；隔離版六頁導覽通過。正式瀏覽器實際請求 `/ems/favicon-a.svg` 回傳 200 SVG；Alarms 與觸發按鈕正常顯示。36 個發布檔案 SHA256 與 manifest 全數一致。僅更新靜態圖示與 HTML metadata，BFF 未重啟，登入與 Telegram 邏輯不變。原有分頁需重新整理載入新圖示。

回復：`server-config.before-v8.json` 指向 v7；核對後續改動後套回並 stop-public/start-public。4178 來源與 4179 發布保持運行，4181 驗證程序已停止。
## 2026-09-29：EMS 字標與監控 header 統一（已上線）

目前正式版本：`20260929-shared-header-v1`，38 個發布檔案 SHA256 全數吻合。前版 `20260923-local-v8` 保留；`20260929-ems-logo-v1` 是未公開的首頁單頁中間建置。

依使用者提供的 `\\192.168.0.97\行銷部\99.進行中專案\20260924_PVsim_EMS_synaiQ_logo\pvsim_ems_logo-03.svg` 替換 header「EMS」文字。原檔保留於 `scratch/brand-update-20260929/pvsim_ems_logo-03.svg`，SHA256 `9526aadbc984ba09055f12c4fd7e2c3a3b85912717ba9a21536657b8b9f39d7c`。網站使用 `assets/ems-wordmark-03.svg`：只裁去畫布留白（viewBox 206.42 248.67 429.042 97.94）與將填色改為既有金色 #cca858，三個 path 的幾何資料逐字不變。保留 tAIstro 標誌與「能源管理系統」文字，七個 board 和 live Monitor 都套用相同字標。

監控頁原本使用独立 `.top` 文字 header；改為相同的品牌、專案、警報入口與帳號區，字型/74px桌機高度/響應式斷點對齊。監控專案名稱顯示「自建 EMS 專案」，不冒用示意頁案場。後端資料標示移到內容標題；帳號選單顯示實際 username 與 OPS 角色，未登入可點「登入」聚焦表單，登入後可從右上角選單「登出」。原 API/session/Telegram 及量測程式契約不變。

驗證：`qa/header-brand.cjs` 在來源、編譯隔離版與正式網址驗證 Main/Monitor/Demand/Storage/Alarms/Devices/Reports，1920/1024/768/390/320px 無整頁溢出。來源及正式站實測帳號選單登入、真實圖表、手機選單、登出與清空資料，無 JavaScript 例外；桌機/手機 header 截圖已人工檢視。`qa/history-public.cjs` 正式站量測 08:59:54→09:00:00、三類設備圖表、24h/7d、分頁、CSV、空時段與手機回歸通過。

回復設定：`server-config.before-20260929-header.json` 指向 v8；先核對後續修改再套回並 stop-public/start-public。本次只重啟靜態發布程序，BFF 未重啟；4178 來源預覽與 4179 發布維持運行，4181 隔離 QA 已停止。
## 2026-09-29：重啟後公開入口 504 恢復

檢查時公開 /ems/ 回504；本機BFF session回401（預期未登入），4178預覽正常，但4179沒有監聽程序。依既有start-public.ps1啟動發布服務，保留release=20260929-shared-header-v1與原有路由設定。

恢復後正式首頁200、未登入session仍401；實際瀏覽器登入並確認sim-001量測由11:41:19前進至11:41:24，delta-sim-001可讀83筆原始紀錄、狀態「持續接收中」，無pageerror。證據：output/ems-public-local/qa/recovery-20260929.json。

目前仍未設定開機自動啟動4179；電腦重啟後須依上方步驟啟動發布程序。本次為服務恢復，未切換公開靜態版本。
## 2026-09-29：Delta監控下拉名稱與細小點位（已公開）

依使用者要求發布20260929-delta-monitor-v1。與前版20260929-shared-header-v1相比僅live/history-live.mjs和live/charts.mjs兩檔不同：delta-sim-001下拉文字固定為「太陽能逆變器(delta-sim-001)」；主序列為2px實心circle、無border、hover不放大，保留connectNulls=false。

隔離4181驗證通過後切換4179；正式網址實際登入確認指定文字、四張圖表點位屬性與83筆Delta紀錄，無pageerror。38個發布檔案SHA256全數符合manifest。qa/delta-release.cjs、delta-staging-20260929.json、delta-public-20260929.json保留驗收證據。後端與4178未重啟。

回復設定server-config.before-20260929-delta.json指向shared-header-v1；核對後續變更再套用並stop/start-public。舊release保留，隔離QA程序完成後停止。

## 2026-09-29：縮小 EMS Logo

已發布 `20260929-logo-size-v1`。相較前版 `20260929-delta-monitor-v1`，38 個發布檔案只有 `brand-header.css` 改動：共用 Logo 寬度由 4.4em 改為 3.5em，縮小約 20%，維持原始向量比例。先前即時監控更新完整保留。

七頁在 1920、1024、768、390、320px 的 Header 檢查通過；桌面與手機已檢視。正式 URL Main / Monitor 在 1920px 的 Logo 寬度為 84px、390px 為 56px，沒有橫向溢出；全部 38 個公開檔案 SHA256 與新 manifest 一致。後端與帳號未變更，隔離檢查程序已停止。回復設定保留於 `server-config.before-20260929-logo-size.json`（指向 delta-monitor-v1）。