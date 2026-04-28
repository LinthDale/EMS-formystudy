# synaiq EMS — MVP

自建 EMS（Energy Management System）的工程碼，依 `自學架構.md` 的 Stage 定義逐步推進。現在專案已從單一路徑的電力資料管線，擴充到 Grafana 監控、Telegram 告警基礎，以及 KC 工廠環境 / 設備狀態資料整合。

## 現在進度：**Stage 2 已完成，Stage 3 部分完成，KC integration Phase 1-6 已完成**

目前可用能力：

| 區塊 | 狀態 | 說明 |
|------|------|------|
| Stage 1：電力資料管線 | ✅ 完成 | simulator → gateway → MQTT → ingest → TimescaleDB → PostgREST |
| Stage 2：Grafana / 告警基礎 | ✅ 完成 | Grafana dashboard 已 provision，Telegram alertmanager 設定已納入環境變數 |
| Stage 3：裝置服務 / 控制面 | 🟡 部分完成 | KC MCP server 已可透過 MCP client 讀寫 Modbus simulator；device-service CRUD / gateway reload 尚未完成 |
| KC integration Phase 1-6 | ✅ 完成 | KC 外部來源、Modbus / MQTT simulator、Telegraf ingest、factory table、MCP server、Grafana 工廠視覺化已整合 |

目前共有 12 個容器：原本 EMS 電力管線 7 個，加上 KC 工廠資料與 MCP 控制 5 個。

## 系統架構

### 電力資料管線

```text
┌──────────┐   Modbus   ┌─────────┐   MQTT   ┌────────┐   SQL   ┌─────────────┐   HTTP   ┌────────────┐
│simulator │ ─── TCP ──▶│ gateway │ ───────▶│ ingest │ ──────▶│ TimescaleDB │ ───────▶│ PostgREST  │
│ 假電表   │    :5020    │Telegraf │          │Telegraf│        │             │          │ query :3001│
└──────────┘            └─────────┘          └────────┘        └─────────────┘          └────────────┘
                                                                      │
                                                                      ▼
                                                               ┌────────────┐
                                                               │ Grafana    │
                                                               │ :3000      │
                                                               └────────────┘
```

### KC 工廠資料與 MCP 控制管線

```text
┌────────────────┐   Modbus   ┌────────────┐   MQTT   ┌────────────┐   SQL   ┌────────────────────┐
│kc-modbus-sim   │ ─── TCP ──▶│kc-gateway  │ ───────▶│kc-ingest   │ ──────▶│factory_measurements│
│factory_plc     │    :5021    │Telegraf    │          │Telegraf    │        │TimescaleDB table   │
└────────────────┘            └────────────┘          └────────────┘        └────────────────────┘
        ▲
        │ MCP read/write
        │
┌────────────────┐
│kc-mcp-server   │  Streamable HTTP MCP endpoint: http://localhost:8765/mcp
└────────────────┘

┌────────────────┐
│kc-mqtt-sim     │  MQTT topic: kc/factory/sensor-001/measurements
└────────────────┘
```

KC 工廠資料的 Grafana 視覺化不沿用電力圖表邏輯，而是依主流工廠環境監測做法分成：即時狀態 gauge、環境趨勢 time series、設備狀態 state timeline、最新資料 table。

## 快速入口

| 入口 | URL / 指令 | 用途 |
|------|------------|------|
| Grafana | <http://localhost:3000/d/ems-overview> | EMS Overview dashboard，含電力與 KC 工廠視覺化 |
| PostgREST：電力資料 | <http://localhost:3001/electricity_measurements?order=time.desc&limit=10> | 查詢歷史電力資料 |
| PostgREST：工廠資料 | <http://localhost:3001/factory_measurements?order=time.desc&limit=10> | 查詢 KC 溫度、濕度、壓力、馬達、Pump、Valve |
| Simulator health | <http://localhost:8001/health> | 原 EMS 假電表健康檢查 |
| MCP endpoint | `http://localhost:8765/mcp` | MCP client 使用，不是瀏覽器頁面 |

