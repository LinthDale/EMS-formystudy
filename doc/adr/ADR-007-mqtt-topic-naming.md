# ADR-007：MQTT Topic 命名規範

## Status
Accepted（2026-04-22；v2 修訂於 2026-04-24，引入 KC factory）

## Context

MQTT broker 為 EMS 資料管線的中樞。所有 gateway 發布、所有 ingest 訂閱，topic 命名直接影響：
- 訂閱通配符的精準度（避免 `ems/#` 撈太廣）
- 多租戶 / 多場域擴展時的隔離
- 權限策略（未來啟用 ACL）

需要從 Day 1 訂規範，否則後期改名牽動所有 gateway / ingest / 測試。

## Decision

統一 topic 規範：

```
<domain>/devices/{device_id}/measurements
```

其中：
- `<domain>` ∈ { `ems`, `factory` }（未來可加 `solar`、`storage`、`grid` …）
- `{device_id}` 採 kebab-case（如 `sim-001`、`plc-001`、`sensor-001`）
- 結尾固定為 `measurements`（保留未來 `commands`、`events` 等子層擴展）

範例：
| Topic | 用途 |
|-------|------|
| `ems/devices/sim-001/measurements` | 電表（模擬） |
| `factory/devices/plc-001/measurements` | 工廠 PLC |
| `factory/devices/sensor-001/measurements` | 工廠 MQTT JSON 感測器 |

訂閱建議：
- 單一場域全設備：`ems/devices/+/measurements`
- 全場域全設備：`+/devices/+/measurements`
- 特定設備：`ems/devices/sim-001/measurements`

Payload 格式：
- 來自 Telegraf gateway：Influx Line Protocol（保留 tag / field / timestamp 完整語意）
- 來自外部 MQTT 設備（如 KC sensor）：JSON，由 ingest 端 parser 處理

## Consequences

**正面**
- 通配訂閱精準：`ems/#` 不會撈到 `factory/*`
- 多場域擴展只需新增 `<domain>` 前綴
- 未來加 ACL 時，每個 role 可限制 topic 前綴（如 KC 廠商只能發 `factory/devices/*`）
- 對應 ADR-006 的物理隔離原則

**負面**
- Topic 字串較長（vs. 扁平的 `sim-001`）
- 既有訂閱者改規則需同步調整（已於 v2 修訂時完成）

**後續觸發**
- 新增設備一律遵循此規範；不允許 ad-hoc topic
- 啟用 Mosquitto ACL 時，按 `<domain>` 切權限
- `commands` 子層上線時新增專屬 ADR 規範格式
- 此規範為 `api/openapi.yml` 的 MQTT 區段參照來源
