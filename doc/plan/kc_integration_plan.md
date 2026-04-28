# KC 外部專案整合計畫

> 建立日期：2026-04-24
> 修訂日期：2026-04-27（v5 — 既有 `measurements` 更名為 `electricity_measurements`，與 `factory_measurements` 對稱）
> 狀態：**Phase 1-6 已實作完成（Grafana 工廠視覺化已補齊）**
> 目標：將 kc_iot_gateway 和 kc_modbus_mcp 整合到 EMS，透過 git submodule 管理源碼，docker-compose 本地 build image

---

## 一、整合目標

1. **保留既有電表鏈路**：sim-001 的資料流不中斷，歷史資料不刪除
2. **納入外部 repo 源碼**：用 git submodule 管理，可獨立更新上游
3. **統一 Docker 管理**：所有 image 在 EMS 的 docker-compose 中建置
4. **擴展 Grafana**：在現有儀表板新增工廠感測器 panels
5. **預留 AI 擴展**：整合 MCP Server 讓 Claude 可以控制設備
6. **DB 命名統一**：既有 `measurements` 表更名為 `electricity_measurements`，與新增 `factory_measurements` 形成對稱命名（v5 新增）

---

## 二、外部 Repo 完整評估

### 2.1 kc_iot_gateway

**Repo**: https://github.com/KerberosClaw/kc_iot_gateway

**內含三個可獨立執行的元件**：

| 元件 | 入口檔 | 功能 | EMS 採用？ |
|------|--------|------|-----------|
| Modbus 模擬器 | `simulators/modbus_simulator.py` | 工廠 PLC（**pressure 不會動態變化**） | ❌ 不採用 |
| MQTT 模擬器 | `simulators/mqtt_simulator.py` | JSON 格式感測器（溫濕度） | ✅ 採用 |
| Gateway 主體 | `python -m src` | FastAPI + MCP + Dashboard + Rules | ⏸ 暫不採用 |

**採用理由**：
- MQTT 模擬器：唯一的 JSON MQTT 來源，示範 EMS 如何處理非 ILP 格式

**不採用理由**：
- Modbus 模擬器：pressure 欄位初始化為 1000 後 loop 中不會更新（見 simulators/modbus_simulator.py 第 49-63 行），只有 temperature 和 humidity 動態變化。改用 kc_modbus_mcp 的完整版
- Gateway 主體與 EMS 既有的 Telegraf gateway 功能重疊
- Rules engine 與 Grafana Alerting 功能重疊
- Dashboard 與 Grafana 功能重疊
- MCP Server 由 kc_modbus_mcp 提供就夠了

### 2.2 kc_modbus_mcp

**Repo**: https://github.com/KerberosClaw/kc_modbus_mcp

**內含兩個可獨立執行的元件**：

| 元件 | 入口檔 | 功能 | EMS 採用？ |
|------|--------|------|-----------|
| Modbus 模擬器 | `simulator.py` | 工廠 PLC，**完整動態更新**（含 pressure 隨機 900-1100） | ✅ 採用 |
| MCP Server | `server.py` | 讓 AI Agent 用自然語言讀寫 Modbus 設備 | ✅ 採用 |

**採用理由**：
- Modbus 模擬器：temperature、humidity、pressure 都會動態變化，驗收能真正測到 pipeline 端到端（參見 simulator.py 第 67-96 行）
- MCP Server：讓 Claude 可以用「讀取功率」之類的自然語言操作設備
- 同一個 Dockerfile build 的 image 可以同時跑 simulator.py 和 server.py

**Dockerfile**：單一 Dockerfile，同 image 跑兩個 command（kc-modbus-sim 和 kc-mcp-server）。

### 2.3 採用元件總覽

```
kc_iot_gateway repo
  ├── simulators/modbus_simulator.py  → 不採用（pressure 不動態）
  ├── simulators/mqtt_simulator.py     → EMS 的 kc-mqtt-sim 容器 ✅
  └── src/ (Gateway 主體)              → 不採用

kc_modbus_mcp repo
  ├── simulator.py                     → EMS 的 kc-modbus-sim 容器 ✅ (完整動態)
  └── server.py (MCP Server)           → EMS 的 kc-mcp-server 容器 ✅
```

### 2.4 Image 使用總覽（共用策略）

| Image | 從哪 build | 跑的容器（不同 command） |
|-------|-----------|----------------------|
| `ems-kc-iot-gateway:local` | `external/kc_iot_gateway/` | kc-mqtt-sim（只用它的 mqtt_simulator.py） |
| `ems-kc-modbus-mcp:local` | `external/kc_modbus_mcp/` | kc-modbus-sim + kc-mcp-server |

---

## 三、整合後架構

```
┌──────────────────────────────────────────────────────────────────────────┐
│                     EMS + KC Integration (Submodule + Docker)             │
└──────────────────────────────────────────────────────────────────────────┘

 外部 Submodule                    EMS 容器（從 submodule build）
┌────────────────────┐
│ external/          │          ┌─────────────────────────┐
│  kc_iot_gateway/   │──build──▶│ kc-mqtt-sim             │ ← build from
│   (只用 mqtt_sim)   │          │   (JSON MQTT 感測器)    │   kc_iot_gateway
└────────────────────┘          └───────────┬─────────────┘
                                            │ MQTT JSON
                                            ▼
┌────────────────────┐          ┌─────────────────────────┐
│ external/          │──build──▶│ kc-modbus-sim :5021     │ ← build from
│  kc_modbus_mcp/    │          │   (PLC 模擬器, 完整)    │   kc_modbus_mcp
│                    │          └───────────┬─────────────┘
│  (同一 image       │                      │ Modbus TCP
│   兩個 command)    │──reuse──▶┌─────────────────────────┐
│                    │          │ kc-mcp-server :8765     │ ← reuse same
│                    │          │   (AI Agent 介面)       │   image
└────────────────────┘          └─────────────────────────┘
                                             ▲ Modbus TCP
                                             │ (讀 simulator & kc-modbus-sim)
                                             │
                    ┌────────────────────────┘
                    │
            ┌───────┴──────┐      ┌──────────────┐
            │ ems-simulator│      │  Claude/AI   │
            │ :5020 (電表) │      │  (MCP Client)│
            └──────────────┘      └──────────────┘

 EMS 既有容器（不動）
 ┌──────────────┐     Modbus    ┌────────────┐     MQTT     ┌──────────┐
 │ems-simulator │ ─────:5020──▶│ems-gateway │ ───────────▶│mosquitto │
 └──────────────┘                └────────────┘              └─────┬────┘
                                                                   │
                              ┌────────────────────────────────────┘
                              │ (subscribe)
                  ┌───────────┴────────────┬────────────┐
                  ▼                        ▼            ▼
         ┌──────────────┐       ┌──────────────┐  ┌──────────────┐
         │ ems-ingest   │       │ kc-ingest    │  │ kc-mqtt-sim  │
         │ (電表 → DB)  │       │ (工廠 → DB)  │  │ (publish)    │
         └──────┬───────┘       └──────┬───────┘  └──────────────┘
                │                      │
                ▼                      ▼
         ┌──────────────────────────────────────────────────┐
         │             ems-timescaledb                      │
         │  electricity_measurements + factory_measurements │
         └──────────┬───────────────────────────────────────┘
                    │
         ┌──────────┴───────────┐
         ▼                      ▼
  ┌──────────────┐       ┌──────────────┐
  │ ems-grafana  │       │  ems-query   │
  │  (儀表板)    │       │ (REST API)   │
  └──────────────┘       └──────────────┘
```

