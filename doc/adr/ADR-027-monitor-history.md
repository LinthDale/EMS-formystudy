# ADR-027：有界歷史趨勢與分頁原始紀錄
## Status
Accepted for local implementation（2026-09-23，使用者要求圖表與歷史紀錄）。
## Context
ADR-025 最新 1,000 筆無法代表完整指定區間。既有 Grafana 直接 SQL 聚合，但瀏覽器不能越過 BFF。PRD-0018 延伸 FR-520/521。
## Decision
新增 history / records 兩個 OPS-only BFF facade，既有 measurements 不變。history 由 PostgREST 的唯讀、SECURITY INVOKER RPC 聚合既有 api views；有界最多 7 天與 1200 桶。records 固定區間 + offset 分頁。不得使用 legacy domain operator pass-through 或把服務憑證交給瀏覽器。採用 ECharts 面板、範圍與放大互動。預覽沿用原有紙白/橄欖/金色品牌。
## Consequences
完整區間不再受 1,000 筆截斷；min/max 保存尖峰。新增可重複套用 migration 017（016 為窄表規劃保留）；不修改既有表或 retention。晚到資料可影響 offset 分頁，非交易快照。布林桶以最後狀態及 min/max 表示，不保證桶內每次切換細節，原始表可查。
