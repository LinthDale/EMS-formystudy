# ADR-018：擴充 Freeze Trigger 保護欄位集 + metadata 局部 merge

## Status
Accepted（2026-05-29）

> 延伸 [ADR-016](ADR-016-two-layer-ai-guardrail-db-freeze-trigger.md) 的 DB freeze trigger。源於 PRD-0003 **Phase 1.1 實作前弱點掃描 Finding B**（對 live DB 實測確認）。ADR-016 不修改（依 ADR 規則僅可改狀態），本 ADR 記錄調整並由 migration 011 落地。

## Context

ADR-016 / migration 010 的 `enforce_freeze_rule()` 只比對 4 個欄位是否變動：`device_type` / `status` / `classified_by` / `gateway_id`。

實作前弱點掃描實測：以 `device_service_ai` role 對凍結裝置（`classified_by='migration_backfill'` 的 sim-001）：
- 改 `device_type` → **被擋** ✓
- 改 `vendor='attacker'` / `model` / `location` / `protocol` / `metadata` / `ai_confidence` → **成功寫入** ✗

即被 RCE 的 AI role 仍可竄改「人工策展的身分欄位」與 `metadata`。

兩難：FR-335 明定 AI **必須**能在凍結裝置寫 `last_seen_at` 與 `metadata.drift_detected_at`（drift 偵測）。因此 `metadata` 與 `ai_confidence` / `ai_provider` / `last_error` **不能**整欄凍結，否則 drift 偵測失效。

## Decision

**1. 擴充 freeze trigger 保護欄位集**（migration 011，`CREATE OR REPLACE` 取代 010 的函式體）：

| 凍結（變動即擋） | 維持可寫（AI 本職） |
|------|------|
| device_type, status, classified_by, gateway_id（原 010）+ **vendor, model, location, protocol（本 ADR 新增）** | metadata, ai_confidence, ai_provider, last_error, last_seen_at, confirmed_at, activated_at, stale_marked_at |

理由：vendor/model/location/protocol 屬人工策展的裝置身分，與 device_type 同性質，應一併凍結。

**2. `metadata` 整欄覆寫由 app 層控制**（Phase 1.2 實作要求，非 DB 欄位凍結）：
- device-service 對凍結裝置只能用 **局部 merge**（`metadata = metadata || delta`）寫入 `drift_detected_at` 等 AI 子鍵，**禁止整欄覆寫**（避免抹除 human / audit sub-key）
- 此為應用層不變式，列入 Phase 1.2 backlog 與 code review checklist；DB 層無法區分「合法子鍵更新」與「惡意整欄覆寫」，故不在 trigger 強制

**3. `enforce_signals_freeze()` 不變**：signals 主欄位已全凍（INSERT/UPDATE 皆擋）。

## Consequences

**正面**
- 凍結裝置的身分欄位（含既有 sim-001/plc-001/sensor-001）即使 AI role 被 RCE 也改不動
- 保留 FR-335 要求的 AI drift 偵測寫入能力（metadata 子鍵 + last_seen_at）
- 以新 migration 落地，不改已套用的 010（migration append-only）

**負面**
- `metadata` 整欄覆寫的防護落在 app 層，DB 層無法兜底 → 依賴 Phase 1.2 正確實作 + review
- 合法的人工改 vendor/model/location/protocol（透過 OPS override）須夾 `freeze_override` token，多一步

**已知風險（殘留）**
- app 層若誤用整欄覆寫 metadata → 繞過保護；以 code review + 單元測試（驗證 merge 行為）緩解
- localhost trust（見弱點掃描 Finding A）下可假冒任何 role → 屬 pg_hba / 部署層，由 Promotion Checklist P-8 處理

**後續觸發**
- migration 011 + `test_migrations.py` 對應測試（vendor 改動被擋、ai_confidence 仍可寫）
- Phase 1.2：metadata 局部 merge 不變式 + 測試
- 同步更新 risk-register（Finding A localhost trust、metadata app 層殘留）