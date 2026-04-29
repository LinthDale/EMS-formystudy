# ADR-007：MQTT Topic 命名規範

## Status
Accepted（2026-04-22；v3 修訂於 2026-04-29，校正為實際實作）

## Context

MQTT broker 為 EMS 資料管線的中樞。所有 gateway 發布、所有 ingest 訂閱，topic 命名直接影響：
- 訂閱通配符精準度
- 多場域擴展時的隔離與 ACL 設計
- 對外 / 對內權限策略

需要從 Day 1 訂規範，否則後期改名牽動所有 gateway / ingest / 測試。

## Decision

### 主規範（gateway 發布、Telegraf 來源）

```
ems/<domain>/{device_id}/measurements
```

其中：
- `<domain>` ∈ { `devices`（電表）, `factory`（工廠 PLC） }，未來可加 `solar`、`storage`、`grid` 等
- `{device_id}` 採 kebab-case
- 結尾固定 `measurements`，保留未來 `commands`、`events` 子層擴展

實況對照：

| 來源 | 實際 topic | 設定檔 |
|------|-----------|--------|
| ems-gateway（電表） | `ems/devices/sim-001/measurements` | `services/gateway/telegraf.conf` |
| kc-gateway（工廠 PLC） | `ems/factory/plc-001/measurements` | `services/kc-gateway/telegraf.conf` |

Payload：Influx Line Protocol（兩者皆然）。

### 例外：第三方 JSON sensor

```
factory/sensor/temp_01
```

外部 KC MQTT simulator 直發 JSON、不經 Telegraf；topic 沿用其上游格式，由 `kc-ingest` 透過 `mqtt_consumer.json_v2` 解析後寫入 `factory_measurements`，並補 tag `device_id = "sensor-001"`、`device_type = "sensor"`。

此例外為**有意保留**：第三方來源不強行重命名以避免改 KC 上游 repo；但**新增的內部 sensor 必須遵循主規範**。

### 訂閱建議

- 全 ems 域 PLC + 電表：`ems/+/+/measurements`
- 僅電表：`ems/devices/+/measurements`
- 僅工廠 PLC：`ems/factory/+/measurements`
- 第三方 JSON sensor：明示完整 topic（如 `factory/sensor/temp_01`）

## Consequences

**正面**
- `ems/<domain>/...` 前綴讓多場域擴展與 ACL 切分明確
- 訂閱通配符精準（`ems/devices/#` 不會撈到 factory）
- 對應 ADR-006 的物理隔離原則

**負面**
- 第三方 JSON sensor 命名與主規範不一致；需於每處文件明示為例外
- 既有 `factory/sensor/temp_01` 為單一 hard-coded topic（非 device-id 變數），不利擴展
- README 舊版誤記為 `kc/factory/...`，待同步更正

**Open Issue**
- **R-013**（風險登記）：第三方 sensor topic 與主規範不一致；長期應評估 Telegraf 中間層重新發布到 `ems/factory/sensor-001/measurements` 達到統一
- README 與本 ADR 校正：本次 v3 修訂同步處理

**後續觸發**
- 新增內部設備一律遵循 `ems/<domain>/{device_id}/measurements`
- 新增第三方來源走 `mqtt_consumer.json_v2` + tag override 模式
- 啟用 Mosquitto ACL 時，按 `ems/<domain>` 切權限
- `commands` 子層上線時新增專屬 ADR 規範格式