---

## 四、目錄結構

```
EMS/
├── .gitmodules                          ← 新增
├── docker-compose.yml                   ← 修改
├── external/                            ← 新增
│   ├── kc_iot_gateway/                  ← submodule
│   │   ├── Dockerfile
│   │   ├── pyproject.toml
│   │   ├── simulators/
│   │   │   ├── modbus_simulator.py
│   │   │   └── mqtt_simulator.py
│   │   └── src/ (不使用)
│   └── kc_modbus_mcp/                   ← submodule
│       ├── Dockerfile
│       ├── pyproject.toml
│       ├── server.py
│       ├── devices.yaml
│       └── src/
├── services/
│   ├── simulator/                       ← 既有
│   ├── gateway/                         ← 既有 (telegraf)
│   ├── ingest/                          ← 既有 (telegraf)
│   ├── kc-gateway/                      ← 新增 (telegraf, 讀 kc-modbus-sim)
│   │   └── telegraf.conf
│   └── kc-ingest/                       ← 新增 (telegraf, MQTT → DB)
│       └── telegraf.conf
├── infra/
│   ├── timescaledb/
│   │   ├── init.sql                     ← 既有，不動
│   │   └── migrations/                  ← 新增
│   │       └── 001_add_factory.sql
│   └── grafana/                         ← 既有
└── config/
    └── mcp-devices.yaml                 ← 新增 (kc-mcp-server 的設備描述)
```

---

## 五、Docker Image 建置策略

### 5.1 Image 清單

| Image 名稱 | 來源 | 用途 | 跑哪些容器 |
|-----------|------|------|-----------|
| `ems-kc-iot-gateway:local` | `external/kc_iot_gateway/Dockerfile` | Python + kc_iot_gateway 源碼 | kc-mqtt-sim |
| `ems-kc-modbus-mcp:local` | `external/kc_modbus_mcp/Dockerfile` | Python + kc_modbus_mcp 源碼 | kc-modbus-sim, kc-mcp-server |
| `ems-simulator` (既有) | `services/simulator/Dockerfile` | Python + pymodbus | ems-simulator |

### 5.2 Image 共用策略

`ems-kc-modbus-mcp:local` **build 一次，用於兩個容器**（不同 command）：

```yaml
# 第一個容器：build 並 tag
kc-modbus-sim:
  build:
    context: ./external/kc_modbus_mcp
  image: ems-kc-modbus-mcp:local         # ← 指定 tag
  command: python simulator.py

# 第二個容器：直接用 image（Docker Compose 會先 build 上面那個）
kc-mcp-server:
  image: ems-kc-modbus-mcp:local         # ← 重用
  command: python server.py
  depends_on:
    kc-modbus-sim:
      condition: service_healthy          # ← 確保 image 已 build
```

### 5.3 Build 時機

```bash
# 初次或源碼更新後
docker compose build kc-modbus-sim kc-mqtt-sim

# 或跟啟動一起
docker compose up -d --build
```

### 5.4 Submodule 更新後的重 build

```bash
# 1. 更新 submodule
git submodule update --remote external/kc_modbus_mcp

# 2. 重 build image
docker compose build --no-cache kc-modbus-sim

# 3. 重啟相關容器
docker compose up -d kc-modbus-sim kc-mcp-server
```

---

## 六、Submodule 設定

### 6.1 初次設定指令（在 WSL 中執行）

```bash
cd ~/synaiq/EMS

# 1. 清掉舊的 sibling clone
# （可選）若 ~/synaiq/kc_iot_gateway 和 kc_modbus_mcp 是先前的 sibling clone
# 且確認沒有未提交的本地變更，再手動清理：
#   mv ~/synaiq/kc_iot_gateway ~/synaiq/kc_iot_gateway.bak
#   mv ~/synaiq/kc_modbus_mcp ~/synaiq/kc_modbus_mcp.bak
# 不要直接 rm -rf，避免誤刪未推上去的工作

# 2. 建立 external 目錄
mkdir -p external

# 3. 加入兩個 submodule
git submodule add https://github.com/KerberosClaw/kc_iot_gateway.git external/kc_iot_gateway
git submodule add https://github.com/KerberosClaw/kc_modbus_mcp.git external/kc_modbus_mcp

# 4. 確認 .gitmodules
cat .gitmodules

# 5. Commit
git add .gitmodules external/
git commit -m "feat: add kc_iot_gateway and kc_modbus_mcp as git submodules"
```

### 6.2 `.gitmodules` 內容

```ini
[submodule "external/kc_iot_gateway"]
    path = external/kc_iot_gateway
    url = https://github.com/KerberosClaw/kc_iot_gateway.git

[submodule "external/kc_modbus_mcp"]
    path = external/kc_modbus_mcp
    url = https://github.com/KerberosClaw/kc_modbus_mcp.git
```

### 6.3 維運指令

