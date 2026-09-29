# ADR-028：BFF 發送固定 Telegram 示範警報
## Status
Accepted — 2026-09-23，依使用者要求增加警報中心 DEMO 按鈕。
## Context
既有 Telegram contact point 已設定；產品警報頁目前無通知操作。讓前端接 Bot API 會暴露密鑰；Grafana 管理 API 權限超出這個按鈕所需。
## Decision
由既有 FastAPI BFF 增加 OPS/Origin 驗證的 GET/POST /api/alarms/demo。沿用 Telegram Token/Chat ID，固定接收對象和明確 DEMO 內容，30s 冷卻、10min UUID 去重，不自動重試。前端只能提交 UUID；公開 Node 代理精確放行端點。Bot 密鑰不進瀏覽器，HTTP 日誌遮蔽 Token。不更動 Grafana 真實告警和設備控制。
## Consequences
無新服務與 DB migration；新增 BFF 對 Telegram 的 HTTPS egress。單進程 in-memory 去重/紀錄重啟會清空，水平擴展前改用共享儲存。回應成功只代表 Telegram ACK，非已讀。新增測試、API契約、四同步文件，詳見 [PRD-0019](../prd/PRD-0019-telegram-demo-alarm.md)。