MCP endpoint 用最新版 Chrome 直接打開會看到 `Not Acceptable: Client must accept text/event-stream`，這是正常的；它需要 MCP client 以 `Accept: application/json, text/event-stream` 連線。

## 啟動

```bash
# 第一次跑先複製環境變數
cp .env.example .env

# 編輯 .env 填入你的實際值
# 至少確認 POSTGRES_PASSWORD、AUTHENTICATOR_PASSWORD
# 若要 Telegram 告警，再確認 TELEGRAM_BOT_TOKEN、TELEGRAM_CHAT_ID

docker compose up -d
```

等約 30 秒讓所有容器起來。可以用：

```bash
docker compose ps
```

若 KC 外部來源或相關 Dockerfile 有修改，重建 KC 服務：

```bash
docker compose up -d --build kc-modbus-sim kc-mqtt-sim kc-gateway kc-ingest kc-mcp-server
```

## 驗收

### 1. simulator 活著

```bash
curl http://localhost:8001/health
# 期望：{"status":"ok"}

curl http://localhost:8001/config
# 期望：看到 power_base_kw、period_seconds 等參數
```

### 2. MQTT 有資料在流

需要 `mosquitto-clients`。Windows / WSL 若沒有安裝，可以直接用 mosquitto 容器內建 client。

```bash
# 電力資料
docker exec -it ems-mosquitto mosquitto_sub -t 'ems/#' -v

# KC 工廠資料
docker exec -it ems-mosquitto mosquitto_sub -t 'kc/#' -v
```

電力資料會類似：

```text
ems/devices/sim-001/measurements electricity_measurements,device_id=sim-001 voltage=220.3,current=10.1,power_kw=52.4,energy_kwh=0.014 1682000000000000000
```

KC 工廠資料會類似：

```text
kc/factory/factory_plc/measurements factory_measurements,device_id=factory_plc temperature_c=28.1,humidity_pct=61.5,pressure_kpa=101.3,motor_rpm=1450,pump_on=true,valve_open=false 1682000000000000000
```

### 3. DB 有資料落地

```bash
# 電力資料
docker exec -it ems-timescaledb psql -U postgres -d ems -c \
  "SELECT time, device_id, voltage, power_kw FROM electricity_measurements ORDER BY time DESC LIMIT 5;"

# KC 工廠資料
docker exec -it ems-timescaledb psql -U postgres -d ems -c \
  "SELECT time, device_id, temperature_c, humidity_pct, pressure_kpa, motor_rpm, pump_on, valve_open FROM factory_measurements ORDER BY time DESC LIMIT 5;"
```

### 4. REST API 拿得到歷史資料

```bash
curl 'http://localhost:3001/electricity_measurements?order=time.desc&limit=10'
curl 'http://localhost:3001/factory_measurements?order=time.desc&limit=10'
```

電力資料每筆應含 `time`、`device_id`、`voltage`、`current`、`power_kw`、`energy_kwh`。KC 工廠資料每筆應含 `time`、`device_id`、`temperature_c`、`humidity_pct`、`pressure_kpa`、`motor_rpm`、`pump_on`、`valve_open`。

### 5. Grafana dashboard 有更新

Grafana 預設入口：

```text
http://localhost:3000/d/ems-overview
```

預設帳密若未變更為：

```text
admin / admin
```

Dashboard 應包含 `KC 工廠環境與設備狀態` row，裡面有溫度、濕度、壓力、馬達轉速、Pump / Valve 狀態、趨勢圖、狀態時間軸與最新資料表。

如果檔案已更新但 UI 還沒變，可重載 Grafana provisioning：

```bash
curl -u admin:admin -X POST http://localhost:3000/api/admin/provisioning/dashboards/reload
```

### 6. MCP server 可由 MCP client 連線

MCP endpoint：

```text
http://localhost:8765/mcp
```

MCP Inspector 建議設定：