| 動作 | 指令 |
|------|------|
| 更新全部 submodule | `git submodule update --remote` |
| 更新單一 submodule | `cd external/kc_iot_gateway && git pull origin main && cd ../..` |
| 他人 clone EMS | `git clone --recurse-submodules <url>` |
| Clone 後補拉 | `git submodule init && git submodule update` |
| Lock 在特定 commit | `cd external/kc_iot_gateway && git checkout <hash>` |

---

## 七、MQTT Payload 契約

### 7.1 既有電表（v5：表名更名，MQTT 不動）

> v5 變更：DB 表名 `measurements` → `electricity_measurements`，與 `factory_measurements` 對稱。
> MQTT topic 保留不動（topic 是 protocol 層 path，跟 DB schema 解耦）。

```
Topic: ems/devices/sim-001/measurements              ← 不改 (MQTT protocol path)
Format: Influx Line Protocol
electricity_measurements,device_id=sim-001 voltage=380.2,current=105.3,power_kw=56.78,energy_kwh=1234.56 <ns>
↑ ILP measurement name 改為 electricity_measurements (對應 DB table)
```

**需同步修改**：
- `services/gateway/telegraf.conf`：input 的 `name` 或 `name_override` 設為 `electricity_measurements`
- `services/ingest/telegraf.conf`：若有顯式 measurement_name，同步改名

### 7.2 新增工廠 PLC（kc-gateway 輸出 ILP）

```
Topic: ems/factory/plc-001/measurements
Format: Influx Line Protocol
factory_measurements,device_id=plc-001,device_type=plc \
  temperature=25.3,humidity=55.2,motor_speed=0,pump_on=false,valve_open=false,pressure=1013 <ns>
```

### 7.3 新增 MQTT 感測器（kc-mqtt-sim 輸出 JSON，EMS 端適配）

```
Topic: factory/sensor/temp_01         ← 硬編碼，不是 ems/ 前綴
Format: JSON
{"temp": 24.8, "hum": 52.1}
```

**kc-ingest 轉換後**：
- tags: `device_id=sensor-001, device_type=sensor`
- fields: `temperature=24.8, humidity=52.1`

### 7.4 欄位對應總表

| 來源 | Topic | Format | temperature | humidity | motor_speed | pump_on | valve_open | pressure |
|------|-------|--------|-------------|----------|-------------|---------|------------|----------|
| kc-gateway | `ems/factory/plc-001/measurements` | ILP | HR[0-1] float32 | HR[2-3] float32 | HR[4] uint16 | Coil[0] | Coil[1] | IR[0] |
| kc-mqtt-sim | `factory/sensor/temp_01` | JSON | $.temp | $.hum | — | — | — | — |

---

## 八、資料庫 Schema

### 8.1 既有表格（v5：更名，schema 不變）

`measurements` → `electricity_measurements` (voltage, current, power_kw, energy_kwh)

- 欄位 schema **完全不變**，只改名稱
- View 同步：`api.measurements` → `api.electricity_measurements`
- PostgREST endpoint：`/measurements` → `/electricity_measurements`
- 詳細 migration 見 §九 與 附錄 F

### 8.2 新增表格（完整版）

```sql
CREATE TABLE factory_measurements (
    time        TIMESTAMPTZ      NOT NULL,
    device_id   TEXT             NOT NULL,
    device_type TEXT,                        -- 'plc' | 'sensor'
    temperature DOUBLE PRECISION,
    humidity    DOUBLE PRECISION,
    motor_speed DOUBLE PRECISION,
    pump_on     BOOLEAN,
    valve_open  BOOLEAN,
    pressure    DOUBLE PRECISION
);

SELECT create_hypertable('factory_measurements', 'time');
CREATE INDEX idx_factory_device_time ON factory_measurements (device_id, time DESC);

CREATE VIEW api.factory_measurements AS
    SELECT time, device_id, device_type,
           temperature, humidity, motor_speed,
           pump_on, valve_open, pressure
    FROM public.factory_measurements;

GRANT SELECT ON api.factory_measurements TO web_anon;
NOTIFY pgrst, 'reload schema';
```

---

## 九、Migration 策略（非破壞式）

### 9.1 分離 Bootstrap 和 Migration

| 檔案 | 執行時機 | 用途 |
|------|---------|------|
| `infra/timescaledb/init.sql` | Volume 空時自動 | **修改**：直接以 `electricity_measurements` 命名建表（全新部署不需 rename） |
| `infra/timescaledb/migrations/000_rename_measurements.sql` | 手動執行一次 | **新增**：既有部署將 `measurements` 改名為 `electricity_measurements` |
| `infra/timescaledb/migrations/001_add_factory.sql` | 手動執行一次 | 新增 `factory_measurements` 表 |

### 9.2 Migration 腳本

- `000_rename_measurements.sql` 內容見**附錄 F**（v5 新增）
- `001_add_factory.sql` 內容見**附錄 A**

### 9.3 執行順序（既有部署）

> 順序很重要：Telegraf 在 table 改名瞬間會找不到目標 table 而報錯（雖然會 retry），先停 ingest 再改是最安全的。

```bash
# 1. 停止寫入端，避免改名瞬間 ingest 寫入失敗
docker compose stop ingest

# 2. 跑 rename migration（idempotent，重複跑安全）
docker cp infra/timescaledb/migrations/000_rename_measurements.sql ems-timescaledb:/tmp/
docker exec ems-timescaledb psql -U postgres -d ems -f /tmp/000_rename_measurements.sql

# 3. 更新 services/gateway/telegraf.conf：
#    [[inputs.modbus]] 的 name 或 name_override 改為 electricity_measurements
#    重啟 gateway 讓 ILP measurement name 一致
docker compose up -d --force-recreate gateway

# 4. 跑 factory migration（新增 factory_measurements 表）
docker cp infra/timescaledb/migrations/001_add_factory.sql ems-timescaledb:/tmp/
docker exec ems-timescaledb psql -U postgres -d ems -f /tmp/001_add_factory.sql

# 5. 啟動 ingest（既有 + 新增 kc-ingest）
docker compose up -d ingest kc-ingest

# 6. 驗證 PostgREST 看得到新 endpoint
sleep 5
curl -s 'http://localhost:3001/' | grep -E 'electricity_measurements|factory_measurements'
```

### 9.4 全新部署

新環境只需 `init.sql`（已含 `electricity_measurements`）+ `001_add_factory.sql`，**不需** 跑 `000_rename`（migration 內含 idempotent 檢查，跑了也安全跳過）。

