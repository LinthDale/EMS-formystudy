# ADR-001：Open-source-first 服務選型

## Status
Accepted（2026-04-22）

## Context

Stage 1 規劃 6 個容器的資料管線（simulator → gateway → mosquitto → ingest → DB → query）。原始直覺是每個服務都自寫 Python，估計 5 個服務、各 200-500 行程式碼，維運成本與 bug 面積大。

評估後發現：
- gateway（Modbus → MQTT）：Telegraf 內建 `inputs.modbus` + `outputs.mqtt`，純 config
- ingest（MQTT → DB）：Telegraf 內建 `inputs.mqtt_consumer` + `outputs.postgresql`
- query（REST API）：PostgREST 直接把 PostgreSQL schema 曝為 REST，零程式
- broker：Eclipse Mosquitto / EMQX 標準品
- DB：TimescaleDB（PostgreSQL 擴充）

只有 simulator 需要自寫（FastAPI + pymodbus + 模擬數值產生器）。

## Decision

**「能用開源就不手搓」。** 6 個容器中只有 simulator 自寫程式碼；其餘 5 個容器全部使用成熟開源工具，僅維護 config / env。

對應實作：
- gateway / ingest：`telegraf:1.30` + `telegraf.conf`
- mosquitto：`eclipse-mosquitto:2` + `mosquitto.conf`
- timescaledb：`timescale/timescaledb:latest-pg15` + `init.sql` + `02-authenticator.sh`
- query：`postgrest/postgrest:14.10` + 環境變數

## Consequences

**正面**
- Stage 1 自寫程式碼從 ~1500 行降至 ~200 行
- 工具已通過大量 production 驗證，bug 風險低
- 文件、社群、StackOverflow 答案豐富
- 可替換性高（Mosquitto → EMQX、Telegraf → 其他 collector）皆為標準介面

**負面**
- 受限於工具本身能力；客製化超出工具邊界時須切換或自寫
- 多套 config 語法（Telegraf TOML、Mosquitto conf、PostgREST env）學習成本
- 供應鏈依賴（image 升級、CVE 跟進）

**後續觸發**
- 若需求超出 Telegraf 能力（複雜協定轉換、有狀態計算），再評估自寫
- 升級 image 版本須走 ADR 補充（pymodbus 鎖版即為衍生案，見 ADR-002）
