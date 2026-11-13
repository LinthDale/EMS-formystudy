# ADR-036：Telegram 訪客 QR 綁定採 BFF 長輪詢與單一綁定

## Status
Accepted — 2026-10-13，使用者核准展位 QR 綁定需求並同意修訂 PRD-0019 Non-goal。部分取代 [ADR-028](ADR-028-telegram-demo-alarm.md)：「固定單一接收對象」改為「有效訪客綁定優先，否則固定對象」；ADR-028 其餘決策（OPS/Origin、冷卻、UUID 去重、Token 遮蔽、固定文字）保留。

## Context
展位需要讓訪客自助成為示範告警收件者。BFF 只聽 127.0.0.1:8003，經 Windows Node 代理與 DGX nginx 對外，沒有可供 Telegram webhook 回呼的入站端點；新增入站路徑會擴大攻擊面並需改 DGX。同一 Bot Token 目前只被 Grafana 與 BFF 用於 sendMessage，沒有任何 getUpdates／webhook 消費者。需求要求最新掃描者優先、10 分鐘到期、當日不重複計數、重啟不歸零與最小個資。

## Decision
- BFF lifespan 內啟動單一背景任務，以 getUpdates long polling（timeout 25 秒、只收 message）讀 Bot 更新，offset 存 SQLite；不使用 webhook，不自動 deleteWebhook，偵測到 webhook 或 409 時只回報狀態。
- Deep link `t.me/<bot>?start=<code>`：code 為記憶體中 128-bit 隨機值，每 60 秒輪替、每個有效 300 秒，可重複使用以符合「後掃者優先」；訊息超過 120 秒忽略。
- 唯一綁定（取代式）與當日計數存於 BFF 專用 SQLite volume `demo_alarm_state`（沿用 ADR-033 單程序 flock／fail-closed 模式，另開 secure_delete）；訪客以每日隨機 key 的 HMAC 假名化，午夜換 key 並清空。
- POST /api/alarms/demo 不改請求契約：有效綁定送訪客三行文字並計號（ACK 或不確定才計），否則送固定對象原文字；回應與 GET 狀態只做附加欄位，代理白名單不變。
- 前端以 vendored `uqr`（MIT）在瀏覽器產生 QR SVG；功能以 `bff.toml` `demo_bind_enabled` 開關。

## Alternatives
- Webhook：需對外入站 HTTPS 端點與 DGX 設定，與 loopback-only BFF 邊界衝突，否決。
- 固定 start code：可被拍照後長期遠端冒綁，否決。
- 後端產生 QR（Python 套件）：新增 BFF 執行期依賴、API 回傳大型矩陣，否決。
- 記憶體狀態不持久化：重啟會讓計數歸零，不符需求，否決。

## Consequences
新增 BFF 對 api.telegram.org 的長連線出站與一個 volume；不新增容器、port 或入站路徑。同一 Bot Token 同時只能有一個 getUpdates 消費者，預備測試容器必須在正式 BFF 啟用前停止。單程序 uvicorn 假設延續；水平擴展前需改共用協調。成功仍只代表 Telegram ACK。詳見 [PRD-0024](../prd/PRD-0024-booth-telegram-qr-binding.md)。