---

## 十、docker-compose.yml 新增服務

```yaml
  # ===== KC Modbus Simulator (from kc_modbus_mcp, shares image with MCP server) =====
  kc-modbus-sim:
    build:
      context: ./external/kc_modbus_mcp
    image: ems-kc-modbus-mcp:local
    container_name: ems-kc-modbus-sim
    command: python simulator.py
    environment:
      - SIMULATOR_HOST=0.0.0.0
      - SIMULATOR_PORT=5020
    ports:
      - "5021:5020"
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c", "import socket; s=socket.socket(); s.connect(('localhost',5020)); s.close()"]
      interval: 5s
      timeout: 3s
      retries: 5

  # ===== KC MQTT Simulator (from kc_iot_gateway) =====
  kc-mqtt-sim:
    build:
      context: ./external/kc_iot_gateway
    image: ems-kc-iot-gateway:local
    container_name: ems-kc-mqtt-sim
    command: python simulators/mqtt_simulator.py
    environment:
      - MQTT_BROKER=mosquitto
      - MQTT_PORT=1883
    depends_on:
      mosquitto:
        condition: service_started
    restart: unless-stopped

  # ===== KC Gateway (Telegraf: Modbus → MQTT) =====
  kc-gateway:
    image: telegraf:1.30
    container_name: ems-kc-gateway
    depends_on:
      kc-modbus-sim:
        condition: service_healthy
      mosquitto:
        condition: service_started
    volumes:
      - ./services/kc-gateway/telegraf.conf:/etc/telegraf/telegraf.conf:ro
    restart: unless-stopped

  # ===== KC Ingest (Telegraf: MQTT → TimescaleDB) =====
  kc-ingest:
    image: telegraf:1.30
    container_name: ems-kc-ingest
    depends_on:
      timescaledb:
        condition: service_healthy
      mosquitto:
        condition: service_started
    environment:
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-postgres}
    volumes:
      - ./services/kc-ingest/telegraf.conf:/etc/telegraf/telegraf.conf:ro
    restart: unless-stopped

  # ===== KC Modbus MCP Server (AI Agent Interface, reuses kc-modbus-sim image) =====
  #
  # 安全注意：
  # - MCP Server 沒有認證機制（參見 kc_modbus_mcp upstream README）
  # - Raw mode 允許讀寫任何可達的 Modbus 設備
  # - 預設綁定 127.0.0.1（只允許本機連接），不暴露到內網
  # - 如需從其他機器連接，改為 8765:8765（去掉 127.0.0.1），並自行處理 firewall / VPN
  kc-mcp-server:
    image: ems-kc-modbus-mcp:local
    container_name: ems-kc-mcp-server
    command: python server.py
    environment:
      - MODBUS_PROFILE=/app/devices.yaml
      - MCP_HOST=0.0.0.0
      - MCP_PORT=8765
    ports:
      - "127.0.0.1:8765:8765"              # 僅本機，避免未認證控制面暴露
    volumes:
      - ./config/mcp-devices.yaml:/app/devices.yaml:ro
    depends_on:
      simulator:
        condition: service_started       # 連 EMS 既有電表
      kc-modbus-sim:
        condition: service_healthy        # 連工廠 PLC (確保 image 已 build)
    restart: unless-stopped
```

---

## 十一、容器總覽

| # | 容器名稱 | Image 來源 | Port | 功能 |
|---|---------|-----------|------|------|
| 1 | ems-simulator | 自建 | 5020, 8001 | 電表模擬器（既有） |
| 2 | ems-gateway | telegraf:1.30 | — | 電表 Modbus → MQTT（既有） |
| 3 | ems-mosquitto | eclipse-mosquitto:2 | 1883 | MQTT broker（既有） |
| 4 | ems-ingest | telegraf:1.30 | — | 電表 MQTT → DB（既有） |
| 5 | ems-timescaledb | timescale/timescaledb | 5432 | 時序資料庫（既有） |
| 6 | ems-query | postgrest/postgrest | 3001 | REST API（既有） |
| 7 | ems-grafana | grafana/grafana-oss | 3000 | 儀表板（既有） |
| 8 | ems-kc-modbus-sim | `ems-kc-modbus-mcp:local` | 5021 | 工廠 PLC 模擬器（共用 image） |
| 9 | ems-kc-mqtt-sim | `ems-kc-iot-gateway:local` | — | JSON 感測器模擬器 |
| 10 | ems-kc-gateway | telegraf:1.30 | — | 工廠 Modbus → MQTT |
| 11 | ems-kc-ingest | telegraf:1.30 | — | 工廠 MQTT → DB |
| 12 | ems-kc-mcp-server | `ems-kc-modbus-mcp:local` | 127.0.0.1:8765 | AI Agent MCP 介面（共用 image） |

**既有 7 + 新增 5 = 12 個容器**

**Image 共用**：8 號和 12 號容器共用 `ems-kc-modbus-mcp:local`，只 build 一次。

---

## 十一-A、安全邊界（重要）

| 服務 | 預設綁定 | 說明 |
|------|---------|------|
| ems-simulator | `0.0.0.0:5020` (Modbus), `0.0.0.0:8001` (REST) | 既有，dev 環境用 |
| ems-grafana | `0.0.0.0:3000` | 有密碼保護 |
| ems-query | `0.0.0.0:3001` | 唯讀 PostgREST，read-only role |
| **kc-modbus-sim** | `0.0.0.0:5021` (Modbus) | **無認證**，dev 模擬器 |
| **kc-mcp-server** | `127.0.0.1:8765` (MCP) | **無認證**，僅綁本機 |

### MCP Server 風險

`kc_modbus_mcp` upstream README 明確聲明：
> 本專案為 POC / 開發用途，設計用於受信任的內網環境。MCP Server 不包含認證機制，Raw mode 允許讀寫任何可達的 Modbus 設備。

**風險**：
- 任何能連到 :8765 的人都能呼叫 `write_device` 控制設備
- Raw mode（`write_registers`）能寫到 simulator 內任何 Modbus 設備
- 沒有 audit log

