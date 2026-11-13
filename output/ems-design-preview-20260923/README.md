# EMS 本機設計預覽與即時監控

入口：http://127.0.0.1:4178/#Monitor；能源總覽：http://127.0.0.1:4178/#Main。

即時監控已接自建 EMS BFF（127.0.0.1:8003），每 5 秒讀取最新 1,000 筆。其餘六頁仍為示意資料。這是 output 下的獨立預覽，尚未併入正式 frontend 應用。

## 登入與啟動

本機帳號 demo；密碼位於專案根目錄 `.local/ems-preview-login.json`，不提交 Git、不公開。前端僅持有既有 HttpOnly session，不包含服務 API 金鑰。

依既有 Docker Compose 啟動資料管線、query、device-service 與 bff。Windows 使用 start-preview.ps1 啟動 Node 預覽伺服器。4178 僅綁定 loopback；僅代理登入、登出、session、設備及量測讀取。不可改用 Python 靜態伺服器，否則 API 代理無法運作。

## 2026-09-23 驗證

修復 REST device-service 的本機資料庫連線設定：經使用者確認，同步既有正常容器的 DB_AI_PASSWORD / DB_OPS_PASSWORD 到 .env，私有備份在 .local/env-before-db-sync；未更改資料庫密碼或資料。

登入、設備清單、量測均為 HTTP 200。sim-001 量測從 12:08:26 前進至 12:08:31，功率 39.27 → 37.57 kW；plc-001、sensor-001 亦有量測。資料來自目前運行中的模擬器與採集管線，不能視為現場硬體驗收。

qa/live-smoke.cjs 驗證嵌入畫面登入、真實量測更新與無頁面例外；qa/live-devices.cjs 驗證設備切換及未登入 401 / 缺 Origin 403；qa/model.test.mjs 四項通過，含缺值不補零、過期與空資料。登入表單所在 iframe 已補 allow-forms。

Main 四個插畫使用 energy-illustrations-v3.png，各自獨立 clipPath 防止鄰圖溢出；無意義側欄裝飾已移除。
### 歷史圖表擴充（2026-09-23，PRD-0018 / ADR-027）

2026-09-23 經使用者明確同意，已完成本機 migration 017、BFF 重建與預覽切換，真實資料 E2E 已通過。
變更檔案：migration 017_measurement_history.sql、BFF routes/history.py、preview public/live/{history-live,history-model,charts}.mjs、Monitor.history.html。Node proxy 需允許 GET history / records。

部署順序（需明確批准後執行）：
1. 以 postgres 在 EMS 本機資料庫執行 migration 017。新增唯讀 INVOKER RPC，EXECUTE 僅給既有 web_anon；不修改量測資料。016 為既有窄表草案保留。
2. 重建並重啟 bff；in-memory session 清空，使用者須重新登入。
3. 將 Monitor.history.html 複製至 Monitor.html，Node proxy 啟用 history/records allowlist 後重新啟動僅 loopback 的預覽。
4. 登入測試 3 台設備、15m/24h/7d/自訂範圍、上一/下一頁、CSV及真實量測更新。實際取樣源目前為模擬器。
5. 回滾預覽使用 output/ems-design-preview-20260923/backup-before-history；BFF 回退新增 router。可保留未使用的唯讀 RPC，不刪歷史量測。

隔離測試已通過：tmpfs、network=none 的 ems-history-qa，migration重跑兩次；tests/integration/history-contract.sql 為事務回滾測試（半開時間邊界、min/max/mean/last、布林、空資料、分頁、7天限額），不留下測試資料。BFF 183 tests 通過，新history module覆蓋98%；前端mock E2E通過。mock畫面不是現場資料證據。

隔離負載驗證：86,400 筆 1 秒電表資料，24h / 600 桶 / 4 訊號產生 2,400 點，0.269s；offset 50,000 的 100 筆頁0.193s。僅單次隔離本機測試，非正式環境 SLA。測試資料事務回滾，一次性容器已移除。
## 已部署驗收（2026-09-23 13:03 Asia/Taipei）

經使用者明確批准，已在目前 EMS 資料庫套用 migration 017、重建 BFF，Node proxy 啟用 history/records。新版入口 http://127.0.0.1:4178/?revision=history-v1#Monitor。需要重新登入既有 local-ops 帳號。

qa/history-live.cjs 實測：三類設備共 4/6/2 張趨勢圖；sim-001 量測由 13:02:58 更新至 13:03:04；24h、7d、自訂空區间、固定視窗歷史第2頁與100列 CSV、390px版面均通過，所有資料查詢 HTTP 200、無 JavaScript 例外。此為實際管線採集的模擬器資料，非硬體驗收。畫面預設30秒刷新，可選5秒或暫停。

## 2026-09-23 Telegram DEMO 已部署
目前帳號為 demo（舊 local-ops 已停用）；#Alarms 新增實際 Telegram 通知按鈕、同頁登入及發送紀錄。來源 live/alarm-demo.mjs/css，BFF /api/alarms/demo；4178 proxy 已精確放行 GET/POST，金鑰仍僅後端。完整驗收與回復見 ../ems-public-local/README.md 的 v7 紀錄。
