# Architecture Diagrams

> 對齊：`doc/PRD-架構設計-Guideline.md` §3.1（C4 Model）

本目錄收錄 EMS 系統三層架構圖：

| 檔案 | C4 層級 | 用途 |
|------|--------|------|
| [`c4-context.md`](c4-context.md) | Level 1 — System Context | 系統與外部 Actor / System 的關係 |
| [`c4-container.md`](c4-container.md) | Level 2 — Container | 服務、資料庫、佇列、外部 API 的部署單位 |
| [`data-flow.md`](data-flow.md) | Data Flow | 關鍵業務流程的資料流向（含同步 / 非同步標記） |

## 維護規則

- 所有圖採 **Mermaid**（GitHub / VS Code 可直接渲染，無需外部工具）
- 同步呼叫：實線；非同步（MQTT / Queue）：虛線
- 跨網段邊界（OT/IT、Public/Private）以 subgraph 框出
- 任何 `docker-compose.yml`、`services/*`、外部整合的變更，必須同步更新對應圖