**緩解**：
1. **預設綁 127.0.0.1**（已在 docker-compose 設定）— 只有本機可連
2. **不要直接暴露到公網** — 不開 firewall、不放 reverse proxy
3. 若需遠端使用，搭配 **SSH tunnel** 或 **VPN**：
   ```bash
   # 從遠端機器透過 SSH tunnel 連到 EMS 主機的 MCP
   ssh -L 8765:localhost:8765 user@ems-host
   # 然後本機 mcporter 連 http://localhost:8765/mcp
   ```
4. 生產環境前要加 reverse proxy + auth（Caddy / Traefik + basic auth / OAuth）

---

## 十二、實作步驟

### Phase 1：Submodule 設定

```bash
cd ~/synaiq/EMS
git checkout -b feature/kc-integration

# 清掉舊 clone
# （可選）若 ~/synaiq/kc_iot_gateway 和 kc_modbus_mcp 是先前的 sibling clone
# 且確認沒有未提交的本地變更，再手動清理：
#   mv ~/synaiq/kc_iot_gateway ~/synaiq/kc_iot_gateway.bak
#   mv ~/synaiq/kc_modbus_mcp ~/synaiq/kc_modbus_mcp.bak
# 不要直接 rm -rf，避免誤刪未推上去的工作

# 加 submodule
mkdir -p external
git submodule add https://github.com/KerberosClaw/kc_iot_gateway.git external/kc_iot_gateway
git submodule add https://github.com/KerberosClaw/kc_modbus_mcp.git external/kc_modbus_mcp

git add .gitmodules external/
git commit -m "feat: add kc submodules"
```

### Phase 2：建立配置檔案

```bash
mkdir -p services/kc-gateway services/kc-ingest
mkdir -p infra/timescaledb/migrations
mkdir -p config

# 建立以下檔案（內容見附錄）：
# - services/kc-gateway/telegraf.conf
# - services/kc-ingest/telegraf.conf
# - infra/timescaledb/migrations/001_add_factory.sql
# - config/mcp-devices.yaml
```

### Phase 3：修改 docker-compose.yml

新增 §十 列的 5 個服務。

### Phase 4：執行 Migration（v5：rename → 改 telegraf → factory）

> 詳細順序與理由見 §9.3。

```bash
# 4.1 停 ingest，跑 rename
docker compose stop ingest
docker cp infra/timescaledb/migrations/000_rename_measurements.sql ems-timescaledb:/tmp/
docker exec ems-timescaledb psql -U postgres -d ems -f /tmp/000_rename_measurements.sql

# 4.2 同步修改 services/gateway/telegraf.conf：
#     ILP measurement name → electricity_measurements
docker compose up -d --force-recreate gateway

# 4.3 跑 factory migration
docker cp infra/timescaledb/migrations/001_add_factory.sql ems-timescaledb:/tmp/
docker exec ems-timescaledb psql -U postgres -d ems -f /tmp/001_add_factory.sql

# 4.4 重啟 ingest（既有 + 新 kc-ingest）
docker compose up -d ingest
```

### Phase 5：Build 並啟動新服務

```bash
# Build 兩個 image
# - ems-kc-modbus-mcp:local   (kc-modbus-sim 和 kc-mcp-server 共用)
# - ems-kc-iot-gateway:local  (kc-mqtt-sim 用)
docker compose build kc-modbus-sim kc-mqtt-sim

# 啟動 5 個新服務
docker compose up -d kc-modbus-sim kc-mqtt-sim kc-gateway kc-ingest kc-mcp-server

# 驗證 build 結果
docker images | grep ems-kc
# 預期看到兩個：ems-kc-modbus-mcp:local 和 ems-kc-iot-gateway:local
```

### Phase 6：擴展 Grafana（§十三）

新增工廠 panels 到現有 dashboard 或建立新 dashboard JSON。

### Phase 6 完成紀錄

已在 `infra/grafana/provisioning/dashboards/ems-overview.json` 新增 `KC 工廠環境與設備狀態` 區塊，包含：

- Gauge：PLC 溫度、PLC 濕度、壓力、馬達轉速
- Stat：Pump、Valve 目前 ON/OFF
- Time series：溫度、濕度、壓力趨勢
- State timeline：Pump / Valve 狀態持續時間
- Table：最新 `factory_measurements` 明細


---

## 十三、驗收清單

### 13.1 回歸測試（既有功能不受影響）

| 項目 | 指令 | 預期 |
|------|------|------|
| 電表 MQTT | `docker exec ems-mosquitto mosquitto_sub -t 'ems/devices/#' -C 1` | 收到 sim-001（topic 不變） |
| 電表 DB | `docker exec ems-timescaledb psql -U postgres -d ems -c "SELECT COUNT(*) FROM electricity_measurements WHERE time > NOW() - INTERVAL '1 minute';"` | count > 0 |
| 電表 REST | `curl 'http://localhost:3001/electricity_measurements?limit=1'` | JSON |
| Grafana 電表 panel | http://localhost:3000 | 數值更新中（dashboard SQL 已改 `FROM electricity_measurements`） |
| 舊表已清除 | `docker exec ems-timescaledb psql -U postgres -d ems -c "\dt public.measurements"` | `Did not find any relation`（已 rename） |
| 歷史資料保留 | `docker exec ems-timescaledb psql -U postgres -d ems -c "SELECT COUNT(*) FROM electricity_measurements"` | 等於 rename 前的筆數 |

### 13.2 新功能測試（讀取）

| 項目 | 指令 | 預期 |
|------|------|------|
| PLC MQTT (ILP) | `docker exec ems-mosquitto mosquitto_sub -t 'ems/factory/plc-001/#' -C 1` | ILP 格式 |
| Sensor MQTT (JSON) | `docker exec ems-mosquitto mosquitto_sub -t 'factory/sensor/temp_01' -C 1` | JSON 格式 |
| 工廠 DB | `docker exec ems-timescaledb psql -U postgres -d ems -c "SELECT device_id, device_type, temperature FROM factory_measurements ORDER BY time DESC LIMIT 5;"` | plc-001 和 sensor-001 都有 |
| 工廠 REST | `curl 'http://localhost:3001/factory_measurements?limit=3'` | JSON |

### 13.3 新功能測試（完整 PLC 欄位覆蓋）

覆蓋所有 PLC 欄位：temperature, humidity, pressure 是模擬器自動產生；motor_speed, pump_on, valve_open 需手動寫入驗證。

#### 13.3.1 自動產生的欄位（temperature / humidity / pressure）

