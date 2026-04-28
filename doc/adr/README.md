# Architecture Decision Records (ADR)

> 對齊：`doc/PRD-架構設計-Guideline.md` §9

此目錄記錄 EMS 系統所有架構層級的決策。每個 ADR 為獨立檔案，編號連續、不刪除（取代用 `Superseded by ADR-XXX`）。

## 索引

| # | 標題 | 狀態 | 日期 |
|---|------|------|------|
| ADR-001 | Open-source-first 服務選型 | Accepted | 2026-04-22 |
| ADR-002 | pymodbus 鎖定 3.6.9 | Accepted | 2026-04-22 |
| ADR-003 | Telegraf 採用 `[[inputs.modbus.request]]` 新版語法 | Accepted | 2026-04-22 |
| ADR-004 | PostgREST 連線字串改 key=value 格式 | Accepted | 2026-04-22 |
| ADR-005 | DB schema 採 `api` / `public` 雙層隔離 | Accepted | 2026-04-22 |
| ADR-006 | KC Factory 鏈路獨立為 kc-gateway / kc-ingest | Accepted | 2026-04-24 |
| ADR-007 | MQTT Topic 命名規範 `ems/devices/{id}/measurements` | Accepted | 2026-04-22 |
| ADR-008 | Grafana 對外採 Cloudflare Tunnel + Access | Accepted | 2026-04-28 |

## 撰寫規則

- 檔名：`ADR-NNN-kebab-case-title.md`
- 模板：見 `doc/PRD-架構設計-Guideline.md` §9
- 狀態值：`Proposed` / `Accepted` / `Deprecated` / `Superseded by ADR-XXX`
- 變更已 Accepted 的 ADR：新建後續 ADR 並反向連結，**不修改舊 ADR 內容**（僅可改狀態）
