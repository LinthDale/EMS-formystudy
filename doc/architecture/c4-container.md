# C4 Level 2 — Container Diagram

> 範圍：EMS 內部所有容器（services + infra）、技術選型、部署位置、Owner。

```mermaid
flowchart LR
    %% External
    cf_tunnel["Cloudflare<br/>Tunnel"]
    telegram_ext["Telegram<br/>Bot API"]
    ai_mcp["AI Agent<br/>(MCP Client)"]

    subgraph host["Docker Host (WSL Ubuntu)"]
      direction TB

      subgraph dev_only["Dev-only Simulators"]
        sim["ems-simulator<br/>Python 3.x<br/>FastAPI + pymodbus 3.6.9<br/>:5020 :8001"]
        kc_modbus_sim["ems-kc-modbus-sim<br/>(external/kc_modbus_mcp)<br/>:5021"]
        kc_mqtt_sim["ems-kc-mqtt-sim<br/>(external/kc_iot_gateway)"]
      end

      subgraph data_plane["Data Plane"]
        gw["ems-gateway<br/>telegraf:1.30<br/>Modbus → MQTT"]
        kc_gw["ems-kc-gateway<br/>telegraf:1.30<br/>PLC Modbus → MQTT"]
        broker["ems-mosquitto<br/>eclipse-mosquitto:2<br/>:1883"]
        ingest["ems-ingest<br/>telegraf:1.30<br/>MQTT → DB"]
        kc_ingest["ems-kc-ingest<br/>telegraf:1.30<br/>MQTT → DB"]
      end

      subgraph storage["Storage"]
        db[("ems-timescaledb<br/>PostgreSQL 15<br/>+ TimescaleDB<br/>:5432")]
      end

      subgraph app_plane["Application / API"]
        query["ems-query<br/>postgrest:14.10<br/>:3001"]
        grafana["ems-grafana<br/>Grafana<br/>:3000"]
        mcp["ems-kc-mcp-server<br/>(external/kc_modbus_mcp)<br/>:8765"]
      end
    end

    %% External devices (示意)
    plc_real["真實 PLC<br/>（未來）"]

    %% Flows
    sim -- "Modbus TCP" --> gw
    kc_modbus_sim -- "Modbus TCP" --> kc_gw
    plc_real -. "Modbus TCP" .-> kc_gw

    gw -- "MQTT publish<br/>ems/devices/sim-001/measurements<br/>(ILP)" --> broker
    kc_gw -- "MQTT publish<br/>factory/devices/plc-001/measurements<br/>(ILP)" --> broker
    kc_mqtt_sim -- "MQTT publish<br/>factory/devices/sensor-001/measurements<br/>(JSON)" --> broker

    broker -. "MQTT subscribe<br/>ems/devices/+/measurements" .-> ingest
    broker -. "MQTT subscribe<br/>factory/devices/+/measurements" .-> kc_ingest

    ingest -- "INSERT<br/>electricity_measurements" --> db
    kc_ingest -- "INSERT<br/>factory_measurements" --> db

    query -- "SELECT api.*" --> db
    grafana -- "SELECT public.*" --> db

    mcp -- "Modbus 讀寫" --> sim
    mcp -- "Modbus 讀寫" --> kc_modbus_sim
    ai_mcp --> mcp

    cf_tunnel --> grafana
    grafana -- "告警觸發" --> telegram_ext

    classDef ext fill:#fff4e6,stroke:#ea580c,color:#000
    classDef sim_cls fill:#fef3c7,stroke:#ca8a04,color:#000
    classDef data fill:#dbeafe,stroke:#2563eb,color:#000
    classDef store fill:#ede9fe,stroke:#7c3aed,color:#000
    classDef app fill:#dcfce7,stroke:#16a34a,color:#000

    class cf_tunnel,telegram_ext,ai_mcp,plc_real ext
    class sim,kc_modbus_sim,kc_mqtt_sim sim_cls
    class gw,kc_gw,broker,ingest,kc_ingest data
    class db store
    class query,grafana,mcp app
```

## 容器索引

| 容器 | 鏡像 | 自寫? | 對外 Port | Owner | Rollback 影響 |
|------|------|------|----------|-------|--------------|
| ems-simulator | local build | ✅ Python | 5020, 8001 | EMS team | dev only |
| ems-gateway | telegraf:1.30 | ❌ config | — | EMS team | 電表流斷 |
| ems-kc-gateway | telegraf:1.30 | ❌ config | — | EMS team | 工廠流斷 |
| ems-mosquitto | eclipse-mosquitto:2 | ❌ | 1883 | EMS team | **全系統中斷** |
| ems-ingest | telegraf:1.30 | ❌ config | — | EMS team | 電表寫入停（Mosquitto QoS1 暫存）|
| ems-kc-ingest | telegraf:1.30 | ❌ config | — | EMS team | 工廠寫入停 |
| ems-timescaledb | timescale/pg15 | ❌ schema | 5432 | EMS team | **全系統中斷** |
| ems-query | postgrest:14.10 | ❌ env | 3001 | EMS team | 歷史查詢停 |
| ems-grafana | grafana | ❌ provisioning | 3000 | EMS team | Dashboard / Alerting 停 |
| ems-kc-modbus-sim | external/kc_modbus_mcp | external | 5021 | KC | dev only |
| ems-kc-mqtt-sim | external/kc_iot_gateway | external | — | KC | dev only |
| ems-kc-mcp-server | external/kc_modbus_mcp | external | 8765 | KC | AI 控制功能停 |

## 技術選型摘要（連結 ADR）

- 服務全採開源工具：[ADR-001](../adr/ADR-001-open-source-first.md)
- pymodbus 鎖 3.6.9：[ADR-002](../adr/ADR-002-pymodbus-version-pin.md)
- Telegraf request 新語法：[ADR-003](../adr/ADR-003-telegraf-modbus-request-syntax.md)
- PostgREST 連線格式：[ADR-004](../adr/ADR-004-postgrest-connection-string-format.md)
- DB schema 雙層隔離：[ADR-005](../adr/ADR-005-db-schema-isolation.md)
- KC 鏈路獨立：[ADR-006](../adr/ADR-006-kc-factory-separate-pipeline.md)
- MQTT topic 命名：[ADR-007](../adr/ADR-007-mqtt-topic-naming.md)
- Grafana 對外 Cloudflare Tunnel：[ADR-008](../adr/ADR-008-cloudflare-tunnel-grafana-public-access.md)

## 關鍵性等級

| 容器 | 失效衝擊 | 備援 |
|------|---------|------|
| timescaledb | 🔴 全系統中斷 | 無（單點，待補：streaming replica） |
| mosquitto | 🔴 全資料流斷 | 無（QoS1 短時暫存） |
| gateway / kc-gateway | 🟠 該域資料流斷 | 無 |
| ingest / kc-ingest | 🟡 短時延遲（QoS1 buffer） | 無 |
| grafana | 🟢 視覺化停，資料仍寫入 | 無 |
| query (postgrest) | 🟢 歷史查詢停 | 可重啟 |
| simulator | 🟢 測試流斷 | 無（dev only） |
