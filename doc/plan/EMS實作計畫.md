# EMS MVP 實作提案

> 建立日期：2026-04-22
> 狀態：**等待你對齊 → 開始實作**
> 依據：`自學架構.md`、`開源專案列表.md`、`比較分析/D_架構定位比較.md`

---

## 一、設計原則

1. **先求有**：6 週內看得到假電表資料流到前端儀表板
2. **可擴充**：每個功能是獨立微服務，換語言、加協定、換 DB 都不影響其他服務
3. **微服務 + REST**：服務控制走 REST API，資料串流走 MQTT（理由見 §四）
4. **對齊自學架構**：Mock Level 2 模擬器當資料源（不用等買電表）
5. **台灣在地化可插拔**：費率計算、15 分鐘需量做成獨立服務，未來容易替換

---

## 二、整體架構

```
[Level 2 模擬器]                         [未來：真實電表]
       │                                       │
       │ Modbus TCP                            │ Modbus RTU
       ▼                                       ▼
┌─────────────────┐    REST    ┌──────────────────┐
│ gateway-service │ ◀────────  │ device-service   │
│   (通訊接入)    │  /devices   │   (設備 CRUD)    │
└────────┬────────┘            └────────▲─────────┘
         │ MQTT publish                 │ REST
         ▼                              │
┌──────────────────┐                    │
│ Mosquitto Broker │                    │
└─┬─────────┬──────┘                    │
  │ sub     │ sub                       │
  ▼         ▼                           │
┌──────┐ ┌──────────┐  ┌────────────────▼─┐
│ingest│ │realtime  │  │  alarm-service   │
│svc   │ │service   │  │   (告警引擎)      │
└──┬───┘ └────┬─────┘  └───────┬──────────┘
   │ SQL     │ WS             │ 通知
   ▼         │                ▼
┌──────────┐ │         [LINE / Email]
│Timescale │ │
│  DB      │ │
└──▲───────┘ │
   │ SQL     │
┌──┴───────┐ │       ┌─────────────────┐
│query-svc │ │       │business-service │
│(歷史查詢)│ │       │(需量+費率)      │
└──▲───────┘ │       └────────▲────────┘
   │ REST    │ WS             │ REST
   │         │                │
   └─────┬───┴────────────────┘
         │
    ┌────▼─────────┐
    │  frontend    │
    │ (React SPA)  │
    └──────────────┘
```

---

## 三、服務列表與 REST API

### 1. gateway-service（通訊接入層）
**職責**：連接 Modbus 設備、輪詢、發 MQTT

| Method | Path | 用途 |
|--------|------|------|
| GET | `/health` | 健康檢查 |
| GET | `/devices` | 目前在輪詢的設備清單 + 最後讀取時間 |
| POST | `/devices/{id}/read` | 強制重讀一次（除錯用）|
| POST | `/reload` | 從 device-service 重拉設備清單並重啟輪詢 |

### 2. ingest-service（資料寫入）
**職責**：subscribe MQTT、批次寫 TimescaleDB

| Method | Path | 用途 |
|--------|------|------|
| GET | `/health` | — |
| GET | `/stats` | 寫入速率、最後寫入時間、緩衝深度 |

### 3. query-service（歷史查詢）
**職責**：對外查歷史資料的 REST API

| Method | Path | 用途 |
|--------|------|------|
| GET | `/measurements?device_id=&channel=&from=&to=&agg=` | 歷史曲線，agg = raw/1m/15m/1h |
| GET | `/measurements/latest?device_id=` | 最新值 |
| GET | `/measurements/stats?device_id=&period=day\|week\|month` | 統計值 |

### 4. realtime-service（即時推送）
**職責**：WebSocket server，將 MQTT 轉譯給瀏覽器

| 類型 | Path | 用途 |
|------|------|------|
| WebSocket | `/ws?device_id=&channel=` | 訂閱即時值 |
| REST GET | `/health` | — |
| REST GET | `/connections` | 目前 WebSocket 連線數 |

### 5. device-service（設備管理）
**職責**：設備 metadata CRUD

| Method | Path | 用途 |
|--------|------|------|
| GET | `/devices` | 列表 |
| GET | `/devices/{id}` | 單一設備 |
| POST | `/devices` | 新增 |
| PUT | `/devices/{id}` | 修改 |
| DELETE | `/devices/{id}` | 刪除（保留歷史資料）|