```bash
# 驗證最新一筆 PLC 資料包含所有自動產生欄位（非 null）
docker exec ems-timescaledb psql -U postgres -d ems -c "
  SELECT time, temperature, humidity, pressure
  FROM factory_measurements 
  WHERE device_id='plc-001' AND time > NOW() - INTERVAL '30 seconds'
  ORDER BY time DESC LIMIT 1;
"
# 預期：temperature 20-30 之間、humidity 40-60 之間、pressure 900-1100 之間，都非 null
```

#### 13.3.2 手動寫入：motor_speed (Holding Register)

```bash
python3 -c "
from pymodbus.client import ModbusTcpClient
c = ModbusTcpClient('localhost', port=5021)
c.connect(); c.write_register(4, 1500, slave=1); c.close()
print('Wrote motor_speed=1500')
"

sleep 3
docker exec ems-timescaledb psql -U postgres -d ems -c \
  "SELECT motor_speed FROM factory_measurements WHERE device_id='plc-001' ORDER BY time DESC LIMIT 1;"
# 預期：motor_speed = 1500
```

#### 13.3.3 手動寫入：pump_on (Coil 0)

```bash
python3 -c "
from pymodbus.client import ModbusTcpClient
c = ModbusTcpClient('localhost', port=5021)
c.connect(); c.write_coil(0, True, slave=1); c.close()
print('Wrote pump_on=true')
"

sleep 3
docker exec ems-timescaledb psql -U postgres -d ems -c \
  "SELECT pump_on FROM factory_measurements WHERE device_id='plc-001' ORDER BY time DESC LIMIT 1;"
# 預期：pump_on = t (true)
```

#### 13.3.4 手動寫入：valve_open (Coil 1)

```bash
python3 -c "
from pymodbus.client import ModbusTcpClient
c = ModbusTcpClient('localhost', port=5021)
c.connect(); c.write_coil(1, True, slave=1); c.close()
print('Wrote valve_open=true')
"

sleep 3
docker exec ems-timescaledb psql -U postgres -d ems -c \
  "SELECT valve_open FROM factory_measurements WHERE device_id='plc-001' ORDER BY time DESC LIMIT 1;"
# 預期：valve_open = t (true)
```

#### 13.3.5 驗收矩陣

| 欄位 | 類型 | 驗證方式 | 來源 |
|------|------|---------|------|
| temperature | FLOAT32 HR[0-1] | 自動，查非 null | 模擬器正弦波 |
| humidity | FLOAT32 HR[2-3] | 自動，查非 null | 模擬器隨機 |
| motor_speed | UINT16 HR[4] | 手動 write_register | 需寫入 |
| pressure | UINT16 IR[0] | 自動，查非 null | 模擬器隨機 |
| pump_on | BOOL Coil[0] | 手動 write_coil | 需寫入 |
| valve_open | BOOL Coil[1] | 手動 write_coil | 需寫入 |

### 13.4 MCP Server 測試

> **設備名稱對應**：MCP 的設備名稱來自 `mcp-devices.yaml` 的 key（`energy_meter`、`factory_plc`），與 DB 中的 `device_id`（`sim-001`、`plc-001`）是不同的識別系統——MCP 用語義化名稱給 AI 讀，device_id 是物理識別。

```bash
# 安裝 mcporter
npm install -g mcporter

# 連接 MCP Server
mcporter config add ems-mcp --url http://localhost:8765/mcp

# 列出設備
mcporter call ems-mcp.list_devices
# 預期：列出 energy_meter 和 factory_plc

# 讀取電表功率
mcporter call ems-mcp.read_device device=energy_meter register=power_kw
# 預期：power_kw=56.78 kW（或當下實際值）

# 讀取工廠溫度
mcporter call ems-mcp.read_device device=factory_plc register=temperature
# 預期：temperature=25.3 °C

# 寫入工廠馬達轉速
mcporter call ems-mcp.write_device device=factory_plc register=motor_speed value=1500
# 預期：寫入成功，之後驗收 13.3.2 會看到 DB 中 motor_speed=1500

# 從 Claude Desktop 連接（optional）
# 在 Claude Desktop 的 MCP 設定加入：
# {"ems-mcp": {"url": "http://localhost:8765/mcp"}}
```

**MCP 名稱 vs device_id 對照表**：

| MCP 設備名 (YAML key) | DB 中 device_id (MQTT tag) | 實際設備 |
|---------------------|---------------------------|---------|
| `energy_meter` | `sim-001` | EMS 既有電表模擬器 |
| `factory_plc` | `plc-001` | KC 工廠 PLC 模擬器 |

### 13.5 容器狀態

```bash
docker compose ps
# 預期：12 個容器全部 running/healthy
```

---

## 十四、回滾計畫

### 14.1 Code Rollback

```bash
# 回到 main branch
git checkout main

# 或 revert commit
git revert <commit-hash>

# 重新部署
docker compose down
docker compose up -d
```

### 14.2 Submodule Rollback

```bash
# 刪除 submodule
git submodule deinit -f external/kc_iot_gateway
git submodule deinit -f external/kc_modbus_mcp
git rm -f external/kc_iot_gateway external/kc_modbus_mcp
rm -rf .git/modules/external/
```

### 14.3 Data Rollback（不砍 volume）

```sql
-- (a) 移除新增的 factory 表
DROP VIEW IF EXISTS api.factory_measurements;
DROP TABLE IF EXISTS factory_measurements;

-- (b) 還原電表表名 measurements（若需完全回到 v4 之前）
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables
               WHERE table_schema='public' AND table_name='electricity_measurements') THEN
        ALTER TABLE public.electricity_measurements RENAME TO measurements;
        ALTER INDEX IF EXISTS idx_electricity_device_time
              RENAME TO idx_measurements_device_time;

        DROP VIEW IF EXISTS api.electricity_measurements;
        CREATE VIEW api.measurements AS
            SELECT time, device_id, voltage, current, power_kw, energy_kwh
            FROM public.measurements;
        GRANT SELECT ON api.measurements TO web_anon;
    END IF;
END $$;

NOTIFY pgrst, 'reload schema';
```

> 還原後同步把 `services/gateway/telegraf.conf` 的 ILP measurement name 改回 `measurements`，並 `docker compose up -d --force-recreate gateway`。

### 14.4 Image Cleanup

