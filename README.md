# synaiq EMS

自主研發的商用 **EMS（Energy Management System）** —— 從電力資料採集、可視化、告警，一路延伸到工廠環境監測與 AI 控制面（MCP）。

> 對標 Schneider PME、研華 WebAccess/EMS 等國際成熟產品，差異化定位在**台灣在地化**（台電費率、需量管理）、**AI 主動控制**（MCP 協定原生支援）、與**可深度客製**的整體架構。

## 這個系統能做到什麼

| 能力 | 說明 |
|------|------|
| **電力資料管線** | Modbus 電表（POC 階段以模擬器替代）→ 端到端串流寫入時序資料庫，延遲 < 15 秒 |
| **歷史資料 REST API** | 對外曝露電力與工廠量測資料的查詢接口，支援彈性過濾、排序、分頁語法 |
| **即時可視化** | 整合儀表板涵蓋電力曲線、工廠環境趨勢、設備狀態時間軸 |
| **告警鏈路** | 自訂閾值 / 持續時間規則 → Telegram 即時通知，附事件時間、設備、超限值 |
| **工廠環境整合** | 工廠 PLC 與環境感測器與電表共用同一條管線，單一資料平台統一管理 |
| **AI 控制面（MCP）** | 原生 MCP 介面，讓 Claude / 其他 AI Agent 用自然語言讀寫 PLC 暫存器 |
| **故障注入測試** | 模擬器提供故障注入 API，方便驗證告警鏈路與恢復流程 |
| **一鍵部署 / 重建** | 容器化部署，單一指令啟動整套系統；可在不影響規格的情況下完整重建 |

## 預期達到什麼

長線目標是把這套系統推進到能取代台灣商用 EMS 競品的位置，路徑分五個方向：

1. **資料平台**：把採集 / 儲存 / 查詢 / 視覺化做穩、做快，作為所有上層能力的地基。

2. **裝置自動登錄與 AI 輔助分類**：
   - 裝置中繼資料集中於**單一 source of truth**，取代散落於部署設定、採集設定、資料庫 migration 的現況
   - 新裝置接上後，系統主動偵測（MQTT 訂閱），無需人工修改部署設定
   - **可切換的 LLM 服務介面**自動分類裝置類型與訊號定義，支援雲端服務與離線本地部署，依成本 / 隱私需求自由切換
   - **信心分流**：高信心結果自動納管；低信心進入人工確認佇列，並以 MCP 工具讓 AI Agent 與運維協作補充上下文
   - **三層分權**（運維 / 採集端 / AI）的 API 鑑別，防止偽造裝置灌爆系統與越權修改主資料

3. **設備管理與控制面**：提供裝置 CRUD、設定下發、採集服務動態 reload；MCP 控制面從「讀寫模擬器」進化為具備權限邊界的正式控制流程。

4. **業務計算**：台電三段式費率、契約容量、15 分鐘需量、能源報表 —— 在地化是這套系統相對國際產品的核心差異。

5. **AI 主動控制**：以 MCP 為介面，讓 Agent 在告警 / 排程 / 最佳化情境下自動下發控制指令，並以審計與權限機制守住安全邊界。

各階段的需求、驗收與設計取捨見 `doc/prd/`；目前實作狀態見 `doc/prd/README.md` 索引表。

## 系統架構

### 電力資料管線

```text
┌──────────┐  Modbus  ┌──────────┐   MQTT   ┌──────────┐   SQL   ┌────────────┐   HTTP   ┌────────────┐
│電表模擬器│ ── TCP ─▶│採集閘道  │ ────────▶│寫入服務  │ ──────▶│時序資料庫  │ ───────▶│查詢 API    │
│          │   :5020  │          │          │          │        │            │          │ :3001      │
└──────────┘          └──────────┘          └──────────┘        └────────────┘          └────────────┘
                                                                       │
                                                                       ▼
                                                                ┌────────────┐
                                                                │監控儀表板  │
                                                                │ :3000      │
                                                                └────────────┘
```

### 工廠資料與 AI 控制面

