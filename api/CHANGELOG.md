# API CHANGELOG（api/openapi.yml）

> 規則見 [api-contract-governance](../doc/governance/api-contract-governance.md)。每次 API 變更一條：版本 / 日期 / 級別 / 摘要 / 對應 PRD。

## 2.1.0 — 2026-09-30（MINOR）
- PRD-0023 / ADR-035：local 帳號唯一來源 PostgreSQL，移除 env user table。
- 補列既有 BFF auth login/session/logout/role 契約；停用、角色與密碼變更撤銷舊 session，DB 故障503。
- 帳號管理為主機 CLI，未新增公網管理 API；OIDC 保持相容。

## 2.0.1 — 2026-09-29（PATCH，文件）
- 補充維運CLI數字loopback HTTP的Secure-cookie相容處理；BFF session、認證、API schema及server安全設定不變。
- CLI登入/讀取錯誤與派送後未知結果分開提示；PRD-0022／ADR-033。

## 2.0.0 — 2026-09-29
- Breaking (PRD-0022 / ADR-033): retire host :8001 simulator API and unaudited Modbus/MCP simulator writes.
- Add OPS-only /api/simulators state/configure and persistent /operations query/reconcile.
- UUID dedup, instance/revision CAS, durable intent, append-only events, bounded bodies and unknown outcome handling.
- Internal control :9000 is service-credential protected and has no host port; see [operations manual](../doc/operations/simulator-control.md).

## 1.3.0 — 2026-06-10（MINOR）
- `GET /devices`：新增選填查詢參數 `type`（device_type 過濾）、`limit`/`offset`（分頁，limit 1–500）、`sort`（7 欄位 allowlist）/`order`（asc/desc，NULLS LAST）。預設行為不變（全列、ORDER BY device_id）。
- `DeviceOut`：新增選填欄位 `ai_confidence`（0–1，未分類 null）——信心佇列（PRD-0005 FR-510）所需。
- 修正既有 spec 漂移：`DeviceOut` 補上實作早已回傳的 `confirmed_at` 欄位。
- 對應：PRD-0005 §1.5 GATE-2 後端增量（D1/D3）。消費端注意：新增欄位為 additive；client 由 spec 重新生成即可。

## 1.4.0 — 2026-09-23（MINOR，本機已部署）
- 新增 OPS-only BFF history / records，完整指定區間彙整與原始紀錄分頁；既有 measurements 不變。PRD-0018 / ADR-027；migration 017 唯讀 RPC。

## 1.5.0 — 2026-09-23（MINOR）
- 新增 OPS-only `GET/POST /api/alarms/demo`：狀態/最近十筆、固定 Telegram 對象與 DEMO 文字、Origin CSRF、30 秒冷卻與 10 分鐘 UUID 去重。PRD-0019 / ADR-028。
- 此功能不觸發設備故障或修改 Grafana 告警規則；200 僅表示 Telegram 已確認接收，非使用者已讀。

## 2026-09-29 — Delta phase-1 telemetry extension
新增x-delta-telemetry描述既有MQTT/四欄electricity相容投影；無新增或變更HTTP endpoint。V/A=L1、kW=三相總功率、kWh=累計發電，詳PRD-0020/ADR-029。