```text
Transport: Streamable HTTP
URL: http://localhost:8765/mcp
Command / Args / Environment: 留空
```

啟動 Inspector：

```bash
npx @modelcontextprotocol/inspector
```

Chrome 直接打開 endpoint 不是有效測試，因為 MCP server 不是一般網頁。

## 除錯

### 某個服務起不來？

```bash
docker compose ps                  # 看哪個 container 掛了
docker compose logs <服務名>        # 看該服務的日誌
docker compose logs -f ingest      # 持續追蹤原 EMS ingest
docker compose logs -f kc-ingest   # 持續追蹤 KC ingest
```

### 常見問題

| 症狀 | 可能原因 | 解法 |
|------|---------|------|
| query 回 401 / 500 | authenticator 密碼跟 init 時不一致 | 砍資料卷重建：`docker compose down -v && docker compose up -d` |
| MQTT `ems/#` 空空 | gateway 連不到 simulator | 看 `docker compose logs gateway` 是否有 connection refused |
| MQTT `kc/#` 空空 | kc-gateway 或 kc-mqtt-sim 未正常送資料 | 看 `docker compose logs kc-gateway kc-mqtt-sim` |
| DB 沒電力資料 | ingest 沒認證成功 / MQTT 沒收到 | `docker compose logs ingest` 找錯誤 |
| DB 沒 KC 工廠資料 | kc-ingest 沒收到 MQTT 或寫入 DB 失敗 | `docker compose logs kc-ingest`，再查 `kc/#` topic |
| `/electricity_measurements` 回 `[]` | DB 真的還沒資料 / PostgREST schema 設定錯 | 先確認 simulator、MQTT、DB 三步都通 |
| `/factory_measurements` 回 `[]` | KC 資料尚未進 DB / migration 未跑 | 查 `factory_measurements` table 是否存在，並看 `kc-ingest` log |
| Grafana 看不到 KC row | dashboard provisioning 尚未重載 / 瀏覽器快取 | 呼叫 provisioning reload API，或重啟 `grafana` |
| Chrome 打開 `/mcp` 顯示 Not Acceptable | 直接用瀏覽器打 MCP endpoint | 改用 MCP Inspector，Transport 選 Streamable HTTP |
| MCP Inspector 連不上 | URL / Transport 填錯，或 kc-mcp-server 未啟動 | URL 用 `http://localhost:8765/mcp`，並查 `docker compose logs kc-mcp-server` |

### 完全重來（砍掉資料庫重建）

```bash
docker compose down -v
docker compose up -d
```

注意：這會刪除 TimescaleDB volume，歷史資料會消失。

## 服務對照表

| 服務 | 對外 Port | 用途 | 用什麼開源工具 | 自寫程式？ |
|------|----------|------|--------------|-----------|
| simulator | 5020 (Modbus), 8001 (REST) | 假電表 | Python + pymodbus + FastAPI | ✅ 自寫 |
| gateway | — | 電力 Modbus → MQTT | Telegraf | ❌ 只 config |
| mosquitto | 1883 | MQTT broker | Eclipse Mosquitto | ❌ |
| ingest | — | 電力 MQTT → DB | Telegraf | ❌ 只 config |
| timescaledb | 5432 | 時序資料庫 | TimescaleDB | ❌ |
| query | 3001 | 歷史查詢 REST API | PostgREST | ❌ 只 config |
| grafana | 3000 | 儀表板與告警 UI | Grafana | ❌ 只 config / dashboard JSON |
| kc-modbus-sim | 5021 | KC factory_plc Modbus simulator | Python + pymodbus | 外部來源，含本地相容性修正 |
| kc-mqtt-sim | — | KC sensor MQTT simulator | Python | 外部來源 |
| kc-gateway | — | KC Modbus → MQTT | Telegraf | ❌ 只 config |
| kc-ingest | — | KC MQTT → factory_measurements | Telegraf | ❌ 只 config |
| kc-mcp-server | 8765 (127.0.0.1) | MCP read/write Modbus simulator | FastMCP / Python | 外部來源，含本地相容性修正 |

