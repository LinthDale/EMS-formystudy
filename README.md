# synaiq EMS

## 接手入口與資料地圖





## 模擬先行的 EMS 演進方案（2026-11-10）





長線 AI 控制能力以候選意圖、既定授權與站端確定性約束為邊界；設備自動分類不自動取得控制權。第一個切片為 PV＋負載＋BESS＋PCC 閉環，實機驗收留待設備取得後。

[![CI](https://github.com/LinthDale/EMS-formystudy/actions/workflows/ci.yml/badge.svg?branch=dev)](https://github.com/LinthDale/EMS-formystudy/actions/workflows/ci.yml)

自主研發的商用 **EMS（Energy Management System）** —— 從電力資料採集、可視化、告警，一路延伸到工廠環境監測、**裝置自動登錄與 AI 輔助分類**，以及 AI 控制面（MCP）。

> 對標 Schneider PME、研華 WebAccess/EMS 等國際成熟產品，差異化定位在**台灣在地化**（台電費率、需量管理）、**AI 主動控制**（MCP 協定原生支援）、與**可深度客製**的整體架構。

## 這個系統能做到什麼

| 能力 | 說明 |
|------|------|
| **電力資料管線** | Modbus 電表（POC 階段以模擬器替代）→ 端到端串流寫入時序資料庫，延遲 < 15 秒 |
| **歷史資料 REST API** | 對外曝露電力與工廠量測資料的查詢接口，支援彈性過濾、排序、分頁語法 |
| **即時可視化** | 整合儀表板涵蓋電力曲線、工廠環境趨勢、設備狀態時間軸 |
| **告警鏈路** | 自訂閾值 / 持續時間規則 → Telegram 即時通知，附事件時間、設備、超限值 |
| **工廠環境整合** | 工廠 PLC 與環境感測器與電表共用同一條管線，單一資料平台統一管理 |
| **裝置自動登錄 + AI 分類** | 新裝置 MQTT 上線即自動偵測，可切換 LLM（mock / 雲端 / 本地）分類裝置型別與訊號定義；高信心自動納管、低信心進人工確認佇列（PRD-0003） |
| **雙層 AI 安全防護** | 分類路徑經兩層 AI 守衛（L1 分類 + L2 guardrail）＋輸入淨化＋輸出驗證＋預算硬上限＋三層 API 分權；所有 AI 決策寫入 append-only 稽核紀錄 |
| **AI 控制面（MCP）** | 原生 MCP 介面，讓 Claude / 其他 AI Agent 用自然語言讀取 PLC 暫存器（模擬器控制改由 BFF OPS 稽核入口），並以 AI 通道工具讀取 / 重跑裝置分類 |
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
   - **目前狀態**：本方向已於 PRD-0003（Phase 1.1–1.4）實作為 `device-service`，含可切換 LLM 分類、MQTT 自動發現、雙層 AI 守衛、L1/L2 各自的預算硬上限（FR-329/FR-340）、append-only 稽核與 AI 通道 MCP，已合併於 `dev`。預設使用 mock LLM（零成本、不外連）；真實 provider 的雙層守衛已通過實機 E2E、L2 成本亦已納入獨立預算計量並 fail-closed。production 上線前的後續項：跨-provider（L1/L2 不同廠商）defense-in-depth、Grafana 監控 panel、預算告警投遞。

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

### 裝置登錄與 AI 輔助分類（PRD-0003）

新裝置經 MQTT 上線即被自動偵測，進入裝置登錄服務的分類管線；結果依信心分流（高信心自動納管、低信心進人工確認佇列）。分類路徑全程受多層防護：

```text
┌─────────────┐  MQTT 訂閱  ┌──────────────────────────────────────────────────────┐
│ 新裝置上線  │ ──────────▶ │ 裝置登錄服務 device-service (:8002)                    │
└─────────────┘             │  淨化 → 預算閘 → L2 守衛(pre) → L1 分類(可切換 provider) │
                            │  → L2 守衛(post) → 輸出驗證 → 信心分流                  │
┌─────────────┐  X-API-Key  │  雙 DB 連線池最小權限 · DB 凍結觸發器 · append-only 稽核 │
│ 運維 / AI   │ ──────────▶ └──────────────────────────────────────────────────────┘
└─────────────┘                         │ AI 通道 MCP endpoint（本機）
                                         ▼  http://127.0.0.1:8766/mcp（讀取 / 重跑分類工具）
```

裝置中繼資料集中於單一 source of truth；運維可經 REST 確認 / 修正 / 退役裝置，或提交修正回饋（correction）讓後續分類參考。設計取捨見 `doc/prd/PRD-0003-Device-Registry-Auto-Discovery.md` 與 `doc/adr/`（ADR-009～018）。

## 服務組成

| 服務 | 對外 Port | 用途 |
|------|----------|------|
| 電表模擬器 | 127.0.0.1:5020（Modbus 唯讀） | POC 電表；設定與故障注入經 BFF :8003 |
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
| AI 控制面 (kc-mcp-server) | 8765 (本機) | MCP client 唯讀查詢模擬器暫存器；控制經 BFF OPS |
| 裝置登錄服務 (device-service) | 8002 (REST) | 裝置 CRUD / 自動分類 / 人機確認 / 修正回饋 / 稽核（PRD-0003） |
| 裝置登錄 MCP (device-service-mcp) | 127.0.0.1:8766 (本機) | device-service 的 MCP endpoint，AI 通道讀取 / 重跑分類工具 |
| BFF (bff) | 127.0.0.1:8003 (本機) | 瀏覽器↔後端唯一通道：session/CSRF/role→key 注入（PRD-0005 §9）|
| 自建前端 (frontend) | 5173 (dev) | React/Vite 產品 UI；經同源 BFF /api 取數，零瀏覽器金鑰；本地登入頁 + live BFF 接線（session cookie credentials:include、同源 CSRF、route guard）；字體自託管 @fontsource（Inter / Space Grotesk / Noto Sans TC / JetBrains Mono，後台可切換、繁中以 Noto Sans TC 補字，離線無 CDN）（PRD-0005 §6.4/§9）|
| 前端正式服務 (frontend-prod) | 127.0.0.1:8080 (prod profile) | nginx 服務 SPA 靜態 build；注入 §9.5 安全標頭（CSP/HSTS/X-Frame/Referrer/nosniff）+ 同源代理 /api→BFF（PRD-0005 §9.5）|

## 快速入口

| 入口 | URL / 指令 | 用途 |
|------|------------|------|
| 監控儀表板 | <http://localhost:3000/d/ems-overview> | EMS Overview，含電力與工廠視覺化 |
| 電力資料查詢 API | <http://localhost:3001/electricity_measurements?order=time.desc&limit=10> | 查詢歷史電力資料 |
| 工廠資料查詢 API | <http://localhost:3001/factory_measurements?order=time.desc&limit=10> | 查詢溫度、濕度、壓力、馬達、Pump、Valve |
| 模擬器控制及狀態 | [統一控制手冊](doc/operations/simulator-control.md) | OPS 登入後查詢四台模擬器 |
| 裝置登錄服務健康檢查 | `curl http://localhost:8002/healthz` | device-service 雙 DB 連線池狀態 |
| kc MCP endpoint | `http://localhost:8765/mcp` | 工廠 PLC MCP client 連線（非瀏覽器頁面） |
| 裝置登錄 MCP endpoint | `http://127.0.0.1:8766/mcp`（需 X-API-Key） | device-service AI 通道工具（非瀏覽器頁面） |

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
python3 scripts/simulator_control.py --username demo state sim-001
# 以既有 OPS 帳號登入；預期 available=true
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
├── AGENTS.md                # Agent 接手與必讀入口
├── project_rules.md         # 專案規定；重要變更後需同步文件
├── docker-compose.yml       # 一條龍啟動所有服務
├── .env.example             # 環境變數範本
├── api/
│   └── openapi.yml          # 對外 API schema
├── config/                  # 設備與服務設定
├── doc/                     # 規範、PRD、ADR、架構、運維文件
│   ├── README.md            # 依任務找文件、程式及驗證紀錄的總地圖
│   ├── PRD-架構設計-Guideline.md
│   ├── prd/                 # 正式 PRD（含實作狀態索引）
│   ├── architecture/        # C4 Context / Container / Data Flow
│   ├── adr/                 # Architecture Decision Records
│   ├── governance/          # NFR、風險登記簿、威脅建模
│   ├── operations/          # 操作手冊、容器速查表、對外公開指南
│   └── archive/             # 已被 PRD 取代的歷史規劃
├── infra/                   # 資料庫初始化、broker、儀表板 provisioning
└── services/                # 自有服務模組（電表 / 採集 / 寫入 / 工廠 / MCP / 裝置登錄 device-service）
```

## 文件索引

> **新人 / 接手工程師閱讀順序**：`project_rules.md` → `doc/PRD-架構設計-Guideline.md` → `doc/prd/README.md`（定位並讀相關 PRD 全文）→ `doc/architecture/` → `doc/adr/` → 才開始動手。詳見 `project_rules.md` §14。

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
| `api/openapi.yml` | 對外 API schema（查詢 API + 模擬器 + 儀表板管理 + 裝置登錄 device-service REST API） |


### 本機設計預覽量測驗證（2026-09-23）

獨立預覽 http://127.0.0.1:4178/#Monitor 已使用既有 BFF session 與量測 API，5 秒更新。其餘六頁為示意資料；目前來源為專案模擬器。設定、啟動與驗證紀錄見 [預覽說明](output/ems-design-preview-20260923/README.md). 未新增或修改後端 API 合約。

### 監控圖表與歷史紀錄（本機已部署）
PRD-0018 / ADR-027：新增有界歷史查詢、ECharts 趨勢、布林状态與原始紀錄分頁。已經使用者批准，套用 migration 017 並重啟 BFF；三類設備與歷史查詢已通過真實資料驗證。操作細節見 [預覽說明](output/ems-design-preview-20260923/README.md)。
### 警報中心 Telegram 示範通知
警報中心新增「觸發警報」：以既有 OPS 登入後，透過 BFF 發送固定 DEMO／無需處置訊息到已設定的 Telegram。既有 `.env` 的 TELEGRAM_BOT_TOKEN、TELEGRAM_CHAT_ID 由 Compose 注入 BFF；不寫入前端。30 秒冷卻，最近成功十筆僅存記憶體。見 [PRD-0019](doc/prd/PRD-0019-telegram-demo-alarm.md)、[ADR-028](doc/adr/ADR-028-telegram-demo-alarm.md)。

### 展位 QR Code 綁定訪客（PRD-0024）
警報中心顯示 QR Code：訪客掃碼並在 Telegram 按「開始」即成為唯一示範收件者（後掃者優先、10 分鐘到期、`/stop` 解除），按「觸發警報」只送該訪客並告知「今天第 N 位」（台北日不重複計數、午夜歸零）；無綁定時維持固定對象原訊息。BFF 以 getUpdates 長輪詢（無 webhook／入站埠），狀態存 `demo_alarm_state` volume，`bff.toml` `demo_bind_enabled` 可關閉。見 [PRD-0024](doc/prd/PRD-0024-booth-telegram-qr-binding.md)、[ADR-036](doc/adr/ADR-036-telegram-visitor-binding-long-polling.md)、[操作手冊](doc/operations/操作手冊.md)。

## Delta 三相模擬與 4G 邊緣採集
已新增 [Delta simulator / parser / TCP–RTU edge](services/delta/README.md)（V1.35）；opt-in `delta-demo` profile。
本機 [Monitor](http://127.0.0.1:4178/#Monitor) 選 `delta-sim-001`，欄位為 L1 V/A、三相總 kW、累計 kWh。
Pi + SIM7600G-H 的 TLS、systemd 與雙介面範本見 [操作交接](doc/operations/delta-edge.md)；實體 RTU/4G 與接收端身份綁定尚待現場驗收。

### Delta 現場採購與容量規格（Draft，2026-09-29）
[SQLite 深度調研](doc/research/2026-09-29-sqlite-edge-capacity.md)與[PRD-0021](doc/prd/PRD-0021-multi-device-edge-reliability.md)提出M70A-262／RPI-M30A、每gateway 8台／10秒／斷網7天的待驗收目標。現有軟體仍為單設備與broker ACK；新多設備排程、中央committed ACK及硬體验收尚未實作。研究附隔離容量結果，不是Pi benchmark。

對帳規格補充（Draft）：PRD-0021 §15.1加入每5分鐘ID／序號／hash對帳、斷線後差額補傳與缺測分類。目前尚未實作；已採但未入庫可補傳，未採到的瞬時值不能憑空補回。

採樣間隔需求更新（Draft）：[PRD-0021 §15.2](doc/prd/PRD-0021-multi-device-edge-reliability.md)定義每設備1／5／10／15／30秒、預設10秒與混合頻率。EMS選單與gateway設定回報尚未實作；8台／10秒／7天是基準，較快組合須另核算bus、pending/audit容量與補傳。

### Delta RTU 從站模擬（2026-09-29）
PC 可執行 `python -m delta_device simulator --transport rtu --serial-port COM5 --baudrate 19200 --unit-id 1`，經兩顆隔離 USB–RS485 與 Pi 主站對接。從 `services/delta` 目錄執行；TCP 仍為預設。安裝、接線、Pi單次解析及4G分段驗收見 [Delta操作說明](services/delta/README.md#rtu-從站電腦模擬-delta樹莓派採集)。實體線路、Windows COM 與4G待到貨驗證。


### Delta demo 每秒採樣（2026-09-29）
`delta-sim-001` 已支援每秒採樣與有界電壓/電流誤差，真實 field 範本仍為 10 秒。畫面使用實際入庫資料，沒有前端補值。部署、回復、queue 容量及驗收見 [Delta 操作紀錄](doc/operations/delta-edge.md) 與 [ADR-034](doc/adr/ADR-034-delta-one-second-noise.md)。

## Simulator 統一控制與操作紀錄（PRD-0022）
四台 sim-001 / plc-001 / sensor-001 / delta-sim-001 統一走 BFF OPS API，操作先持久化再執行。
本機目前 OPS 帳號是 `demo`；`python3 scripts/simulator_control.py --username demo list` 查狀態，`history` 查設定命令紀錄。
首次使用請依 [快速開始與 sim 簡寫設定](doc/operations/simulator-control.md#從目前這台電腦開始)；`sim` 是需自行建立的 Bash function，新視窗要先保存至 `~/.bashrc`。
指令、參數、逾時對帳、SQLite volume 與備份見 [操作手冊](doc/operations/simulator-control.md)。
舊 :8001 POST 與 simulator Modbus/MCP raw write 已停用；真機與 Pi edge 維持唯讀。

2026-09-29 CLI 登入修正：本機 simulator 指令預設用 `http://127.0.0.1:8003`，已支援同origin的 Secure session cookie；保留後端安全設定。若曾出現登入200後查詢401，直接重跑目前 `scripts/simulator_control.py`。操作入口與故障排除見 [控制手冊](doc/operations/simulator-control.md)。

### DB 帳號管理（2026-09-30）

本機帳號已改存 PostgreSQL `bff_auth.accounts`，異動記錄於 `bff_auth.account_audit`；`.env` 只保留服務 DSN。`demo` 保留原密碼與 OPS 角色。
```bash
cd ~/synaiq/EMS
docker compose run --rm account-admin list
docker compose run --rm account-admin create dalelin --role ops --reason "新增維運人員"
```
新增／停用／改密碼／權限與備份見 [帳號管理操作手冊](doc/operations/account-management.md)。帳號異動立即在下一次請求撤銷舊 session；無網頁帳號管理入口。


### 2026-11-12 Windows 實體 RS485 bench（無 Pi）

兩台 USB–RS485 接同一台 Windows PC，COM3 從站／COM4 採集；修正 Windows 短封包後 110/110 成功。獨立 `delta-rtu-sim-001` 的 SQLite 暫存／補送、DB 與 EMS records API 15/15 通過，完整回歸 78 passed、coverage 95.20%。Pi、4G、Delta 真機與長期可靠性仍待驗證；舊紀錄的「Windows COM／實體 RS485 待驗證」僅由本次 bench 範圍更新。重現、證據及限制見 [驗證紀錄](output/delta-rtu-bench-20261112/README.md)。


### 2026-11-12 無 Pi 驗證計畫與執行入口

[單設備 Windows 台架計畫與驗收基準](doc/operations/delta-no-pi-validation-plan.md)：定義採樣槽帳本、資料正確性、USB／封包／上傳故障、程序恢復及 DB 對帳關卡。門檻為台架提議值，非已達成 SLA；中央 committed ACK／去重沿 PRD-0021 待實作。本次未新增容器、API 或 runtime 設定。


### 無 Pi 逐關執行紀錄（2026-11-12）

實際關卡狀態、帳本工具重現方式及限制見 [逐關驗證紀錄](output/delta-no-pi-validation-20261112/README.md)。測試只作用於獨立 delta-rtu-sim-001 與各 run 自有 SQLite，不新增／重啟共用容器；中央 DB committed ACK 仍未實作。

### 2026-11-12 Delta RTU串口恢復修正

[ADR-040](doc/adr/ADR-040-delta-rtu-listener-recovery.md)補上模擬器成功監聽後的同埠重開與背景task回收。完整Delta回歸127 passed、line coverage95.71%，修正後正常實體採集3/3及DB/API對帳通過；USB拔插恢復仍待重驗，舊FAIL保留。詳[逐關紀錄](output/delta-no-pi-validation-20261112/README.md)。

2026-11-12 12:16更新（ADR-040）：COM3修正後實體拔插usb-com3-04-fixed通過，離線33.328秒，恢復上界9.672秒，原程序持續運行，52筆DB/API逐筆相符、pending0；COM4仍待獨立測試，關卡4只部分完成。實際證據以逐關紀錄為準。

2026-11-12 12:22：COM4測試觀察3.047秒恢復、52/52筆DB/API一致，但COM3亦曾離線，未滿足單端隔離條件，原工具FAIL保留、COM4判讀INCONCLUSIVE待重測。COM3已通過，整個關卡4未完成。詳逐關紀錄。

2026-11-12 12:30：COM4-02單端恢復上界2.516秒、55/55 DB/API對帳、pending0；離線27.235秒未達28秒預設下限，原FAIL不改，操作時長判讀INCONCLUSIVE待受控計時補驗。COM3維持已通過，整關未完成。

2026-11-12使用者取消USB秒數補驗：已停usb-com4-03-timed，保留不完整證據。COM4功能恢復2.516秒及55/55對帳成立，離線27.235秒的工具原FAIL以操作時長偏差保留；不再要求人工秒數補驗，USB項目依現有證據結束。

2026-11-12第5關實體RS485故障測試完成：前五類各20/20通過，遲到舊回覆20/20被下一個read誤收，第5關FAIL，資料新鮮度策略待處理。沒有向EMS發布故障值。USB秒數補驗依使用者取消。詳[逐關紀錄](output/delta-no-pi-validation-20261112/README.md)。

## RTU不確定交易更新（2026-11-12，ADR-041）

完整sample替身已重現跨串口close/open混入舊AC。正式Poller現於不確定交易後丟棄整筆並鎖定；未知上界不再採新值，SQLite既有可信資料仍可補送。有核定的modbus.response_lifetime_seconds與response_lifetime_source才可等待／重建client與framer／清buffer後重採；field RTU也須啟動隔離。field範本null刻意拒絕啟動，須由工程人員補足機型／韌體／USB驅動的核定依據，不可照抄台架1秒。

這是本機原始碼變更，未重建共用EMS容器、未改MQTT／DB／API契約；不代表任意延遲或惡意重播皆可辨識。真機M70A-262／RPI-M30A上界未核定，風險保持Open。依據與最新實測見ADR-041及output/delta-no-pi-validation-20261112/README.md；歷史FAIL不覆寫。

2026-11-12本輪最終：164項回歸通過、production line coverage96.06%；完整sample實體有界保護40/40、5分鐘上傳中斷80筆DB/API逐筆一致、10次採集child強殺30筆恢復且DB/API一致、私有SQLite容量／損壞副本故障注入通過。中央DB committed ACK仍缺、第9關BLOCKED，1h／24h與真機未驗。修正未部署共用容器。[紀錄](output/delta-no-pi-validation-20261112/README.md)。

## 2026-11-12 續驗：DB確認反例與長測

[最新逐關紀錄](output/delta-no-pi-validation-20261112/README.md)：第9關以私有真MQTT／production傳送端／受控SQLite重現3案，v1系統驗收FAIL；未操作共享DB，v2中央commit receipt／去重待實作。本機Monitor攔截API的5案新鮮度及圖表／卡片／表格值通過，只屬UI契約。1秒1小時於13:49啟動，通過才進5秒24小時，當前以紀錄內活動status為準；未先報長測通過。保持PC開機及兩顆USB，不再人工拔插。回歸183 passed、production coverage96.06%；無API／schema變更、未部署共享runtime。

## 2026-11-12 時鐘／TLS補驗完成

[補驗紀錄](output/delta-no-pi-validation-20261112/field-security-02/README.md)：正式edge加真Modbus TCP／SQLite／私有TLS broker，時鐘2案11階段、TLS10案，共12/12通過；7個憑證／認證拒絕案保留pending，同Publisher1.0274秒重連。只注入測試UTC／節拍及sender permit，不改主機時鐘或COM。首輪9/12失敗保留，工具修正後另驗；完整回歸191 passed／12 skipped，12項隔離案已另實跑，production coverage96.06%。私有容器已清理，無API／schema／production改動、未部署共享runtime。1秒／1小時已PASS、5秒／24小時仍運行；中央receipt／去重、多設備仍待實作，非Pi／4G／真機准入。

## 採集測試交接（2026-11-12）

[目前進度、未完成清單及接續順序](doc/operations/edge-temperature-handoff-20261112.md)：下一個整合目標是溫度貼片經 Pi 解析／暫存後傳至 EMS，日照移出本輪；ADTEK／Pi 全鏈路尚未實作驗收。既有 Windows Delta 台架的 1h PASS、24h 活動狀態及中央 receipt／去重缺口分開追蹤，接手前先看動態 status，不占用 COM3／COM4。

### 2026-11-12 無 Pi 弱網與積壓補測

[完整證據](output/no-pi-backlog-20261112/README.md)：10,120 筆私有積壓／同步採樣、155 筆弱網、1,000 筆線上備份前綴、110 筆真 EMS DB／API 對帳及 stale→live 介面檢查通過；Linux 自有臨時服務重啟／停止亦通過。新增測試工具，203 項回歸通過，production coverage 96.06%；未改 production／共享容器或活動 24h 長測來源。中央 receipt／去重仍待實作。

### 2026-11-12 實際接收端與 IP 丟包補測

[證據](output/no-pi-ingest-20261112/README.md)：私有相同 Telegraf／TimescaleDB 接收副本重現重送重複入庫、接收停機時 PUBACK 後缺筆，v1 可靠送達仍 FAIL；私有 DB 暫停 10 秒後 10／10 恢復。另以核心 netem 真正丟 17 個 IP 封包，230／230 完整；211 項回歸、production coverage 96.06%。原長測前 1,740 槽 DB／API 相符，24h 仍 RUNNING；未改 production 或活動來源，自有容器／qdisc 已清理。中央 receipt／去重及 Pi／4G／溫度全鏈路仍未完成。

## 中央提交確認與重送去重修復（2026-11-12）

[實作／部署／離線轉換入口](services/edge-receiver/README.md)、[ADR-043](doc/adr/ADR-043-opt-in-committed-telemetry.md)、[驗證紀錄](output/committed-delivery-fix-20261112/README.md)。新增 opt-in v2：本地保留到 DB committed ACK；穩定 ID/hash、原子 receipt＋投影、並行去重、缺列修復及權威 mTLS／ACL。259 項通過、12 項專用 clock/TLS 跳過、combined coverage 90.81%；真 MQTT停機／ACK遺失／TCP採集SIGKILL恢復、DB失敗及 mTLS負向驗證通過。舊 v1 反例保持、共享部署／原 24h 未切換；Pi、完整多設備／manifest對帳／20/s容量仍未驗收。

### 2026-11-13 長測中斷稽核

[實際結果](output/soak-interruption-audit-20261113/README.md)：Windows更新於11/12 22:29:14發起重開機，原24h測試停止在約7h39m／5,512筆，DB／API本日逐筆一致但**未完成24h，不能算通過**；原RUNNING已過時。1h本日重查3,600／3,600保持PASS；槽號15ms邊界異常另保留，未啟動重跑。v2昨日259項獨立證據hash相符，未切共享部署。

槽號誤標已於11/13修正：[66項定點補測](output/slot-boundary-fix-20261113/README.md)。工具改按排程原定deadline標槽，保留提早／延遲；不改production scheduler或原始帳本。原五筆只做時間回放，未重跑長測，24h中斷狀態不變。

### 2026-11-13 其他無Pi短測與防回歸

[8個新故障＋35個槽號回歸](output/no-pi-v2-faults-20261113/README.md)共43項通過，另16個控制器反例通過。涵蓋真DB逾時／回滾、終止自有backend、雙接收端去重、衝突quarantine、SQLite滿與不受信client憑證。補測入口核對完整35案identity及DB真故障證據，不能以漏跑／替代／重複／skip／單純ACK逾時假過關。未改production／共享部署、未接COM或重跑長測。

### 2026-11-13 容量滿保留最新量測

使用者核定最新優先；[ADR-045](doc/adr/ADR-045-newest-first-edge-retention.md)／[驗證](output/newest-first-retention-20261113/README.md)：queue／audit／byte滿按capture_seq淘汰最舊量測（含未送／quarantine），原子存入新樣本並保留有界淘汰摘要；不假記committed。schema3本地升版、wire仍2，舊版拒開。336項短回歸通過／12專用case未重跑、coverage≥80%；23容量案、真MQTT舊ACK競態、離線12限3僅補最後3筆。寫新失敗整筆回滾；共享v1、COM與原長測未操作。容量超額後不保證舊資料完整補傳，中央對帳／缺口UI、Pi／實體SD仍待驗。

### 2026-11-13 無Pi恢復與v2憑證續測

[新9案＋35槽號共44通過](output/no-pi-resilience-20261113/README.md)，工具32案通過：真SIGKILL三交易邊界、SQLite BUSY／READONLY、循環寫入中的線上backup、v2錯CA／錯hostname／過期server憑證拒絕及原ID恢復中央一次。修正崩潰驗收把constructor寫入當dirty-spill的假PASS風險，marker改原子發布；本輪production未改、未切共享服務／占COM／重跑長測。不是Pi／SD／實體掉電或PITR驗收。

### 2026-11-13 三項無Pi續測與空庫誤重建修復

[broker重啟／SQLite損壞／client憑證輪替撤權](output/no-pi-lifecycle-20261113/README.md)：42項定點通過、零跳過；相鄰393通過／12專用case跳過、coverage91.02%。同edge程序在broker離線持續TCP採3筆、恢復各入庫一次；4損壞檔拒開且hash不變；同CN新cert可用，CRL撤oldserial＋重啟自有TLSbroker斷活動舊session，old重連拒、新cert可恢復原ID。修ReliableOutbox既有空檔／空schema不可重建reset，並保留精確READONLY_ROLLBACK的原生journal恢復；測試host檔案I/O防symlink補齊。未切共享v1、占COM或重跑長測；正式PKI／Pi／SD／4G／中央PITR仍另驗。

### 2026-11-13 剩餘三項無Pi短測與公平送達修復

[中央備份還原／接收超量恢復／千筆積壓新資料延遲](output/no-pi-restore-load-20261113/README.md)：38定點通過／零跳過，419相鄰通過／12專用case跳過、coverage91.04%。真pg_dump還原新庫，原pending同ID補回／舊ACK拒，backup後已ACK且local刪payload的1筆明示dump＋local不可補，不稱零遺失。200封同樣本重送達queue64/drop135/rate拒65，恢復原／新各1列。[ADR-048](doc/adr/ADR-048-v2-live-backlog-fairness.md)修FIFO為最新／最舊成功1:1交替；1000舊＋3新用原1秒sender節奏，新筆1.044／2.091／2.098秒commit、最舊亦前進，1003總帳保留。是私有短測，非WAL PITR、現場SLA或20/s驗收；共享／COM／長測未動。

2026-11-13 [同步WAL與實體PITR短測](output/no-pi-wal-pitr-20261113/README.md)／[ADR-049](doc/adr/ADR-049-synchronous-wal-ack-and-pitr.md)：field ACK強制獨立WAL刷盤覆蓋固定LSN；basebackup後已ACK且local已刪的B，在原主庫停用後由WAL救回，缺WAL拒絕達標。正式[啟用與還原手冊](services/edge-receiver/WAL-PITR.md)與systemd/TLS範本已備，尚未部署共享；未用COM／重跑長測。

2026-11-13 新無Pi私有短測：[受限field帳號、轉換SIGKILL、inflight clientID碰撞](output/no-pi-cutover-20261113/README.md)，5新案＋35槽號共40通過15秒，131工具／轉換單測通過。純測試與驗收工具補強，產品／共享部署／COM／長測不變。

2026-11-13 [無Pi儲存一致性與正常停機修復](output/no-pi-integrity-20261113/README.md)：66定點通過、500相鄰／12既有skip，coverage91.36%；修邏輯損壞漏檢、live序號回退重用、audit缺失ACK誤刪及讀取快照／摘要溢位。另真MQTT異常批次與SIGTERM重啟11筆完整逐ID/hash／投影核對。無共享部署／COM／長測重跑。

## 2026-11-13 DB／WAL安全與還原短測完成

DB／WAL TLS、128MiB archive ENOSPC恢復、損壞backup／WAL及有效外cluster拒絕已私有短測；55通過62.52秒，568短回歸／12專用skip／coverage90.99%，原已ACK資料PITR36通過。修field db_tls強制驗證、021版本化TLS＋固定角色WAL predicate、外置expected_system_id及tar資源預檢。無COM／共享部署／長測重跑；正式異失效域與Pi仍待驗。 [證據與操作入口](output/no-pi-wal-security-20261113/README.md)。

## 2026-11-13 高必要性強化已收尾

本輪限定三項高必要性補強已完成：中央receipt資料16MiB空間真ENOSPC→retryable／原ID一次恢復；slot真lost→新slot先reserve再basebackup，跨3段／checkpoint後真PITR驗gap marker；同cluster兩分支二次PITR固定核定timeline／target。38定點通過18.00秒；616相鄰短回歸／12既有專用skip／coverage91.73%，48新單測通過（套件重疊不加總）。正式部署／Pi仍待驗，無COM／共享／長測重跑。 [完成項目與證據](output/no-pi-critical-closure-20261113/README.md)。後續只追已知未修問題與硬體驗收，不自動擴充測試範圍。
