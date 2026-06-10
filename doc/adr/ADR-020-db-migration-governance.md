# ADR-020：DB Migration 治理 — schema_migrations 追蹤 + runner 工具選型

## Status
Proposed（2026-06-09）

> 與 [api-contract-governance](../governance/api-contract-governance.md)（API 契約治理）為**兩條獨立治理線**——本 ADR 管 **DB schema 遷移**，與 API 版控無關。源於 review 指出「migration 無版控紀律」之關切；明確**不**在 PRD-0005（前端）內順手換工具。

## Context

EMS 的 DB schema 由 `infra/timescaledb/migrations/` 的**手編號 raw SQL** 管理（`000_*` ~ `015_*`，共 15 支；002 跳號。**2026-06-10 更正**：本 ADR 初稿誤寫 `018_*`，此錯曾傳播至 PRD index 與 PRD-0006 草稿——目錄真相以 `ls infra/timescaledb/migrations/` 為準）。現況：

- **優點（既有事實，不重寫歷史）**：每支 idempotent（`IF NOT EXISTS` / `CREATE OR REPLACE` / `ON CONFLICT` / `DO $$ ... pg_roles 檢查`）、有序、純 SQL 透明、無 ORM 耦合（符合 raw asyncpg 技術棧）。已套用於 dev DB 且經 `tests/integration/test_migrations.py` 驗證。
- **缺口**：
  1. **無 `schema_migrations` 追蹤表**：DB 不知道「已套到第幾號」，全靠人工 / 慣例 + idempotent 重跑兜底。
  2. **無正式 runner**：套用方式分散（test harness `_run_sql_file`、compose init、人工）；無「只跑未套用的、依序、記錄」的單一入口。
  3. **無 down / rollback** 慣例（目前靠 idempotent + 新 migration 修正，不回滾）。
  4. 跳號（002）等靠人記。

非緊急（idempotent 重跑使現況可運作），但隨 schema 變多、多環境（dev/prod）部署，缺追蹤表與 runner 會成為風險。

## Decision

> Proposed — 待評估後決定採用哪個工具 / 最小方案。方向先鎖定：

**1. 不採用 Alembic（明確排除，附理由）**
- Alembic 綁 SQLAlchemy metadata / autogenerate；本專案是 **raw asyncpg + raw SQL**，無 SQLAlchemy model。Alembic 雖能執行 raw SQL，但失去其 autogenerate 主賣點，且引入一個 stack 不對味的相依。
- **除非**專案另行決定導入 SQLAlchemy（目前無此計畫），否則 Alembic 非自然選擇。

**2. 候選工具（raw-SQL 友善，擇一評估）**

| 工具 | 特性 | 對本專案 |
|------|------|---------|
| **dbmate** | 單一 binary、純 SQL up/down、`schema_migrations` 表、語言無關 | 輕、貼近現況（純 SQL），遷移成本低 |
| **sqitch** | 依賴圖 + verify/revert、無編號靠 tag | 功能強但概念較重 |
| **golang-migrate** | binary / library、純 SQL、source 多元 | 輕、CI 友善 |
| **atlas** | 宣告式 schema + diff、HCL/SQL | 強大但範式轉換較大 |

**3. 最小可行方案（若不導入完整工具）**
- 加一個 **`schema_migrations` 表**（filename / applied_at），配一支極簡 runner（依序套未記錄者、寫入表）。**保留 000–015 既有 SQL 不重寫歷史**——以 baseline 方式把現有編號標為已套用，自 **016 起**納入新流程（PRD-0006 之 migration 016 即第一支）。

**4. down/rollback 立場**
- 現況「不回滾、以新 migration 修正」對 append-only / 生產資料是安全預設；是否補 down script 由選型一併決定（dbmate/golang-migrate 支援 down，可選擇性採用）。

## Consequences

**正面**
- DB 有明確「已套版本」真相；多環境部署可重現、可稽核。
- 單一 runner 入口取代分散套用方式，降低人為漏套 / 重複套風險。
- 不重寫 000–015 歷史 → 遷移成本低、不破壊既有 idempotent 保證。

**負面**
- 引入一個新工具 / runner 相依（即使最小方案也多一支腳本 + 一張表）。
- 既有 `test_migrations.py` 的套用路徑需與新 runner 對齊（避免兩套套用邏輯）。

**已知風險 / 待評估**
- baseline 既有 18 支進 `schema_migrations` 時，須確保 dev/prod 標記一致（否則新 runner 會重跑）。
- 工具選型未定前不動手；本 ADR 維持 Proposed。

**後續觸發（採用後）**
- 落地選定工具 / 最小 runner + `schema_migrations` 表（baseline 000–015，016 起納管）。
- 更新 operations manual（部署遷移步驟）、容器速查表（若新增 runner 容器/步驟）。
- 與 [api-contract-governance](../governance/api-contract-governance.md) 並列為治理線，互不耦合。
