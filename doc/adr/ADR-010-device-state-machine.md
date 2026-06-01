# ADR-010：Device 狀態機（五狀態 + stale 軟旗標）

## Status
Accepted（2026-05-29）

> 來源：PRD-0003 §7.1.1 / §7.1.2 / §7.1.3；DL-002 正式化狀態機。

## Context

device registry 需記錄裝置生命週期。痛點之一是「裝置生命週期狀態（active / maintenance / retired）無紀錄」。需要一個封閉、可驗證的狀態集合與轉換規則，並界定哪些轉換屬 AI、哪些限人類（OPS）。

關鍵取捨：

1. `stale`（30 天未處理）要不要進 status enum？
2. candidate 超時要不要自動 retire？
3. `devices` 要不要對 measurements 加 FK？

## Decision

採 **五狀態封閉 enum + stale 為軟旗標**：

- **status enum**（封閉集合）：`candidate` / `confirmed` / `active` / `maintenance` / `retired`
  - `active` 於 Phase 2+（PRD-0004 動態管線啟用後）才生效；Phase 1 高信心 candidate 轉 `confirmed` 即止
  - `retired` 為 terminal 狀態
- **轉換規則**（對齊 §8.6.1 權限矩陣）：
  - `candidate -> confirmed`：AI（信心 > 0.9 + 無 correction 衝突 + L2 PASS + 持有 advisory lock）或 OPS
  - `candidate -> retired`：OPS（reject）
  - `confirmed -> candidate`（demote 重審）：**OPS only**
  - `confirmed -> maintenance / retired`：**OPS only**
  - `maintenance -> confirmed`（resume）：OPS
- **stale 不進 enum**：candidate 超過 30 天未處理 → 設 `stale_marked_at` + `metadata.review_state='stale'`；**不自動 retire**，僅作 dashboard 排序與 alert 訊號（FR-318）
- **不對 measurements 加 FK**：保護既有 ems / factory 域寫入路徑（G7）；devices 與 measurements 鬆耦合，靠 `device_id` 字串關聯

## Consequences

**正面**
- 封閉 enum 可在 DB 層 CHECK constraint 強制，非法狀態寫不進去
- stale 為軟旗標 → 不會把運維還沒看的 candidate 自動清掉（避免誤刪真實裝置線索）
- 不加 FK → 既有 measurements 寫入零影響（G7 / FR-313）

**負面**
- `active` 狀態在 Phase 1 為「預留未用」，需在文件標註避免實作者誤用
- devices ↔ measurements 無 FK → 資料一致性靠應用層而非 DB referential integrity

**已知風險**
- 大量 stale candidate 累積佔空間 → 回滾條件之一（disk > 80%）+ housekeeping 任務追蹤

**後續觸發**
- `active` / `confirmed -> active` 轉換規則於 PRD-0004 補完
- 狀態機若需新增狀態，走後續 ADR（不改本 ADR）