```bash
docker rmi ems-kc-iot-gateway:local ems-kc-modbus-mcp:local
```

---

## 附錄 A：001_add_factory.sql

```sql
-- Migration: 001_add_factory
BEGIN;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'factory_measurements') THEN
        RAISE NOTICE 'factory_measurements already exists, skipping';
        RETURN;
    END IF;

    CREATE TABLE factory_measurements (
        time        TIMESTAMPTZ      NOT NULL,
        device_id   TEXT             NOT NULL,
        device_type TEXT,
        temperature DOUBLE PRECISION,
        humidity    DOUBLE PRECISION,
        motor_speed DOUBLE PRECISION,
        pump_on     BOOLEAN,
        valve_open  BOOLEAN,
        pressure    DOUBLE PRECISION
    );

    PERFORM create_hypertable('factory_measurements', 'time', if_not_exists => TRUE);
    CREATE INDEX idx_factory_device_time ON factory_measurements (device_id, time DESC);

    CREATE VIEW api.factory_measurements AS
        SELECT time, device_id, device_type,
               temperature, humidity, motor_speed,
               pump_on, valve_open, pressure
        FROM public.factory_measurements;

    GRANT SELECT ON api.factory_measurements TO web_anon;
    RAISE NOTICE 'factory_measurements created';
END $$;

COMMIT;
NOTIFY pgrst, 'reload schema';
```

---

## 附錄 B：services/kc-gateway/telegraf.conf

```toml
[agent]
  interval = "2s"
  flush_interval = "2s"
  omit_hostname = true

[[inputs.modbus]]
  name = "plc-001"
  name_override = "factory_measurements"
  slave_id = 1
  timeout = "1s"
  controller = "tcp://kc-modbus-sim:5020"
  configuration_type = "request"

# Holding Registers
[[inputs.modbus.request]]
  slave_id = 1
  byte_order = "ABCD"
  register = "holding"
  fields = [
    { address = 0, name = "temperature", type = "FLOAT32", output = "FLOAT64" },
    { address = 2, name = "humidity",    type = "FLOAT32", output = "FLOAT64" },
    { address = 4, name = "motor_speed", type = "UINT16",  output = "FLOAT64" },
  ]
  tags = { device_id = "plc-001", device_type = "plc" }

# Input Registers
[[inputs.modbus.request]]
  slave_id = 1
  byte_order = "ABCD"
  register = "input"
  fields = [
    { address = 0, name = "pressure", type = "UINT16", output = "FLOAT64" },
  ]
  tags = { device_id = "plc-001", device_type = "plc" }

# Coils
[[inputs.modbus.request]]
  slave_id = 1
  register = "coil"
  fields = [
    { address = 0, name = "pump_on",    type = "BOOL" },
    { address = 1, name = "valve_open", type = "BOOL" },
  ]
  tags = { device_id = "plc-001", device_type = "plc" }

[[outputs.mqtt]]
  servers = ["tcp://mosquitto:1883"]
  topic = 'ems/factory/{{ .Tag "device_id" }}/measurements'
  data_format = "influx"
  client_id = "kc-gateway"
  qos = 1
```

---

## 附錄 C：services/kc-ingest/telegraf.conf

> 依據既有 `services/ingest/telegraf.conf` 的模式：用 `create_templates = []` 禁止自動建表、measurement name 自動對應 table 名稱、`tags_as_jsonb = false` 讓 tags 成為欄位。

```toml
# Ingest: 訂閱工廠 MQTT（ILP + JSON 兩種格式），寫入 TimescaleDB
# 沿用既有 ems-ingest 的配置模式

[agent]
  interval = "10s"
  round_interval = true
  flush_interval = "5s"
  flush_jitter = "1s"
  omit_hostname = true

# ========== INPUT 1: PLC 數據（ILP 格式，來自 kc-gateway）==========
[[inputs.mqtt_consumer]]
  servers = ["tcp://mosquitto:1883"]
  topics = ["ems/factory/+/measurements"]
  data_format = "influx"
  client_id = "kc-ingest-plc"
  qos = 1

# ========== INPUT 2: 感測器（JSON 格式，來自 kc-mqtt-sim）==========
[[inputs.mqtt_consumer]]
  servers = ["tcp://mosquitto:1883"]
  topics = ["factory/sensor/temp_01"]
  data_format = "json_v2"
  client_id = "kc-ingest-sensor"
  qos = 1

  [[inputs.mqtt_consumer.json_v2]]
    measurement_name = "factory_measurements"

    [[inputs.mqtt_consumer.json_v2.field]]
      path = "temp"
      rename = "temperature"
      type = "float"
    [[inputs.mqtt_consumer.json_v2.field]]
      path = "hum"
      rename = "humidity"
      type = "float"

  # tags 必須放在所有其他設定之後（Telegraf TOML 解析規則）
  [inputs.mqtt_consumer.tags]
    device_id = "sensor-001"
    device_type = "sensor"

# ========== OUTPUT: PostgreSQL / TimescaleDB ==========
# 沿用既有 ems-ingest 的最小配置
# Measurement name "factory_measurements" 自動對應到同名 table
[[outputs.postgresql]]
  connection = "host=timescaledb user=postgres password=${POSTGRES_PASSWORD} sslmode=disable dbname=ems"
  schema = "public"
  tags_as_jsonb = false
  fields_as_jsonb = false
  # table 已在 migration 預建，禁止 Telegraf 自動建表
  create_templates = []
```

---

## 附錄 D：config/mcp-devices.yaml

讓 kc-mcp-server 可以同時讀 EMS 電表和工廠 PLC：

