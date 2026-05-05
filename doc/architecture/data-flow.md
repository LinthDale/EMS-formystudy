# Data Flow Diagram

> 範圍：關鍵業務流程的資料流向。實線 = 同步、虛線 = 非同步 / event-driven。

## 流程一：量測資料上行（電表）

```mermaid
sequenceDiagram
    autonumber
    participant SIM as ems-simulator<br/>(假電表)
    participant GW as ems-gateway<br/>(Telegraf)
    participant MQ as ems-mosquitto
    participant IN as ems-ingest<br/>(Telegraf)
    participant DB as ems-timescaledb
    participant API as ems-query<br/>(PostgREST)
    participant GF as ems-grafana
    participant USER as 使用者

    Note over SIM,GW: 同步輪詢（1s 週期）
    GW->>SIM: Modbus TCP read holding<br/>(voltage, current, power_kw, energy_kwh)
    SIM-->>GW: 4 個 register 值

    Note over GW,MQ: 非同步發布（ILP）
    GW-)MQ: PUBLISH ems/devices/sim-001/measurements<br/>(QoS 1)

    Note over MQ,IN: 非同步訂閱
    MQ-)IN: deliver message
    IN->>DB: INSERT INTO public.electricity_measurements
    DB-->>IN: ack

    Note over USER,API: 同步查詢
    USER->>API: GET /electricity_measurements?...
    API->>DB: SELECT FROM api.electricity_measurements
    DB-->>API: rows
    API-->>USER: JSON

    Note over USER,GF: 同步視覺化
    USER->>GF: 開儀表板
    GF->>DB: SELECT FROM public.electricity_measurements
    DB-->>GF: rows
    GF-->>USER: panel
```

## 流程二：工廠 PLC 資料上行

```mermaid
sequenceDiagram
    autonumber
    participant PLC as ems-kc-modbus-sim<br/>(PLC 模擬)
    participant SENSOR as ems-kc-mqtt-sim<br/>(JSON 感測器)
    participant KGW as ems-kc-gateway
    participant MQ as ems-mosquitto
    participant KIN as ems-kc-ingest
    participant DB as ems-timescaledb

    par PLC 路徑
        KGW->>PLC: Modbus TCP read<br/>(holding/input/coil)
        PLC-->>KGW: temperature, humidity, motor_speed,<br/>pressure, pump_on, valve_open
        KGW-)MQ: PUBLISH factory/devices/plc-001/measurements (ILP)
    and Sensor 路徑
        SENSOR-)MQ: PUBLISH factory/devices/sensor-001/measurements (JSON)
    end

    MQ-)KIN: deliver factory/devices/+/measurements
    KIN->>DB: INSERT INTO public.factory_measurements
    DB-->>KIN: ack
```

## 流程三：告警觸發與通知

```mermaid
sequenceDiagram
    autonumber
    participant DB as ems-timescaledb
    participant GF as ems-grafana<br/>(Alerting)
    participant TG as Telegram Bot API
    participant ONCALL as 值班工程師

    loop 每 1 分鐘評估
        GF->>DB: SELECT avg(power_kw)<br/>WHERE time > now() - 5m
        DB-->>GF: value
        alt value > 100 kW
            GF->>GF: state: pending → firing
            GF-)TG: POST sendMessage<br/>(chat_id, alert text)
            TG-)ONCALL: 推播
        end
    end
```

## 流程四：Demo 訪客存取（Cloudflare Tunnel）

```mermaid
sequenceDiagram
    autonumber
    participant USER as Demo 訪客
    participant CF as Cloudflare<br/>(Access + Tunnel edge)
    participant CFD as cloudflared<br/>(host daemon)
    participant GF as ems-grafana

    USER->>CF: GET https://ems-demo.synaiq-ai.com
    CF-->>USER: 重定向到 Access login
    USER->>CF: 輸入 email
    CF-)USER: 寄送 One-time PIN
    USER->>CF: 提交 PIN
    CF->>CF: 簽發 session cookie
    USER->>CF: 帶 cookie 重新請求
    CF->>CFD: 透過 tunnel 轉發 (mTLS)
    CFD->>GF: HTTP localhost:3000
    GF-->>CFD: HTML / JSON
    CFD-->>CF: response
    CF-->>USER: response
```

## 流程五：AI Agent 控制設備（MCP）

```mermaid
sequenceDiagram
    autonumber
    participant AI as AI Agent<br/>(Claude / MCP Client)
    participant MCP as ems-kc-mcp-server
    participant DEV as Modbus 設備<br/>(simulator / kc-modbus-sim)

    AI->>MCP: tool call: read_register(device, address)
    MCP->>DEV: Modbus TCP read
    DEV-->>MCP: value
    MCP-->>AI: tool result

    AI->>MCP: tool call: write_register(device, address, value)
    MCP->>DEV: Modbus TCP write
    DEV-->>MCP: ack
    MCP-->>AI: tool result
```

## 同步性與資料一致性摘要

| 路徑 | 模式 | 一致性等級 | 失效行為 |
|------|------|-----------|---------|
| Gateway → MQTT | 非同步、QoS 1 | At-least-once | broker 重啟 → 短時暫存後續傳，重啟期間發布的訊息可能丟 |
| MQTT → Ingest → DB | 非同步、5s flush buffer | At-least-once | ingest 強殺 → 丟最後 5 秒 buffer |
| Query / Grafana → DB | 同步 | Read-after-write | DB 慢 → 查詢逾時 |
| Grafana → Telegram | 非同步 | Best-effort | Telegram 不可達 → 告警丟（無重試佇列） |
| MCP → Modbus | 同步 | Strong（單次寫） | 設備斷線 → tool call 失敗 |

## 邊界備註

- 所有 ILP timestamp 採 broker 端產生（Telegraf 預設），非設備端時間
- TimescaleDB 為 hypertable，**append-only**；資料不可變更，僅可整批刪除（保留期管理）
- 所有 measurement 表的 `time` 欄為 PRIMARY KEY 一部分，重複時間 ingest 會以最後到者為準（PostgREST 寫入路徑暫關閉，因此實務不會發生衝突）
