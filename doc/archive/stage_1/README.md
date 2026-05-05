# Stage 1：資料管線通了 — 進度紀錄

> 完成日期：2026-04-22
> 相關文件：
> - `C:\Users\User\Documents\EMS\實作提案_MVP架構.md`（Stage 定義）
> - `C:\Users\User\Documents\EMS\自學架構.md`（§5 階段 2 通訊協定實作）
> - 根目錄 `README.md`（啟動與驗收指令）

---

## 1. 達成狀態

**✅ Stage 1 所有驗收條件通過**

目標：6 個容器一條龍啟動、資料從假電表 → TimescaleDB → REST API 端到端流通。

---

## 2. 交付的資料管線

```
┌──────────┐  Modbus  ┌──────────┐  MQTT  ┌──────────┐  SQL  ┌─────────────┐  HTTP  ┌──────────┐
│simulator │ ──TCP──▶│ gateway  │───────▶│ ingest   │──────▶│ TimescaleDB │◀──────│  query   │
│(Python)  │   :5020  │(Telegraf)│         │(Telegraf)│       │             │  :3001 │(PostgREST)│
└──────────┘          └──────────┘         └──────────┘       └─────────────┘        └──────────┘
                            │                    ▲
                            └────── Mosquitto ───┘
                                      :1883
```

---

## 3. 容器清單

| # | 容器 | 鏡像 | 對外 Port | 功能 | 自寫？ |
|---|------|------|----------|------|-------|
| 1 | ems-simulator | ems-simulator（本地 build） | 5020, 8001 | 假電表（Python + FastAPI + pymodbus 3.6.9） | ✅ |
| 2 | ems-gateway | telegraf:1.30 | — | Modbus TCP → MQTT | ❌ 只 config |
| 3 | ems-mosquitto | eclipse-mosquitto:2 | 1883 | MQTT broker | ❌ |
| 4 | ems-ingest | telegraf:1.30 | — | MQTT → TimescaleDB | ❌ 只 config |
| 5 | ems-timescaledb | timescale/timescaledb:latest-pg15 | 5432 | 時序資料庫 | ❌ schema only |
| 6 | ems-query | postgrest/postgrest:14.10 | 3001 | REST API | ❌ 只 env var |

> 「開源優先」原則驗證成功：**原本想自寫的 5 個服務，實際只有 simulator 需要自寫 Python**，其他都是 config / env var。

---

## 4. 驗收結果

### 4-1. 步驟清單

| 步驟 | 指令 | 結果 |
|------|------|------|
| 1. simulator 活著 | `curl http://localhost:8001/health` | `{"status":"ok"}` ✓ |
| 2. MQTT 有資料 | `docker exec ems-mosquitto mosquitto_sub -t 'ems/#' -v` | 每秒一筆、值正確 ✓ |
| 3. DB 有資料 | `SELECT * FROM electricity_measurements ORDER BY time DESC LIMIT 3` | row 持續寫入 ✓ |
| 4. REST API | `curl 'http://localhost:3001/electricity_measurements?order=time.desc&limit=3'` | 回 JSON，數值正確 ✓ |

### 4-2. 實際資料樣本

MQTT（Influx Line Protocol）：
```
ems/devices/sim-001/measurements
measurements,device_id=sim-001,name=sim-001,slave_id=1,type=holding_register
  voltage=217.5,current=10.7,power_kw=60.02,energy_kwh=2.66
  1776850769000000000
```
> **v5 注**：ILP measurement name `measurements` 已於 v5 更名為 `electricity_measurements`。以上為 Stage 1 當時的實際截獲樣本（歷史紀錄）。

REST API 回傳：
```json
[
  {
    "time": "2026-04-22T09:41:31+00:00",
    "device_id": "sim-001",
    "voltage": 223,
    "current": 9.9,
    "power_kw": 65.04304504394531,
    "energy_kwh": 4.555764198303223
  }
]
```

---

## 5. 過程中修的 5 個 Bug

| # | 問題 | 根因 | 修法 | 相關檔案 |
|---|------|------|------|---------|
| 1 | simulator `ImportError: cannot import name 'ModbusSlaveContext'` | pymodbus 3.13 大改寫（新 SimData/SimDevice API），經典 API 被砍 | 鎖定 `pymodbus==3.6.9`（最後一個穩定的經典 API 版本） | `services/simulator/requirements.txt` |
| 2 | gateway `device name is empty` | Telegraf Modbus plugin 的 `name` 是必填的裝置識別名 | 加 `name = "sim-001"` | `services/gateway/telegraf.conf` |
| 3 | ingest `timestamp_column 不存在` | 我誤用了不存在的設定（Telegraf postgresql 預設用 `time` 欄） | 整行刪掉 | `services/ingest/telegraf.conf` |
| 4 | `power_kw=1112514027`（raw bytes 沒解成 float） | Telegraf legacy `holding_registers` 語法對 FLOAT32 解碼行為不完整 | 改用新的 `[[inputs.modbus.request]]` 語法，每個欄位明標 `output = "FLOAT64"` | `services/gateway/telegraf.conf` |
| 5 | PostgREST `could not translate host name "WSX@timescaledb"` | 密碼 `1qaz@WSX` 裡的 `@` 被 URI 解析成 user-host 分隔符 | 把 `PGRST_DB_URI` 從 URI 格式改為 key=value 格式 | `docker-compose.yml` |