**事件通知**：設備變更後，回呼 `gateway-service` 的 `POST /reload`。

### 6. alarm-service（告警引擎）
**職責**：subscribe MQTT、評估規則、觸發通知

| Method | Path | 用途 |
|--------|------|------|
| GET/POST/PUT/DELETE | `/rules` | 告警規則 CRUD |
| GET | `/alarms/active` | 目前觸發中的告警 |
| POST | `/alarms/{id}/ack` | 確認告警 |
| GET | `/alarms/history?from=&to=` | 告警歷史 |

### 7. business-service（業務邏輯）
**職責**：15 分鐘需量計算 + 台電費率計算

| Method | Path | 用途 |
|--------|------|------|
| GET | `/demand/current?device_id=` | 目前 15 分鐘 bucket 平均 |
| GET | `/demand/max?device_id=&month=YYYY-MM` | 當月最大需量 |
| POST | `/tariff/calculate` | 給定用電區間 → 估算電費 |
| GET | `/tariff/config` | 目前費率設定 |

### 8. simulator-service（僅 dev 環境）
**職責**：Level 2 Modbus 模擬器

- **Modbus TCP Server** on port 5020（給 gateway 連）
- REST:

| Method | Path | 用途 |
|--------|------|------|
| GET | `/config` | 目前模擬參數 |
| POST | `/config` | 改 kW 範圍、雜訊大小、波形類型 |
| POST | `/inject-fault` | 注入錯誤（timeout、錯誤值）測試告警 |

### 9. frontend（React SPA）
呼叫上述所有服務的 REST + WebSocket。

---

## 四、為什麼不全走 REST？

你提到「透過 REST API call 功能支援」方向對了——**服務控制（control plane）確實應該走 REST**。但「資料串流（data plane）」若也強行走 REST 會有三個問題：

1. **扇出問題**：gateway 每秒的量測資料要 push 給 3 個消費者（ingest / realtime / alarm），gateway 必須自己維護每個人的 URL、重試、緩衝——這是 MQTT 已經解決過的問題
2. **耦合問題**：想加第 4 個消費者（例如未來的 AI 預測服務）要改 gateway 程式碼
3. **效能問題**：200 支電表 × 每秒 10 個 channel = 每秒 2000 次 HTTP 連線，太貴

### 混合模式（建議）

| 場景 | 機制 |
|------|------|
| 資料串流（即時量測值）| **MQTT**（pub-sub、解耦、重播）|
| 服務控制 / 查詢（改設定、查歷史、算費率）| **REST** |
| 前端即時顯示 | **WebSocket**（訂閱 realtime-service，後者從 MQTT 轉譯）|
| 服務間事件（加設備 → 閘道重載）| **REST callback**（簡單）或 MQTT event topic（解耦）|

這是工業界事實標準——ThingsBoard、Home Assistant、OpenEMS 都是類似混合模式。

---

## 五、技術棧

| 層 | 選擇 | 理由 |
|---|-----|------|
| 後端語言 | **Python 3.11+** | pymodbus 最成熟、生態廣 |
| Web framework | **FastAPI** | REST + WebSocket 一體；Pydantic 驗證；非同步原生 |
| Modbus | **pymodbus 3.x** | 事實標準 |
| MQTT client | **paho-mqtt** | Eclipse 官方 |
| MQTT broker | **Mosquitto** | 輕量、Docker 一條龍 |
| DB | **TimescaleDB**（PostgreSQL）| 自學架構已選 |
| ORM | **SQLAlchemy 2.0 (async)** + **asyncpg** | 非同步、成熟 |
| 測試 | **pytest + httpx.AsyncClient** | FastAPI 標配 |
| 容器化 | **Docker + Docker Compose** | 一條龍起服務 |
| 前端 | **React + TypeScript + Vite** | 生態成熟 |
| 圖表 | **Apache ECharts** | 效能、內建 dataZoom |

---

## 六、資料夾結構

