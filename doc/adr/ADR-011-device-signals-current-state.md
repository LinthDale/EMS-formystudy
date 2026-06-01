# ADR-011：device_signals 採 current-state + soft delete

## Status
Accepted（2026-05-29）

> 來源：PRD-0003 §7.2；DL-002。

## Context

裝置訊號（voltage / temperature / pressure / motor_speed ...）schema 在 PRD-0001/0002 寫死於 measurements 表，不可延展（痛點 #3）。需要一張可容納異質訊號定義的表，並決定其歷史變更如何保存。

可選方案：

| 方案 | 說明 | 取捨 |
|------|------|------|
| A. append-only 版本表 | 每次變更插新列、永不更新 | 完整歷史，但 Phase 1 查詢需 `DISTINCT ON` / window，複雜度高 ❌（過度設計）|
| B. current-state + soft delete | 每個 (device_id, signal_name) 未 retired 前只存一列；變更寫 metadata.history | 查詢簡單、保留輕量歷史 ✅ |
| C. current-state + hard delete | 直接 UPDATE / DELETE | 無歷史、不可稽核 ❌ |

## Decision

採 **方案 B：current-state + soft delete**：

- 每個 `(device_id, signal_name)` 在「未 retired」前**只存一列**
- **PARTIAL UNIQUE INDEX**：`(device_id, signal_name) WHERE status = 'active'` — active 版本唯一，已 retired 的不阻擋新增
- **DELETE API**：soft delete — 設 `status='retired'` + `retired_at`，不真實刪除
- **PATCH API**：覆寫當前值，舊值 append 進 `metadata.history`（`[{changed_at, old_values, by}]`）
- **FK**：`device_id` → `devices(device_id)` ON DELETE CASCADE
- 完整版本化歷史表留待 Phase 2+ 視需求評估（不在本 PRD）

## Consequences

**正面**
- 查詢「某裝置目前有哪些 active 訊號」= 單純 `WHERE status='active'`，無需 window 函數
- soft delete 保留稽核軌跡；partial unique index 兼顧唯一性與重新啟用
- metadata.history 提供輕量變更紀錄，不必另開版本表

**負面**
- metadata.history 為 JSONB 陣列，長期累積可能膨脹（Phase 1 變更頻率低，可接受）
- 非完整版本化 → 若未來需精確時間旅行查詢，須 Phase 2 升級為版本表

**已知風險**
- `source_ref`（modbus addr / mqtt path）屬 OT 偵察前置情報 → 不開進對外 view（ADR-005 白名單原則 / FR WARN-3）

**後續觸發**
- 對外 view `api.device_signals` 欄位白名單見 PRD §7.4（不含 source_ref / status）
- 版本化歷史表評估 → Phase 2+ 新 ADR
