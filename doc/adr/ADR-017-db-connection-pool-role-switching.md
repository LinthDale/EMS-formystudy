# ADR-017：DB Connection Pool & Role Switching

## Status
Accepted（2026-05-29）

> 來源：PRD-0003 §6.5；DL-006（v6，F-V5-1 / F-V5-2 修法）。補完 ADR-016 的 DB role 拆分「何時用哪個 role」與 connection pooling 模式。

## Context

ADR-016 / migration 010 拆出 `device_service_ai` / `device_service_ops` 兩個 DB role + freeze trigger，但 v5 未明文：

1. device-service **何時用哪個 role**
2. **connection pooling 模式**（尤其 advisory lock 與 `SET LOCAL freeze_override` GUC token 在 pooler 下的相容性）

F-V5-1 / F-V5-2 兩個 FAIL 即源於此。`SET ROLE` 切換與 connection pooler transaction mode 不相容，會導致 advisory lock 釋放時機不可預期、freeze override token 失效。

## Decision

採 **雙連線池（per-role login）+ pgbouncer 強制 session mode**：

### 雙連線池（不用 SET ROLE）
- device-service 維持**兩個獨立連線池**，各用對應 role 的 login DSN：
  - `DB_AI_DSN  = postgresql://device_service_ai:$DB_AI_PASSWORD@timescaledb:5432/ems`
  - `DB_OPS_DSN = postgresql://device_service_ops:$DB_OPS_PASSWORD@timescaledb:5432/ems`
- **不採用** `SET ROLE`（與 pooler transaction mode 不相容）
- AI pool 建議 ≥ OPS pool（AI 路徑流量大）；兩組密碼分存 `.env`

### 路徑 → 連線池對映
| 呼叫路徑 | 連線池 |
|---------|-------|
| MQTT subscribe / 自動分類 / `classify_with_context` MCP / L2 guardrail / AI 寫 ai_*、digest、candidate->confirmed | **AI pool** |
| OPS REST：CRUD / confirm / override / reject / ai-feedback / budget extend / corrections deactivate | **OPS pool** |
| 讀 measurements raw（為 LLM 取樣本）| **OPS pool**（AI role 無 SELECT 權限）|
| INGEST endpoint（Phase 2 webhook）| OPS pool + INGEST scope 中介層 |

> 應用層中介層（FastAPI `Depends(get_ai_pool)` / `Depends(get_ops_pool)`）依 endpoint metadata 注入正確 pool；**不在 handler 內選 pool**。CI lint 檢查 handler 不直接 import 兩個 pool。

### Pgbouncer 相容性
- **若部署 pgbouncer**：必須 **session mode**（非 transaction mode），因為：
  - `pg_advisory_xact_lock` 需 transaction 內持有
  - `SET LOCAL device_service.freeze_override` 需 transaction 內持續可見
  - `current_setting(..., true)` 在 transaction mode 下因 server connection 切換失效
- **不部署 pgbouncer**（Phase 1 dev 直連）：規範仍適用，driver-level connection 天然 transaction-scoped
- 採 pgbouncer 的部署**必須** documented 於 `doc/operations/容器速查表.md` 並標記模式

### 連線健檢
- `/healthz` 同時 ping 兩池；任一不健康 → 503
- 各池 metric：`db_pool_checkout_latency_seconds{pool="ai|ops"}`

## Consequences

**正面**
- per-role login 連線池讓 freeze trigger（ADR-016）與 budget advisory lock（ADR-014）在 pooler 下行為正確
- pool 由中介層注入，handler 無從誤用 role，降低人為提權錯誤
- 雙池健檢確保任一 role 連線異常即早暴露

**負面**
- 維護兩組 DB 密碼 + 兩個連線池（連線數加總）
- pgbouncer 必鎖 session mode，犧牲 transaction mode 的連線複用效率

**已知風險**
- 開發者新增 endpoint 時選錯 pool → CI lint + Depends 注入雙重防呆
- session mode 連線數較高 → 監控 pool checkout latency

**後續觸發**
- production smoke test：兩 role 各自 login + freeze trigger 拒絕測試（夾 GUC token vs 不夾）— Promotion Checklist P-8
- pgbouncer 若導入，integration test 須含 session mode container（PRD §13）