### Bug 教訓速記

- **Bug #1**：上游套件鎖版很重要。pymodbus 3.6 到 3.13 API 改了兩次，新的 `pymodbus>=3.6,<4.0` 區間橫跨了 breaking change。教訓：寫非核心依賴也要鎖到 minor version。
- **Bug #4**：Telegraf 同一個 plugin 有新舊兩套 config 語法時，新的（`[[inputs.modbus.request]]`）通常比較完整、除錯資訊比較清楚。
- **Bug #5**：連線字串遇到特殊字元（`@`、`:`、`/`）時，key=value 格式比 URI 格式穩定。PostgreSQL 系列工具多半兩種都支援。

---

## 6. 關鍵設計決策

1. **「能用開源就不手搓」**：gateway / ingest 都用 Telegraf 設定取代自寫，query 用 PostgREST 直接把 DB schema 曝為 REST API
2. **嚴格一服務一 container**：gateway 和 ingest 都是 Telegraf，但各自一個 container、各自一份 config，不合併
3. **Influx Line Protocol 當 Telegraf 間資料格式**：比 JSON 保留 tag / field / timestamp 語意完整
4. **TimescaleDB schema 預先建立**：`init.sql` 定義 `electricity_measurements` hypertable（原 `measurements`，v5 更名），不讓 Telegraf auto-create 表格；保持 schema 控制權
5. **PostgREST 暴露 `api` schema（不是 `public`）**：view-only 隔離，未來加寫入 endpoint 時能獨立控權
6. **密碼敏感資料走 env var**：`.env` 已在 `.gitignore`，`.env.example` 作為範本
7. **PostgreSQL 需要 env 變數的部分獨立成 `02-authenticator.sh`**：因為 `.sql` 檔在 PostgreSQL 的 initdb 階段不能讀環境變數，shell script 可以

---

## 7. 遇到的取捨

| 取捨點 | 選擇 | 放棄 | 理由 |
|--------|------|------|------|
| pymodbus 版本 | 3.6.9 鎖死 | 跟最新 3.13 一起走 | 3.13 是 SimData 重寫、遷移成本遠大於 MVP 所需 |
| Telegraf modbus 設定語法 | `[[inputs.modbus.request]]` 新版 | legacy `holding_registers` | 新版 FLOAT32 解碼正確、語意更清楚 |
| 連線字串格式 | `key=value` | URI `postgres://...` | 特殊字元免 URL-encode |
| 前端方案 | 延後到 Stage 2 用 Grafana | 自寫 React | 開源優先原則、Grafana 同時能做告警 |

---

## 8. 如何從零重現

```bash
# 1. clone / 到專案根
cd ~/synaiq/EMS

# 2. 備好環境變數
cp .env.example .env
# 編輯 .env：至少填 POSTGRES_PASSWORD 和 AUTHENTICATOR_PASSWORD

# 3. 啟動
docker compose up -d

# 4. 等 ~30 秒讓 timescaledb 完成 initdb 階段

# 5. 驗收
curl http://localhost:8001/health
curl 'http://localhost:3001/electricity_measurements?order=time.desc&limit=5'
```

完全重來（砍資料重建）：
```bash
docker compose down -v
docker compose up -d
```

---

## 9. 已知副作用 / 待清

- **DB 裡有 ~20 筆「假 kW」**（Bug #4 修前的資料，`power_kw > 1000`）。Stage 2 儀表板可 filter 掉，或直接 `DELETE FROM electricity_measurements WHERE power_kw > 1000;`
- **Windows 端 `C:\Users\User\synaiq\EMS\` 仍有一份備份拷貝**。WSL 端是單一真相，Windows 這份待刪

---

## 10. 下一步（Stage 2 預告）

| 項目 | 開源工具 | 程式碼量 |
|------|---------|---------|
| 儀表板 | Grafana container | 0，用 provisioning yaml |
| 告警引擎 | Grafana Alerting（built-in） | 0，在 UI 配 |
| Telegram 通知 | Grafana contact point → Telegram | 貼 bot token + chat_id |
| 第一張 dashboard | voltage / current / power_kw / energy_kwh 曲線 + 即時數值 panel | 0 |
| 第一條告警 | `power_kw > 100 sustained for 30s` → Telegram | 0 |

Stage 2 預估：**幾乎純配置，不寫程式碼**。主要工作是學 Grafana dashboard provisioning 檔案格式 + 設 Telegram 整合。