```text
┌──────────────┐  Modbus  ┌──────────────┐   MQTT   ┌──────────────┐   SQL   ┌────────────────────┐
│工廠 PLC      │ ── TCP ─▶│工廠採集閘道  │ ────────▶│工廠寫入服務  │ ──────▶│工廠量測資料表      │
│模擬器 :5021  │          │              │  ems/    │              │        │（時序資料庫）      │
└──────────────┘          └──────────────┘  factory └──────────────┘        └────────────────────┘
        ▲
        │ MCP read/write
        │
┌──────────────┐
│AI 控制面     │  Streamable HTTP MCP endpoint: http://localhost:8765/mcp
│(MCP Server)  │
└──────────────┘

┌──────────────┐
│工廠感測器    │  MQTT topic: factory/sensor/temp_01（JSON 格式）
│模擬器        │
└──────────────┘
```

MQTT topic 命名規範詳見 `doc/adr/ADR-007-mqtt-topic-naming.md`：主規範為 `ems/<domain>/{device_id}/measurements`（電表 `ems/devices/...`、工廠 PLC `ems/factory/...`）；JSON 格式感測器為例外，沿用上游 topic 由工廠寫入服務解析。

工廠資料的可視化依工廠環境監測常見做法分成：即時狀態 gauge、環境趨勢 time series、設備狀態 state timeline、最新資料 table。

## 服務組成

| 服務 | 對外 Port | 用途 |
|------|----------|------|
| 電表模擬器 | 5020 (Modbus), 8001 (REST) | POC 階段模擬電表，提供故障注入 API |
| 電力採集閘道 | — | 電表 → MQTT |
| MQTT broker | 1883 | 訊息路由 |
| 電力寫入服務 | — | MQTT → 時序資料庫 |
| 時序資料庫 | 5432 | 量測資料儲存 |
| 查詢 API | 3001 | 對外歷史資料查詢 |
| 監控儀表板 | 3000 | 可視化與告警 UI |
| 工廠 PLC 模擬器 | 5021 | POC 階段模擬工廠 PLC |
| 工廠感測器模擬器 | — | POC 階段模擬 JSON 感測器 |
| 工廠採集閘道 | — | PLC → MQTT |
| 工廠寫入服務 | — | MQTT → 工廠量測資料表 |
| AI 控制面 (MCP Server) | 8765 (本機) | MCP client 讀寫設備暫存器 |

## 快速入口

| 入口 | URL / 指令 | 用途 |
|------|------------|------|
| 監控儀表板 | <http://localhost:3000/d/ems-overview> | EMS Overview，含電力與工廠視覺化 |
| 電力資料查詢 API | <http://localhost:3001/electricity_measurements?order=time.desc&limit=10> | 查詢歷史電力資料 |
| 工廠資料查詢 API | <http://localhost:3001/factory_measurements?order=time.desc&limit=10> | 查詢溫度、濕度、壓力、馬達、Pump、Valve |
| 模擬器健康檢查 | <http://localhost:8001/health> | 電表模擬器健康狀態 |
| MCP endpoint | `http://localhost:8765/mcp` | 供 MCP client 連線（非瀏覽器頁面） |

MCP endpoint 用瀏覽器直接打開會看到 `Not Acceptable: Client must accept text/event-stream`，這是正常的；它需要 MCP client 以 `Accept: application/json, text/event-stream` 連線。

## 啟動

```bash
# 第一次跑先複製環境變數
cp .env.example .env

# 編輯 .env 填入實際值
# 至少確認 POSTGRES_PASSWORD、AUTHENTICATOR_PASSWORD
# 若要 Telegram 告警，再確認 TELEGRAM_BOT_TOKEN、TELEGRAM_CHAT_ID

docker compose up -d
```

等約 30 秒讓所有服務起來：

```bash
docker compose ps
```

## 系統健康檢查

下列步驟用來確認整套系統在你的環境上是活的。完整除錯流程見 `doc/operations/操作手冊.md`。

### 1. 模擬器活著

```bash
curl http://localhost:8001/health
# 期望：{"status":"ok"}
```

### 2. 查詢 API 拿得到資料

```bash
curl 'http://localhost:3001/electricity_measurements?order=time.desc&limit=10'
curl 'http://localhost:3001/factory_measurements?order=time.desc&limit=10'
```

電力資料每筆應含 `time`、`device_id`、`voltage`、`current`、`power_kw`、`energy_kwh`；工廠資料每筆應含 `time`、`device_id`、`temperature_c`、`humidity_pct`、`pressure_kpa`、`motor_rpm`、`pump_on`、`valve_open`。

### 3. 監控儀表板可開啟

```text
http://localhost:3000/d/ems-overview
```

