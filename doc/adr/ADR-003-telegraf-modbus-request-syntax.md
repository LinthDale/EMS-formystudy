# ADR-003：Telegraf 採用 `[[inputs.modbus.request]]` 新版語法

## Status
Accepted（2026-04-22）

## Context

gateway 服務以 Telegraf 1.30 把 Modbus holding register 轉成 MQTT 訊息。Telegraf `inputs.modbus` plugin 同時支援兩種設定語法：

1. **Legacy**：`holding_registers = [{ name = "...", byte_order = "ABCD", data_type = "FLOAT32", ... }]`
2. **新版**：`[[inputs.modbus.request]]` 區塊，每欄位明示 `address` / `type` / `output`

Stage 1 初始用 legacy 語法，發現 FLOAT32 解碼錯誤——`power_kw` 出現 `1112514027` 這種未轉成浮點的 raw bytes。問題出在 legacy 語法對 FLOAT32 的解碼邏輯不完整，且除錯訊息少。

## Decision

所有 Telegraf Modbus 設定改用 **`[[inputs.modbus.request]]` 新版語法**：

```toml
[[inputs.modbus.request]]
  slave_id = 1
  byte_order = "ABCD"
  register = "holding"
  fields = [
    { address = 0, name = "voltage",   type = "INT16",   scale = 0.1, output = "FLOAT64" },
    { address = 2, name = "power_kw",  type = "FLOAT32", output = "FLOAT64" },
  ]
  tags = { device_id = "sim-001" }
```

每個欄位明示 `address`、`type`（線上格式）、`output`（解碼後格式），不依賴 plugin 內部猜測。

適用範圍：
- `services/gateway/telegraf.conf`
- `services/kc-gateway/telegraf.conf`
- 未來所有新增 Modbus 設備接入

## Consequences

**正面**
- FLOAT32 / INT16 / UINT16 解碼結果穩定且可預測
- 設定可讀性高（一個 fields = 一張 register map）
- 除錯訊息明確（哪個 address、什麼 type 失敗）
- 同一 conf 可分多個 `request` 區塊處理 holding / input / coil

**負面**
- 設定行數較長（每欄位一行 vs legacy 的密集陣列）
- 與舊文件 / 舊範例不相容，搜尋網路答案要過濾

**後續觸發**
- 接入新設備時，register map 直接寫入 `fields = [...]`，不得回退使用 legacy 語法
- 若未來 Telegraf 棄用 legacy（已預告），既有設定無遷移成本
