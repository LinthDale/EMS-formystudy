# API CHANGELOG（api/openapi.yml）

> 規則見 [api-contract-governance](../doc/governance/api-contract-governance.md)。每次 API 變更一條：版本 / 日期 / 級別 / 摘要 / 對應 PRD。

## 1.3.0 — 2026-06-10（MINOR）
- `GET /devices`：新增選填查詢參數 `type`（device_type 過濾）、`limit`/`offset`（分頁，limit 1–500）、`sort`（7 欄位 allowlist）/`order`（asc/desc，NULLS LAST）。預設行為不變（全列、ORDER BY device_id）。
- `DeviceOut`：新增選填欄位 `ai_confidence`（0–1，未分類 null）——信心佇列（PRD-0005 FR-510）所需。
- 修正既有 spec 漂移：`DeviceOut` 補上實作早已回傳的 `confirmed_at` 欄位。
- 對應：PRD-0005 §1.5 GATE-2 後端增量（D1/D3）。消費端注意：新增欄位為 additive；client 由 spec 重新生成即可。