```yaml
# config/mcp-devices.yaml
devices:
  # EMS 既有電表
  energy_meter:
    host: simulator           # 容器名稱
    port: 5020
    slave_id: 1
    byte_order: big
    registers:
      voltage:
        address: 0
        function_code: 3
        data_type: int16
        scale: 0.1
        unit: "V"
        access: read
        description: "Line voltage"
      current:
        address: 1
        function_code: 3
        data_type: int16
        scale: 0.1
        unit: "A"
        access: read
        description: "Line current"
      power_kw:
        address: 2
        function_code: 3
        data_type: float32
        unit: "kW"
        access: read
        description: "Active power"
      energy_kwh:
        address: 4
        function_code: 3
        data_type: float32
        unit: "kWh"
        access: read
        description: "Cumulative energy"

  # 工廠 PLC
  factory_plc:
    host: kc-modbus-sim       # 容器名稱
    port: 5020
    slave_id: 1
    byte_order: big
    registers:
      temperature:
        address: 0
        function_code: 3
        data_type: float32
        unit: "°C"
        access: read
      humidity:
        address: 2
        function_code: 3
        data_type: float32
        unit: "%RH"
        access: read
      motor_speed:
        address: 4
        function_code: 3
        data_type: uint16
        unit: "RPM"
        access: read_write
      pressure:
        address: 0
        function_code: 4
        data_type: uint16
        unit: "kPa"
        access: read
      pump_on:
        address: 0
        function_code: 1
        data_type: bool
        access: read_write
      valve_open:
        address: 1
        function_code: 1
        data_type: bool
        access: read_write
```

---

## 附錄 E：配置檔案清單

| 檔案 | 狀態 | 用途 |
|------|------|------|
| `docker-compose.yml` | 修改 | 新增 5 個服務 |
| `.gitmodules` | 新增 | 記錄 submodule |
| `external/kc_iot_gateway/` | 新增 (submodule) | kc_iot_gateway 源碼 |
| `external/kc_modbus_mcp/` | 新增 (submodule) | kc_modbus_mcp 源碼 |
| `services/gateway/telegraf.conf` | **修改 (v5)** | ILP measurement name `measurements` → `electricity_measurements` |
| `services/ingest/telegraf.conf` | **修改 (v5)** | 若有顯式 measurement_name，同步改名 |
| `services/kc-gateway/telegraf.conf` | 新增 | 工廠 Modbus → MQTT |
| `services/kc-ingest/telegraf.conf` | 新增 | 工廠 MQTT → DB |
| `infra/timescaledb/init.sql` | **修改 (v5)** | 表名改為 `electricity_measurements`（新部署不需 rename） |
| `infra/timescaledb/migrations/000_rename_measurements.sql` | **新增 (v5)** | 既有部署改名 migration（見附錄 F） |
| `infra/timescaledb/migrations/001_add_factory.sql` | 新增 | 新增 factory_measurements（見附錄 A） |
| `config/mcp-devices.yaml` | 新增 | MCP Server 設備描述 |
| `infra/grafana/provisioning/dashboards/*.json` | **修改或新增** | 工廠 panels + 既有電表 panel SQL 改 `FROM electricity_measurements` |
| `infra/grafana/provisioning/datasources/timescaledb.yaml` | **不動** | 沿用既有 datasource |

---

## 附錄 F：000_rename_measurements.sql（v5 新增）

> 將既有 `measurements` 表更名為 `electricity_measurements`，與 `factory_measurements` 對稱。
> Idempotent — 重複執行安全；全新部署（init.sql 已建新表）也安全跳過。

```sql
-- Migration: 000_rename_measurements
-- 將 measurements → electricity_measurements，schema 不變
BEGIN;

DO $$
BEGIN
    -- 已是新名字 → 跳過（重複執行）
    IF EXISTS (SELECT 1 FROM information_schema.tables
               WHERE table_schema='public' AND table_name='electricity_measurements') THEN
        RAISE NOTICE 'electricity_measurements already exists, skipping rename';
        RETURN;
    END IF;

    -- 找不到舊表 → 跳過（全新部署，init.sql 直接建好新表）
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables
                   WHERE table_schema='public' AND table_name='measurements') THEN
        RAISE NOTICE 'measurements not found (fresh install), skipping';
        RETURN;
    END IF;

    -- 1. Rename table（hypertable metadata 自動跟著）
    ALTER TABLE public.measurements RENAME TO electricity_measurements;

    -- 2. Rename index（若舊 init.sql 有建這個索引）
    ALTER INDEX IF EXISTS idx_measurements_device_time
          RENAME TO idx_electricity_device_time;

    -- 3. Replace API view
    DROP VIEW IF EXISTS api.measurements;
    CREATE VIEW api.electricity_measurements AS
        SELECT time, device_id, voltage, current, power_kw, energy_kwh
        FROM public.electricity_measurements;
    GRANT SELECT ON api.electricity_measurements TO web_anon;

    RAISE NOTICE 'Renamed measurements -> electricity_measurements (data preserved)';
END $$;

COMMIT;
NOTIFY pgrst, 'reload schema';
```

### F.1 執行前後檢查

```bash
# Before：確認舊表存在、記下筆數
docker exec ems-timescaledb psql -U postgres -d ems -c "\dt public.measurements"
docker exec ems-timescaledb psql -U postgres -d ems -c "SELECT COUNT(*) AS before_count FROM measurements;"

# Run
docker cp infra/timescaledb/migrations/000_rename_measurements.sql ems-timescaledb:/tmp/
docker exec ems-timescaledb psql -U postgres -d ems -f /tmp/000_rename_measurements.sql

# After：新表存在、舊表消失、筆數一致
docker exec ems-timescaledb psql -U postgres -d ems -c "\dt public.electricity_measurements"
docker exec ems-timescaledb psql -U postgres -d ems -c "SELECT COUNT(*) AS after_count FROM electricity_measurements;"

# PostgREST schema 已重載
curl -s 'http://localhost:3001/' | grep electricity_measurements
```

### F.2 配套修改清單（不改會掉資料）

跑完 migration 後，下列位置必須同步改，否則寫入端找不到 table、查詢端拿不到資料：

| 位置 | 改什麼 |
|------|-------|
| `services/gateway/telegraf.conf` | `[[inputs.modbus]]` 的 `name` 或 `name_override` 改為 `electricity_measurements`（這是 ILP measurement name，決定寫入哪個 table） |
| `services/ingest/telegraf.conf` | 若有顯式 measurement_name 設定，同步改名（多數情況沿用 ILP 自動帶入則不需改） |
| `infra/timescaledb/init.sql` | 全新部署使用，把 `CREATE TABLE measurements` / 對應 view / 索引名稱全部改為 `electricity_measurements` 系列 |
| `infra/grafana/provisioning/dashboards/*.json` | 所有 `FROM measurements` / `from(bucket: "measurements")` 改為 `electricity_measurements` |
| 應用程式 / 腳本 / 文件 | 任何引用 `/measurements` REST endpoint、`SELECT ... FROM measurements`、或硬編碼名稱的地方 |