```
ems-mvp/
├── README.md
├── docker-compose.yml
├── .env.example
│
├── shared/                         # 共用 Python package
│   ├── pyproject.toml
│   └── ems_shared/
│       ├── __init__.py
│       ├── schemas.py              # Pydantic models 共用
│       ├── mqtt_topics.py          # topic 命名規範
│       └── db.py                   # DB 連線 helper
│
├── services/
│   ├── simulator/
│   │   ├── Dockerfile
│   │   ├── pyproject.toml
│   │   └── src/simulator/
│   │       ├── main.py             # Modbus TCP slave + FastAPI
│   │       ├── waveform.py         # 假資料產生邏輯
│   │       └── api.py
│   │
│   ├── gateway/
│   │   └── src/gateway/
│   │       ├── main.py             # FastAPI entry
│   │       ├── modbus_poller.py    # 輪詢循環
│   │       ├── device_profile.py   # register map 解析
│   │       └── mqtt_publisher.py
│   │
│   ├── ingest/
│   ├── query/
│   ├── realtime/
│   ├── device/
│   ├── alarm/
│   └── business/
│
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   └── src/
│       ├── App.tsx
│       ├── pages/
│       ├── components/
│       └── api/                    # API client（對各服務）
│
└── scripts/
    ├── init_db.sql                 # TimescaleDB hypertable 建立
    └── seed_devices.sql            # 測試用設備資料
```

---

## 七、MVP 分階段（6 週）

### Stage 1：資料管線通了（第 1~2 週）
`docker compose up` 即可跑：
- [x] TimescaleDB + Mosquitto 啟動
- [x] simulator 產假資料
- [x] gateway 讀 simulator、發 MQTT
- [x] ingest 寫 TimescaleDB
- [x] query REST API 能查到歷史

**驗收**：`curl http://localhost:8002/electricity_measurements?device_id=sim-001&from=...&to=...` 回得到資料

### Stage 2：看得到（第 3 週）
- [x] realtime-service WebSocket 推送
- [x] frontend 顯示即時卡片 + 24hr 曲線

**驗收**：瀏覽器打開儀表板，值每秒更新

### Stage 3：動得了（第 4 週）
- [x] device-service CRUD
- [x] gateway 接收 `/reload` 動態調整輪詢
- [x] frontend 「設備管理」頁

**驗收**：UI 新增設備 → 1 分鐘內儀表板出現新設備的值

### Stage 4：會吵（第 5 週）
- [x] alarm-service 閾值規則引擎
- [x] LINE Notify 整合
- [x] frontend 告警列表頁

**驗收**：設「kW > 100 告警」、透過 simulator `/inject-fault` 觸發 → 2 秒內收到 LINE

### Stage 5：算得出來（第 6 週）
- [x] business-service 15 分鐘需量
- [x] 簡易台電費率計算（高壓兩段式時間電價）
- [x] frontend 需量曲線 + 電費估算頁

**驗收**：算的當月最大需量 vs 手算 < 1% 誤差

### Stage 6：多路徑回控（讓用戶選控制方式）

**目標**：系統從「純監控」升級到「有限可控」。新增統一控制入口 `control-service`，支援三條路徑，用戶與規則都能選擇要走哪條；所有控制動作集中審計留存。

#### 三條控制路徑

| 路徑 | 機制 | 適用場景 |
|------|------|---------|
| **AI 路徑** | control-service → kc-mcp-server（MCP）→ Modbus | 自然語言指令、複合判斷、讓 Claude 代理執行 |
| **直接路徑** | control-service → gateway-service write API → Modbus TCP | 前端按鈕觸發、低延遲、確定性點對點操作 |
| **規則路徑** | alarm-service 觸發 → control-service → 任一路徑 | 告警聯動自動回控（如高溫 → 關閥、功率超限 → 卸載）|

#### 需要實作

- [ ] `control-service`（新服務）
  - `POST /control/{device_id}/write`：接受 `path=ai|direct|auto` 參數，路由到對應執行層
  - `GET /control/audit`：控制動作歷史（who / when / path / payload / result）
  - `GET /control/paths`：列出目前可用路徑與健康狀態
- [ ] `gateway-service` 擴充：加 `POST /devices/{id}/write`，直接 Modbus TCP 寫暫存器或線圈（直接路徑的執行端）
- [ ] `alarm-service` 擴充：規則加選填 `action` 欄位，觸發時呼叫 control-service（規則路徑的發起端）
- [ ] `kc-mcp-server` 正式接入（已存在，Stage 6 將它從「AI 專用接口」納入 EMS 正式控制鏈）
- [ ] `frontend` 控制面板：設備列表 → 選路徑 → 填值 → 送出，即時顯示執行結果
- [ ] `frontend` 控制歷史頁：列出所有回控動作記錄，可篩選路徑、設備、時間

#### 服務關係圖

