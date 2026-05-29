# Product Requirements Documents (PRD)

> 對齊：`doc/PRD-架構設計-Guideline.md` §2 標準章節結構

## 索引

| # | 標題 | 狀態 | 對應實作 |
|---|------|------|---------|
| [PRD-0001](PRD-0001-Stage1-Stage2-Foundation.md) | EMS Stage 1 / Stage 2 基礎管線與儀表板 | Implemented | services/{simulator,gateway,ingest}, infra/{mosquitto,timescaledb,grafana} |
| [PRD-0002](PRD-0002-KC-Factory-Integration.md) | KC Factory 工廠 PLC 整合 | Implemented (Phase 1-6) | services/{kc-gateway,kc-ingest}, external/{kc_iot_gateway,kc_modbus_mcp} |
| [PRD-0003](PRD-0003-Device-Registry-Auto-Discovery.md) | Device Registry & Auto-Discovery — 裝置自動登錄與 AI 輔助分類 | **Approved**（2026-05-08）| services/device-service（待實作） |

> 既有 `doc/archive/plan/EMS實作計畫.md` 與 `doc/archive/plan/kc_integration_plan.md` 為**原始規劃文件**（過程紀錄、取捨討論），保留於 archive 下不刪除；PRD-0001 / PRD-0002 為對應的**正式 PRD 形式**，提供 Guideline 15 章節結構。兩者衝突時以 PRD 為準。

## 撰寫規則

- 檔名：`PRD-NNNN-kebab-case-title.md`
- 結構：嚴格遵循 Guideline §2 的 15 章節（必填 13 + 選填 2）
- 狀態值：`Draft` / `Reviewed` / `Approved` / `Implemented` / `Deprecated`
- 鎖定後（Approved 之後）的變更走 ADR，不修改 PRD 主體；可在「附錄」加變更註記指向 ADR

## PRD 提交前自查

於 PR 描述勾選 Guideline §10 完整 checklist，缺項說明理由。
