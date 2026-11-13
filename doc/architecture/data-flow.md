# Data Flow Diagram

2026-11-13 [ADR-045](../adr/ADR-045-newest-first-edge-retention.md)：本地容量淘汰＋新量測同交易，淘汰不經中央ACK、不記送達；[子集資料流](edge-committed-telemetry.md)已更新。schema3、wire2，中央去重路徑不變，未切共享部署。

> 範圍：關鍵業務流程的資料流向。實線 = 同步、虛線 = 非同步 / event-driven。

2026-11-12 [v2 committed telemetry 資料流](edge-committed-telemetry.md)：SQLite先存、PUBACK保留、receipt及投影同交易、commit後ACK、當前session驗證後刪；與下方 v1 Telegraf 路徑隔離。只私有驗證，原共享長測維持 v1。

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
| MQTT → Ingest → DB | 非同步、5s flush buffer | 非durable端到端保證 | ingest 強殺 → 丟最後 5 秒 buffer |
| Query / Grafana → DB | 同步 | Read-after-write | DB 慢 → 查詢逾時 |
| Grafana → Telegram | 非同步 | Best-effort | Telegram 不可達 → 告警丟（無重試佇列） |
| MCP → Modbus | 同步 | Strong（單次寫） | 設備斷線 → tool call 失敗 |

## 邊界備註

- ILP timestamp 由採集端提供：既有Telegraf gateway使用採集時間；Delta edge使用來源UTC時間且重送不改。MQTT broker不產生或改寫ILP時間戳
- TimescaleDB 為 hypertable，**append-only**；資料不可變更，僅可整批刪除（保留期管理）
- 以目前init.sql為準，electricity_measurements沒有PRIMARY/UNIQUE key；重複時間可能新增重複列，不能宣稱最後到者覆寫或exactly-once

## 2026-09-23 歷史查詢擴充（ADR-027）
既有資料流不变：Browser → BFF（OPS session）→ device-service（gateway解析）→ PostgREST（唯讀RPC）→ TimescaleDB。新增有界history/records，無OT控制、無新容器、無既有table修改；詳PRD-0018。
### 示範通知（PRD-0019）
`POST /api/alarms/demo {request_id:UUID4}` → session/OPS/Origin/schema → 全域冷卻與 UUID 去重 → Telegram sendMessage → 驗證 HTTP 200 + ok + message_id + chat.id → 回傳 sent/固定錯誤。8 秒上限、不自動重送；GET 僅回最近十筆成功紀錄與冷卻，重啟清空。
### 展位訪客綁定（PRD-0024 / ADR-036）
訪客手機 → Telegram（`/start <code>`、`/stop`）⇠ BFF 背景任務 getUpdates 長輪詢（出站拉取，offset 存 SQLite）→ 驗證私人對話／code／時效／頻率 → 寫入唯一綁定（volume `demo_alarm_state`）→ sendMessage 確認。按鈕 POST 時於冷卻鎖內解析目前綁定：有效 → 訪客三行文字＋當日號碼（ACK 或逾時才計入，HMAC 每日 key）；否則 → 固定對象原訊息。GET 每 4 秒回 deep link（輪替 code）、遮罩名稱與當日人數。資料不進 TimescaleDB；無新入站路徑。

## Delta 來源時間與斷線回補（PRD-0020 / ADR-029）
Delta→FC04 parser→來源UTC時間→SQLite→QoS1 MQTT→既有Telegraf→DB→BFF/Monitor。採集和sender分執行緒；重送保留payload與時間，只有對應PUBACK才刪除。PUBACK非資料庫commit，既有ingest buffer仍可能丟失、DB仍可能重複。僅持久化L1 V/A、總kW、累計kWh；其他decoded資料止於CLI/未ACKsnapshot。

### RTU 模擬資料流（ADR-031）
Pi主站FC04 request → USB–RS485 #2 → bus → PC USB–RS485 #1 → simulator從站 → raw registers + RTU CRC原路回應 → Pi既有parser → SQLite → MQTT → 後台 → EMS。站號1–247單一站；其他站號/廣播/錯CRC不回應，非法讀寫不能改資料。後續PUBACK/DB限制沿用ADR-029。

### 統一 simulator 控制（ADR-033，取代流程五的模擬器寫入）
OPS + Origin + typed command/CAS → BFF SQLite commit intent → 內部token agent → atomic apply/revision/receipt → SQLite commit outcome。
timeout/crash → unknown、封鎖該台後續指令；receipt證明成功才補記，換instance只解除封鎖不假稱成功。查詢目前設定相同不算對帳證據。
既有電表/PLC/sensor/Delta上行topic及schema不改；applied不表示遙測已落DB。PLC原有不同register request會產生分欄資料列，查單欄最新值須排除不含該欄的資料列。

## PRD-0023：帳號與 session

```mermaid
sequenceDiagram
  participant U as 使用者
  participant B as BFF
  participant D as PostgreSQL
  U->>B: 密碼登入
  B->>D: account id/hash/role/version 同一快照
  B->>B: bounded Argon2 verify
  B-->>U: session cookie
  U->>B: 受保護請求
  B->>D: enabled/id/version/role 查核
  B-->>U: 有效回應，失效401，DB故障503
```
管理異動與 audit 共用 transaction；READ COMMITTED + advisory lock 防止最後 OPS 並行停用。Argon2 工作完成後才釋放slot，HTTP取消不提前解除資源上限。


## 2026-11-10 演進設計：即時狀態與歷史分路（尚未實作）



S1–S4 只連隔離模擬器；7 天歷史回補不得刷新控制快照。PRD-0006 的時間 fallback 與 PRD-0021 的保留來源時間，需按新 PRD §12 在實作前整合；不改目前 v1 管線。受理、達成及 unknown 分開，不因網路 ACK 就宣稱設備完成。





### ADR-041採集有效性更新（2026-11-12）

RTU可能送出請求後遇不確定回覆，整筆sample丟棄並鎖定，沒有SQLite commit／MQTT假值。未知上界停採；有核定時限隔離後換client/framer及清buffer再讀完整sample；field啟動也隔離。既有可信SQLite→MQTT流程維持、PUBACK仍不是DB committed ACK。詳[ADR-041](../adr/ADR-041-rtu-uncertainty-and-bounded-recovery.md)。

### 2026-11-13 DB／WAL TLS與還原準入

沿原receiver→PostgreSQL與PostgreSQL→WAL archive連線，field雙向驗證TLS；WAL ACK須唯一同步ems_wal_archive、TLS＋client DN且flush覆蓋固定LSN。021新函式缺失拒絕，不回舊版。維運backup_preflight先tar layout／資源界限，再外置可信cluster ID＋checksum，最後PG真recovery至核定timeline／target；滿載保留原slot修復，不降級。依[ADR-050](../adr/ADR-050-database-tls-and-recovery-identity.md)，[55案／相鄰回歸證據](../../output/no-pi-wal-security-20261113/README.md)；元件及wire2/schema3不變，正式異失效域／Pi另驗。

2026-11-13：[ADR-051](../adr/ADR-051-pinned-recovery-and-slot-reseed.md) 僅補維運還原準入：外置核定timeline／target、slot先reserve→basebackup→新archive接手→真新鏈PITR驗證→generation換代／重新開ACK；沿原元件／資料流，無新增自動reseed/failover服務。中央資料滿與同ID分支短測已驗，[證據](../../output/no-pi-critical-closure-20261113/README.md)。
