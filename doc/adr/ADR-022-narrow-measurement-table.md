# ADR-022：窄表 signal_measurements — 通用量測儲存決策

## Status
Proposed（2026-06-10）

> 對應 [PRD-0006](../prd/PRD-0006-Generic-Measurement-Pipeline-Dynamic-Visualization.md) FR-601~605。相關：[ADR-020](ADR-020-db-migration-governance.md)（migration 治理）、[ADR-021](ADR-021-device-type-closed-set-policy.md)、PRD-0001/0002（既有寬表）、PRD-0005 §1.5 D2（PostgREST 量測契約已存在）。

## Context

量測儲存僅有 2 張寫死寬表（`electricity_measurements` / `factory_measurements`），新裝置型別（電池 SoC、逆變器 DC 側、EV charger…）的量測**無欄位可落**。需要一個不隨型別增長而改 schema 的通用儲存。

## Decision

**1. 窄表 hypertable** `public.signal_measurements(time TIMESTAMPTZ NOT NULL, device_id TEXT NOT NULL, signal_name TEXT NOT NULL, value_num DOUBLE PRECISION, value_bool BOOLEAN, value_text TEXT)`，CHECK 三 value 欄**恰一非 NULL**；索引 `(device_id, signal_name, time DESC)`。

**2. day-one columnstore 壓縮**：`segmentby = (device_id, signal_name)`、`orderby = time DESC`；壓縮 policy 7 天（可調，tunable-parameters 登錄）；chunk interval 可調。

**3. `measurements_unified` UNION ALL view**：兩張寬表 unpivot + 窄表，讀取側統一形狀（Device Explorer 一個查詢面涵蓋新舊裝置）；是否進 PostgREST 留 PRD-0006 §14 Open Question。

**4. 舊寬表原封不動**：無 dual-write、無回填、telegraf 寫入路徑不動；新舊並行，僅讀取側合併。

**5. 新 DB role `ems_ingest`**：僅 `INSERT ON public.signal_measurements`（+ schema USAGE），無 SELECT/UPDATE/DELETE；供 ingest-generic 專用，**不對 AI role 開放**。

**6. migration 編號自 019 起**（依 ADR-020 治理；PRD-0003 已用至 018）。

### 否決方案
- ❌ **JSONB payload 欄**（time, device_id, payload JSONB）：columnstore 壓縮效果差（無同質欄位可 segment）、無 per-signal 索引、查詢需展開——時序熱路徑不可接受。
- ❌ **per-type 動態建表**（每 device_type 一張表，confirm 時 DDL）：runtime DDL 需要服務持有 CREATE 權限，違反最小權限與 freeze 治理哲學；schema 爆炸、migration 不可治理。
- ❌ **寬表加欄位 / dual-write**：回到「每型別改 schema」的原問題；dual-write 引入一致性負擔而無對應收益（歷史資料不需搬）。

## Consequences

**正面**
- 任意 `(device_id, signal_name, value)` 即插即落庫，新型別零 schema 變更；與 AI 升格（PRD-0006 FR-606/607）銜接成 registry 驅動的端到端鏈。
- `ems_ingest` 最小權限比現狀（telegraf 以 postgres superuser 寫入）更乾淨。

**負面 / 風險**
- 量級：200 裝置 × 10 signals × 1s ≈ 2,000 rows/s，窄表行數高於寬表——以批次寫入 + day-one 壓縮承受；查詢延遲超標時以 1 分鐘 continuous aggregate 後備（PRD-0006 §14 Q2）。
- 寬表與窄表長期雙軌；單軌化（ingest-generic 取代 telegraf）另議（PRD-0006 §14 Q4）。
- retention 數值未定（Open Question）；壓縮率目標 ≥5x，實測後定。