## 資料夾結構

```text
.
├── README.md                         # 專案快速入口與目前進度
├── project_rules.md                  # 專案規定；重要變更後需同步文件
├── docker-compose.yml                # 一條龍啟動 12 個容器
├── .env.example                      # 環境變數範本
├── api/
│   └── openapi.yml                   # PostgREST API 文件，含 electricity / factory measurements
├── config/
│   └── mcp-devices.yaml              # KC MCP server device 設定
├── doc/
│   ├── 操作手冊.md                   # 主要操作文件，含 MCP / Grafana / REST / MQTT / DB
│   ├── 容器速查表.md                 # 12 個容器職責、端口、log、重建方式
│   └── plan/
│       └── kc_integration_plan.md    # KC integration plan 與 phase 追蹤
├── external/
│   ├── kc_iot_gateway/               # KC MQTT simulator 外部來源 clone
│   └── kc_modbus_mcp/                # KC Modbus simulator / MCP server 外部來源 clone
├── infra/
│   ├── timescaledb/
│   │   ├── init.sql                  # 建表、hypertable、api schema
│   │   ├── 000_rename_measurements.sql
│   │   ├── 001_add_factory.sql       # factory_measurements hypertable
│   │   └── 02-authenticator.sh       # 建 PostgREST 用的 role（用 env var）
│   ├── mosquitto/
│   │   └── mosquitto.conf
│   └── grafana/
│       └── provisioning/             # datasource / dashboard provisioning
└── services/
    ├── simulator/                    # 原 EMS 假電表，自寫
    ├── gateway/
    │   └── telegraf.conf             # 原 EMS 電力 Modbus → MQTT
    ├── ingest/
    │   └── telegraf.conf             # 原 EMS 電力 MQTT → DB
    ├── kc-gateway/
    │   └── telegraf.conf             # KC factory_plc Modbus → MQTT
    └── kc-ingest/
        └── telegraf.conf             # KC factory MQTT → DB
```

## 外部來源與本地修正

EMS 目錄目前不是 git repo，因此 KC 來源目前放在 `external/` 下作為一般 clone，尚未轉成 git submodule。

| 來源 | 目前用途 | 已知本地修正 |
|------|----------|--------------|
| `external/kc_iot_gateway` | `kc-mqtt-sim` | 作為 KC sensor MQTT simulator 來源 |
| `external/kc_modbus_mcp` | `kc-modbus-sim`、`kc-mcp-server` | 鎖定 `pymodbus>=3.7.0,<3.13`，並調整 simulator data block 起始位址以符合讀值 |

若未來 EMS 初始化成 git repo，可以再把這兩個來源轉成 submodule，避免外部來源版本不可追蹤。

## 文件索引

| 文件 | 用途 |
|------|------|
| `project_rules.md` | 專案規定；完成重要 plan 後需同步 API、操作、容器與相關文件 |
| `doc/操作手冊.md` | 主要操作流程，已整合 KC、Grafana、MCP，不是貼在結尾 |
| `doc/容器速查表.md` | 12 個容器的端口、職責、log、重建與安全基線 |
| `api/openapi.yml` | PostgREST API schema，含 `electricity_measurements` 與 `factory_measurements` |
| `doc/plan/kc_integration_plan.md` | KC integration phase 進度與驗收狀態 |

## 下一步：Stage 3

下一步不是再做 Stage 2；Grafana dashboard 已包含 KC 工廠環境與設備狀態。接下來應補 Stage 3 的裝置管理與控制面：

1. 建立 device-service 的裝置 CRUD API。
2. 讓 gateway / Telegraf 設定可依裝置清單產生或 reload。
3. 把 MCP 可讀寫 simulator 的能力納入更完整的控制流程與權限邊界。
4. 補上對應 OpenAPI、操作手冊、容器速查與 plan 追蹤。
