# ADR-012：device-service 自帶獨立 MCP endpoint（AI 通道僅讀 + 重跑分類）

## Status
Accepted（2026-05-29）

> 來源：PRD-0003 §6.4 / §8.2；DL-002（歸屬 A）、DL-003（移除 confirm_device）、DL-005（對齊 bounded autonomy）。

## Context

需提供半自動 fallback（G8）：低信心 candidate 由 Claude Code 透過 MCP 介入分類。兩個決策點：

1. **MCP endpoint 歸屬**：併入既有 `kc-mcp-server`，還是 device-service 自帶？
2. **AI 通道權限範圍**：MCP tool 能不能 confirm / override / reject 裝置？

可選方案（歸屬）：

| 方案 | 取捨 |
|------|------|
| A. device-service 自帶獨立 MCP endpoint（127.0.0.1:8766）| 部署解耦、權限自帶、與 kc-mcp 無耦合 ✅ |
| B. 併入 kc-mcp-server | 共用一個 MCP server，但跨 service 權限混雜、kc 與 device 生命週期綁死 ❌ |

## Decision

採 **方案 A**：device-service 自帶獨立 MCP server。

- **bind `127.0.0.1:8766`**（內網限定，不對外）
- 需 `X-API-Key=$AI_API_KEY`；缺 key 回 401
- 每次 tool call 寫 audit log
- **AI 通道僅 3 個 tool**（讀 + 重跑分類）：
  - `list_low_confidence_candidates`
  - `get_device_digest`
  - `classify_with_context`（強制 cache miss 重跑）
- **不開** `confirm` / `override` / `reject` / `ai-feedback`：嘗試呼叫不存在的 `confirm_device` 回 method-not-found
- confirm 類動作**只走 OPS REST**（`/confirm` `/override` `/reject`），由人類 OPS key 執行

**為何 AI 通道不開 confirm/override/reject**：這些是「人類最終決策」動作（§8.6.1 權限矩陣中歸 OPS）。AI 可自動推進 candidate->confirmed（信心 > 0.9，§8.6 bounded autonomy），但「推翻 / 確認 / 拒絕」屬人類保留權，避免 MCP 通道被當成繞過人類審核的後門。

## Consequences

**正面**
- device-service 與 kc-mcp 部署、權限、生命週期完全解耦
- MCP 通道權限最小化（只讀 + 重跑），即使 MCP client 被濫用也無法改裝置狀態
- 與 §8.6 bounded autonomy 一致：AI 自動推進是「本職」，confirm/reject 是「人類權」

**負面**
- 多一個 server process（多一份 port / 健檢 / audit）
- Claude Code 要對低信心 candidate 做決策，仍須走 OPS REST（多一步）

**已知風險**
- MCP endpoint 雖 bind localhost，仍需 X-API-Key 防同機其他 process 濫用

**後續觸發**
- MCP 控制寫入裝置的權限框架 → PRD-0005
- 容器速查表新增 MCP port 8766
