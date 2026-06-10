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
| ADR-009 | LLM Provider 抽象層 + SanitizedSample 強制入參 | Accepted | 2026-05-29 |
| ADR-010 | Device 狀態機（五狀態 + stale 軟旗標）| Accepted | 2026-05-29 |
| ADR-011 | device_signals 採 current-state + soft delete | Accepted | 2026-05-29 |
| ADR-012 | device-service 自帶獨立 MCP endpoint（AI 通道僅讀 + 重跑分類）| Accepted | 2026-05-29 |
| ADR-013 | MQTT Topic Parser Matrix v3（deny-by-default）| Accepted | 2026-05-29 |
| ADR-014 | LLM Budget Ledger Fail-Closed Gate | Accepted | 2026-05-29 |
| ADR-015 | AI Bounded Autonomy + Correction Loop | Accepted | 2026-05-29 |
| ADR-016 | Two-Layer AI Guardrail + DB Freeze Trigger | Accepted | 2026-05-29 |
| ADR-017 | DB Connection Pool & Role Switching | Accepted | 2026-05-29 |
| ADR-018 | 擴充 Freeze Trigger 保護欄位集 + metadata 局部 merge | Accepted | 2026-05-29 |
| ADR-019 | 跨-provider L2 Guardrail（L1/L2 不同廠商 defense-in-depth）| Proposed | 2026-06-09 |
| ADR-020 | DB Migration 治理（schema_migrations + runner 選型；排除 Alembic）| Proposed | 2026-06-09 |

> ADR-009 ~ ADR-017 源自 PRD-0003（Device Registry & Auto-Discovery，Approved 2026-05-08 / DL-007），將 PRD §6.4 鎖定之 9 項架構決策正式化。
> ADR-018 源自 PRD-0003 Phase 1.1 實作前弱點掃描 Finding B，擴充 ADR-016 的 freeze trigger 保護欄位集。
> ADR-019 源自 PRD-0003 §8.7.3 follow-up，為 [PRD-0004](../prd/PRD-0004-device-service-observability-alerting.md) 排除之 Non-Goal；**Proposed，卡 Anthropic key**。
> ADR-020 源自 review 對 migration 版控之關切；與 [api-contract-governance](../governance/api-contract-governance.md) 為兩條獨立治理線（DB 遷移 vs API 契約）；**Proposed，排除 Alembic（stack 非 SQLAlchemy）**。

## 撰寫規則

- 檔名：`ADR-NNN-kebab-case-title.md`
- 模板：見 `doc/PRD-架構設計-Guideline.md` §9
- 狀態值：`Proposed` / `Accepted` / `Deprecated` / `Superseded by ADR-XXX`
- 變更已 Accepted 的 ADR：新建後續 ADR 並反向連結，**不修改舊 ADR 內容**（僅可改狀態）
