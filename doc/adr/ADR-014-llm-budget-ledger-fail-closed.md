# ADR-014：LLM Budget Ledger Fail-Closed Gate

## Status
Accepted（2026-05-29）

> 來源：PRD-0003 §10 Budget Ledger / §8.1；DL-003（fail-closed gate）、DL-005（W-D per-key rate + 滾動 30 天 window）。

## Context

dev 期 LLM 月預算 $20 USD。若無硬性閘門，攻擊者（塞惡意 prompt 觸發大量 classification）或 bug（無限 retry）可燒爆預算。需要一個**先檢查、後呼叫**的閘門，且涵蓋所有外送 LLM 的路徑。

可選方案：

| 方案 | 取捨 |
|------|------|
| A. 只在月底對帳（fail-open）| 超支已成事實 ❌ |
| B. 每次 call 前過 ledger gate（fail-closed）| 達 100% 立即停外部 LLM、走 fallback ✅ |

## Decision

採 **方案 B：pre-call fail-closed gate**：

- **每次 external LLM call 之前先過 budget ledger gate**：100% → 立即走 `MockProvider` system_fallback（`summary_source='system_fallback'`、`ai_provider=null`）
- **涵蓋全部路徑**：`?force=true`、MCP `classify_with_context`、retry、並發路徑一律受限（FR-329）
- **並發保護**：用 `pg_advisory_xact_lock` 確保並發 call 不超扣
- **告警分級**：80% → Telegram alert（單次，重複不重發）；100% → fail-closed gate 啟動（FR-319）
- **L1 / L2 各自 ledger row**：L2 guardrail 用 `provider='guardrail'` 獨立 row；L2 budget 100% → 整個分類管線停（L1 也停，全走 fallback，FR-340）
- **緊急覆寫 endpoint** `POST /admin/budget/extend`（FR-334）：
  - **OPS only**；AI / INGEST / MCP key 一律 401
  - 必填 `additional_usd` + `reason`（≥ 30 字）；超單次上限 422
  - audit log 強制；per-IP 1/min + per-key rate limit（W-D）
- **月度切換改滾動 30 天 window**（W-D，取代固定月度 reset）

## Consequences

**正面**
- 預算不可能被單一攻擊 / bug 燒穿（fail-closed）
- Output Validator / L2 BLOCK 抓到的惡意分類**不計入 budget**，避免「抓到攻擊反而幫攻擊者燒錢」
- system_fallback 確保 budget 用罄後系統仍可回應（degraded，非中斷）

**負面**
- 預算用罄後分類品質降為 deterministic heuristic（MockProvider）
- 並發 advisory lock 增加每次 call 的 DB 往返

**已知風險**
- ledger 計算與真實 API 帳單存在誤差 → 保守估算 + 80% early alert 緩衝

**後續觸發**
- production 啟用獨立 ledger row（`prev_budget=0`，不繼承 dev 累計）— Promotion Checklist P-6
- 並發鎖需 pgbouncer session mode（見 ADR-017）