```
用戶（前端）          alarm-service         Claude AI
    │                      │                    │
    │ POST /write           │ on_trigger action  │ MCP call
    └──────────┬────────────┘                    │
               ▼                                 │
        control-service  ◀───────────────────────┘
         │           │
    path=direct   path=ai
         │           │
  gateway-service  kc-mcp-server
  /devices/write    (MCP server)
         │           │
         └─────┬─────┘
               ▼
         Modbus TCP → PLC / 設備
```

**驗收**：
1. 前端「直接路徑」寫入 `plc-001` 的 `motor_speed=1500` → DB 確認新值
2. 前端「AI 路徑」發送「把馬達轉速設為 1200」→ Claude 透過 MCP 執行 → DB 確認
3. 設定規則：`temperature > 80°C` 觸發 `pump_on=true`（規則路徑）→ 收 Telegram + DB 確認
4. `GET /control/audit` 列出以上三筆記錄，含路徑、payload、執行結果

---

## 八、擴充點

| 未來要做什麼 | 怎麼加 | 不會影響什麼 |
|-------------|-------|-----------|
| 支援 OPC-UA 協定 | 新建 `gateway-opcua` 服務，同樣發 MQTT | 其他服務不動 |
| 支援多租戶 | device-service 加 `tenant_id`、MQTT topic 加租戶層級、query 加過濾 | 通訊協定與資料管線不變 |
| 多個客戶廠區 | 每廠區一套 gateway + simulator，中央服務共用 | 中央服務不變 |
| 新通知管道（Slack / Email） | alarm-service 加 handler | 其他服務不動 |
| 換 TimescaleDB 為 InfluxDB | 只改 ingest + query 兩個服務 | 其他不變 |
| 加 AI 需量預測 | 新建 `prediction-service` 訂閱 MQTT、寫結果到 DB | 其他不動 |
| 對外開放 API 給第三方 | 新建 `public-api-service` + API key 管理 | 內部服務不動 |
| 邊緣部署 | gateway 改跑在 Raspberry Pi，中央服務不變 | — |

**擴充原則**：每次「加服務」或「改一個服務」，不會動到全部。

---

## 九、需要你對齊的 5 個決策

### 決策 1：服務數量

MVP 我設計了 **7 個微服務 + simulator + frontend = 9 個 container**。

- **選項 A（照提案）**：9 個 container，最貼近「每個功能一個微服務」，擴充最乾淨
- **選項 B（合併）**：合併 ingest/query/alarm/business 成一個「core-service」，變 5 個 container，日後再拆

**我的建議**：**選項 A**。因為你明確說「將各階段還有個功能，包裝成微服務」；而且 Docker Compose 管 9 個服務不算難。但若 Stage 1 想先加速可先合併、逐步拆。

### 決策 2：語言

- 後端全 **Python**（FastAPI + pymodbus）
- 前端 **React + TypeScript**

可以嗎？或你有其他偏好（Node.js 後端？Go 閘道？）

### 決策 3：程式碼位置

建議放在 `C:\Users\User\Documents\EMS\ems-mvp\`，獨立 git repo。還是你想放別的地方？

### 決策 4：前端

Stage 2~5 都需要前端。你想：
- (a) 自己寫前端，我寫後端
- (b) 我一起寫前端（React + ECharts）
- (c) Stage 1~3 我全寫，你 review；後面你接手

### 決策 5：通知

Stage 4 的 LINE Notify：
- (a) 我整合真實的 LINE Notify API（你要提供 token）
- (b) 先用 console log + 存 DB，等你拿到 token 再接
- (c) 改用 Email（SMTP）或 Webhook

---

## 十、對齊後立即執行的項目

你確認上述 5 個決策後，我會先做：

1. 建立 `ems-mvp/` 專案骨架（含 `README`、`docker-compose.yml`、`.env.example`、資料夾結構）
2. 寫 `simulator-service`（Level 2 Modbus 模擬器 + FastAPI）
3. 寫 `gateway-service`（讀 simulator、發 MQTT）
4. 寫 `ingest-service`（MQTT → TimescaleDB）
5. 寫 `query-service`（REST 查歷史）
6. 設定 `docker-compose.yml` 起全套
7. 手動驗收 `curl /electricity_measurements` 成功

**這就是 Stage 1。預計 1~2 週完成。**

Stage 1 通了之後再動 Stage 2（realtime + frontend）。每 Stage 做完我都會停下來讓你看、提問。