預設帳密未變更時為 `admin / admin`。Dashboard 應包含 `KC 工廠環境與設備狀態` row，含溫度、濕度、壓力、馬達轉速、Pump / Valve 狀態、趨勢圖、狀態時間軸與最新資料表。

### 4. AI 控制面可由 MCP client 連線

```bash
npx @modelcontextprotocol/inspector
```

Inspector 設定：

```text
Transport: Streamable HTTP
URL: http://localhost:8765/mcp
Command / Args / Environment: 留空
```

## 除錯

完整除錯流程、常見問題排查、log 解讀方式見 `doc/operations/操作手冊.md` 與 `doc/operations/容器速查表.md`。

最常用的兩個指令：

```bash
docker compose ps                    # 看哪個服務掛了
docker compose logs -f <服務名>       # 持續追蹤特定服務 log
```

完全重建（會清空歷史資料）：

```bash
docker compose down -v && docker compose up -d
```

## 資料夾結構

```text
.
├── README.md                # 系統能力總覽與快速入口（本檔）
├── project_rules.md         # 專案規定；重要變更後需同步文件
├── docker-compose.yml       # 一條龍啟動所有服務
├── .env.example             # 環境變數範本
├── api/
│   └── openapi.yml          # 對外 API schema
├── config/                  # 設備與服務設定
├── doc/                     # 規範、PRD、ADR、架構、運維文件
│   ├── PRD-架構設計-Guideline.md
│   ├── prd/                 # 正式 PRD（含實作狀態索引）
│   ├── architecture/        # C4 Context / Container / Data Flow
│   ├── adr/                 # Architecture Decision Records
│   ├── governance/          # NFR、風險登記簿、威脅建模
│   ├── operations/          # 操作手冊、容器速查表、對外公開指南
│   └── archive/             # 已被 PRD 取代的歷史規劃
├── infra/                   # 資料庫初始化、broker、儀表板 provisioning
└── services/                # 自有服務模組（電表 / 採集 / 寫入 / 工廠 / MCP）
```

## 文件索引

> **新人 / 接手工程師閱讀順序**：`project_rules.md` → `doc/PRD-架構設計-Guideline.md` → `doc/prd/`（既有 PRD 全部讀過）→ `doc/architecture/` → `doc/adr/` → 才開始動手。詳見 `project_rules.md` §14。

### 想知道目前進度 / 路線圖？

| 文件 | 內容 |
|------|------|
| `doc/prd/README.md` | PRD 索引表，含每個 PRD 的**實作狀態**（Draft / Reviewed / Approved / Implemented / Deprecated） |
| `doc/prd/PRD-0001-Stage1-Stage2-Foundation.md` | 電力資料管線、可視化、告警的需求與驗收 |
| `doc/prd/PRD-0002-KC-Factory-Integration.md` | 工廠 PLC 整合與 AI 控制面的需求與驗收 |
| `doc/prd/PRD-0003-Device-Registry-Auto-Discovery.md` | 裝置自動登錄、AI 輔助分類、人機協作確認佇列 |
| `doc/archive/plan/EMS實作計畫.md` | 原始 Stage 規劃（已 PRD 化） |
| `doc/archive/plan/kc_integration_plan.md` | 工廠整合 phase 進度（已 PRD 化） |

### 規範與架構（動手前必讀）

| 文件 | 用途 |
|------|------|
| `project_rules.md` | 專案規定；架構強制遵循 Guideline、PRD-first、文件四同步、測試規範 |
| `doc/PRD-架構設計-Guideline.md` | 架構設計權威 Guideline（15 章節 PRD 結構） |
| `doc/architecture/` | C4 Context / Container / Data Flow 圖 |
| `doc/adr/` | Architecture Decision Records |
| `doc/governance/nfr.md` | 量化 Non-Functional Requirements |
| `doc/governance/risk-register.md` | 風險登記簿 |
| `doc/governance/threat-model.md` | 威脅建模（STRIDE） |

### 操作與運維

| 文件 | 用途 |
|------|------|
| `doc/operations/操作手冊.md` | 主要操作流程、除錯、故障排查 |
| `doc/operations/容器速查表.md` | 各服務的端口、職責、log、重建與安全基線 |
| `doc/operations/network/Cloudflare_Grafana_Demo_對外公開操作指南.md` | 對外公開儀表板 demo 操作指南 |

### API

| 文件 | 用途 |
|------|------|
| `api/openapi.yml` | 對外 API schema（查詢 API + 模擬器 + 儀表板管理 API） |
