# ADR-006：KC Factory 鏈路獨立為 kc-gateway / kc-ingest

## Status
Accepted（2026-04-24）

## Context

引入 KC 外部專案（kc_iot_gateway、kc_modbus_mcp）整合工廠 PLC 與 MQTT JSON 感測器後，需決定如何接入既有 EMS 資料管線。

兩種選項：

**A. 共用既有 gateway / ingest**：
- 在 `services/gateway/telegraf.conf` 增加 `[[inputs.modbus]]` 區塊接 kc-modbus-sim
- 在 `services/ingest/telegraf.conf` 增加 MQTT topic 訂閱
- 一個 conf 容納電表 + 工廠

**B. 獨立 kc-gateway / kc-ingest 容器**：
- 各自一份 Telegraf conf、各自一個容器
- 與既有電表鏈路完全分離

選項 A 短期看似省容器，但：
- 一份 conf 容納兩種異質設備（電表 vs PLC）造成設定肥大、難讀
- 任一邊 bug 可能拖垮另一邊
- 工廠資料寫入 `factory_measurements` 表，與電表 `electricity_measurements` 命名對稱（v5 重新命名）；分流容器讓 owner 對應清楚
- 故障隔離：kc-gateway 掛掉不影響電表資料流

## Decision

採 **B：獨立容器**。新增：

| 容器 | 鏡像 | 職責 |
|------|------|------|
| `ems-kc-gateway` | telegraf:1.30 | kc-modbus-sim → MQTT topic `factory/devices/plc-001/measurements` |
| `ems-kc-ingest` | telegraf:1.30 | MQTT `factory/devices/+/measurements` → `factory_measurements` 表 |
| `ems-kc-modbus-sim` | 本地 build（external/kc_modbus_mcp） | 工廠 PLC 模擬器 |
| `ems-kc-mqtt-sim` | 本地 build（external/kc_iot_gateway） | MQTT JSON 感測器模擬 |
| `ems-kc-mcp-server` | 本地 build（external/kc_modbus_mcp） | MCP Server，讓 AI 控制設備 |

外部 repo 暫以一般 clone 置於 `external/`（EMS 目錄尚未初始化為 git repo，submodule 化為後續工作），docker-compose 本地 build image。

## Consequences

**正面**
- 故障隔離：電表 / 工廠任一邊掛掉互不影響
- 設定可讀：每份 conf 只描述一種設備類型
- 命名對稱：`gateway` ↔ `kc-gateway`、`ingest` ↔ `kc-ingest`、`measurements` ↔ `factory_measurements`
- 未來新場域（如太陽能、儲能）按相同模式擴展為 `solar-gateway` 等

**負面**
- 容器數量增加（+5 個）
- 外部來源版本管理目前依賴一般 clone（無 submodule pin），上游變更難以追蹤（風險登記 R-010）
- Telegraf conf 重複片段（mosquitto 連線、output 設定等）

**後續觸發**
- 新場域接入沿用此模式（一場域一組 gateway/ingest）
- 共用片段若惡化為大量重複，再評估抽出 conf 模板
- 新增表沿用對稱命名：`<domain>_measurements`

**取代既有決策**：v1 規劃曾考慮把 KC 整合進既有 gateway，本 ADR 取代之。
