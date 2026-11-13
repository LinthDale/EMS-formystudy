# EMS 自研平台與 Edge／Web／App 產品 PRD 架構草案

> **English summary:** Implementation-oriented architecture for a self-developed BESS EMS, separating local safety from supervisory control and evolving the current Dev/Demo stack into a site-resilient, multi-site product.
>
> 狀態：Working Draft（供總計畫 PRD 整併與跨 Agent 審查）  
> 盤點日期：2026-09-03  
> 範圍：EMS 站端 Edge、雲端、Web/PWA、App 定位、設備通訊、資料、告警、監督式控制、資安、部署與驗證  
> 不修改：BMS/PCS 本地保護演算法、採購型號、正式 proposal/PDF/PPT

---

## 0. 結論先行

目前 EMS repo 已具備可延續的工程基礎，但仍是 **Dev/Demo 階段的固定資料管線與產品 UI P1**，不是可直接投入 BESS 現場的 EMS 控制產品。產品化主線如下：

1. **站端自主性**：失去 Cloud/Internet 時，資料採集、告警、已核准排程與安全降載仍須在 Edge 執行。
2. **正式設備介面層**：BMS、PCS、電表、HVAC、消防、STS 均需 versioned device profile、protocol adapter、通訊健康與 HIL 驗證。
3. **監督式控制服務**：Web/Cloud 不得直接寫 Modbus/CAN；命令必須通過權限、時效、互鎖、BMS/PCS 夾箝、read-back 與 append-only audit。
4. **資料品質與時間語意**：每筆資料須分辨設備時間、採集時間、入庫時間與 quality，不能只採 broker/ingest 主機時間。
5. **多站租戶模型**：現有 device_id 全域主鍵與無 tenant/site 欄位無法安全擴展。
6. **產品面與維運面分離**：React Web/PWA 為客戶/操作員介面；Grafana 為 SRE/工程觀測。
7. **通訊失效分級**：BMS↔PCS、EMS↔PCS、Cloud↔Edge 三條鏈路不可用同一個「一律 FAULT」規則。
8. **MVP 先讀後控**：第一個現場 MVP 僅做真機採集、品質、事件與 Web；P/Q、模式偏好與 start/stop 在 HIL 後才進 Pilot。
9. **PWA 優先**：原生 App 僅在 BLE/NFC、背景推播、MDM 或離線工單需求被驗證後立案。
10. **合理時程為 12 個月、7–8 FTE**：0–16 週 MVP，17–32 週 Pilot，33–52 週 Production Gate。2–3 人應估 18–24 個月。

---

## 1. 現況盤點與證據

### 1.1 已存在且可沿用

| 能力 | 現況證據 | 判定 |
|---|---|---|
| Modbus→MQTT→TimescaleDB | services/gateway/telegraf.conf、services/ingest/telegraf.conf | 可作 SIL/POC 與簡單電表 adapter 範本 |
| MQTT broker | infra/mosquitto/mosquitto.conf | Mosquitto 可沿用；現設定僅 dev |
| 時序資料庫 | infra/timescaledb/init.sql | TimescaleDB 可保留；需版本鎖定、壓縮、租戶化與 HA |
| Device Registry/Discovery | services/device-service/device_service | CRUD、訊號、MQTT 發現、AI 輔助分類與 audit 可延續 |
| API 契約治理 | api/openapi.yml v1.3.0、tests/contract、CI | device-service contract gate 可延伸到產品 API/AsyncAPI |
| Web BFF 安全基線 | services/bff/bff | 同源 BFF、CSRF、HttpOnly session、role→channel key、OIDC code 可沿用 |
| Web UI 基礎 | frontend | React/Vite、設計 token、登入、設備/審核頁、live BFF wiring 可沿用 |
| 告警與 ops dashboard | infra/grafana/provisioning | Grafana/Telegram 可作內部 ops 基線 |
| 測試基礎 | tests/unit、tests/integration、前端/BFF tests | 單元/契約框架可沿用；現場協定/HIL gate 尚缺 |
| BESS 模式邊界草案 | doc/architecture/bess-operating-mode-state-machine.md | 可作起點；失聯語意需修正 |

### 1.2 不能宣稱完成

| 項目 | 實際狀況 | 產品化處置 |
|---|---|---|
| 真實 BESS adapter | 現在只接 simulator/KC simulator、map 固定 | 新建 versioned profile + adapter SDK + HIL |
| 通用量測窄表 | PRD-0006/ADR-022 仍 Draft/Proposed；無 ingest-generic，migration 最大 015 | 審查容量/租戶後實作 |
| 正式 MQTT 安全 | anonymous、無 TLS、無 persistence | mTLS、ACL、persistent session、disk spool |
| 最小 DB 權限 | Telegraf ingest 用 postgres、sslmode=disable | INSERT-only role + TLS/本機 socket |
| 網路分區 | Compose 單一平面，多個 ports 映射 host | OT/Edge/IT/Management 分區與 firewall |
| 高可用/DR | TimescaleDB、Mosquitto 單點 | Pilot 備份/restore，Production HA |
| 產品控制 API | 只有 simulator fault、device CRUD 與 legacy MCP 直寫 | 新建 control-service |
| Web 完整產品 | 僅設備清單/詳情/candidate 審核 | 新增站務、告警、趨勢、排程、控制、audit |
| BFF create/update | ADR-026 Accepted，但 routes 尚無 POST root/PATCH item | 補路由、contract 與 test |
| OIDC UX | BFF 有 OIDC+PKCE；登入頁仍只顯示 local login | Pilot 補 IdP login/logout/MFA |
| 多租戶 | DB/API 無 organization/site scope | 先做資料模型/RLS/authz |
| App | 無 | MVP/Pilot 以 PWA |
| Integration/E2E CI | CI 明載尚未執行 | Pilot 必須加入 compose/HIL nightly |

### 1.3 文件/實作漂移

- PRD index 稱 PRD-0003 Implemented，但主檔仍寫 Approved/TBD。
- frontend 部分註解仍稱 P1 mock，App.tsx 已以 live BFF 為正式路徑。
- ADR-024/025 仍 Proposed，但 OIDC 與 measurement facade 已有實作。
- ADR-026 已 Accepted，但對應 BFF create/update 尚未落地。計畫追蹤需拆 Decision / Implemented / Verified / Released 四態。
- c4-context/c4-container 仍以工廠 demo 為中心，尚未描繪 BESS 與 Edge/Cloud。

---

## 2. 問題、目標與非目標

### 2.1 Problem Statement

100 kWh 級 BESS 需要一套能在斷網時持續運作、整合多廠牌設備、保留完整稽核與資料品質、並由 Web 管理多站的 EMS。現有系統已證明資料管線與 Web 基礎可行，但缺現場控制所需的設備契約、站端權威、互鎖、離線、資安分區及 HIL。

### 2.2 Goals

| ID | 目標 | 可驗收指標 |
|---|---|---|
| G-EMS-01 | 真實設備納管 | BMS、PCS、電表至少各一型號通過 profile contract + HIL |
| G-EMS-02 | 站端離線運作 | WAN 中斷 72h，採集/告警/已核准排程不中斷，復線可補傳 |
| G-EMS-03 | 安全監督式控制 | 命令均具 command_id、expiry、互鎖、夾箝、read-back、audit |
| G-EMS-04 | 可追溯資料 | telemetry 具 source/acquired/ingested time、quality、profile/config version |
| G-EMS-05 | 產品級 Web | 站點、資產、告警、趨勢、排程、命令與 audit 工作流 |
| G-EMS-06 | 多站租戶隔離 | organization/site scope 由 DB、API、broker ACL 共同強制 |
| G-EMS-07 | 可部署可回滾 | Edge signed release 可分批升級、health gate、失敗回前版 |
| G-EMS-08 | 可營運 | freshness、clock、spool、adapter、command success 均可觀測 |

### 2.3 Non-Goals

- EMS 不實作 BMS 電芯保護、接觸器硬保護、PCS 電流/電壓內環、PLL、grid-forming、黑啟動序列或小於 20 ms STS 切換。
- MVP 不讓 AI 自主下達功率、模式、接觸器或保護復歸命令。
- MVP 不支援所有廠牌；每一型號經 profile + HIL 才可列 Supported。
- 不以 Grafana 取代產品 Web，也不把 PostgREST/Modbus/MQTT 直接曝給瀏覽器。
- MVP 不做原生 App；先驗證 responsive PWA。
- 不透過通用 EMS OTA 更新第三方 BMS/PCS firmware。

### 2.4 約束與假設

- 安全門檻與最快反應保持在 BMS/PCS/保護電驛本地；EMS 是 supervisory controller。
- 第一個 Pilot 為單站、單簇/單 PCS；多 PCS 並聯另開控制 PRD。
- BMS/PCS register/CAN map、write、timeout/watchdog 必須以實機文件確認。
- 遠端寫入可由站端關閉，local/manual 權限高於 Cloud。
- 時程以前提 7–8 FTE；硬體交期、電網規約與認證由總計畫管理。

---

## 3. 權責邊界與控制優先權

### 3.1 Authority Matrix

| 層級（高→低） | 權威 | 可執行事項 | EMS 可否覆寫 |
|---|---|---|---|
| L0 人身/硬體保護 | EPO、消防聯鎖、熔斷器、保護電驛 | 立即切斷/跳脫 | 不可 |
| L1 電池/PCS 本地保護 | BMS、PCS local controller | OV/UV/OT/OC/絕緣、允許電流、V/I 內環 | 不可 |
| L2 站端互鎖/仲裁 | Edge site-controller | 模式資格、P/Q 夾箝、需量、排程、失聯策略 | 僅改 policy |
| L3 Cloud 調度 | Fleet/schedule service | schedule/desired intent | Edge 可拒絕/過期/夾箝 |
| L4 Web/App | 使用者 | 提交 intent、ACK、申請控制 | 不直寫 field bus |
| L5 AI/Optimizer | 建議服務 | 預測/排程建議/診斷 | 預設只建議 |

### 3.2 命令夾箝

~~~text
P_final = clamp(P_requested,
                BMS_charge_discharge_limit,
                PCS_capability,
                site_contract_limit,
                SOC_reserve_policy,
                thermal_derate,
                ramp_rate,
                operator_local_override)
~~~

輸入缺失、過期或 quality 不足時不可猜值。Edge 依 profile 拒絕、保持受限穩態或 ramp-to-zero；策略必須逐型號 HIL。

### 3.3 三類失聯

| 失聯 | 權威反應 | 不應做 |
|---|---|---|
| BMS↔PCS/BMS heartbeat | PCS/BMS 本地降載/停機/斷開 | 等 Cloud 決定 |
| Edge↔PCS | PCS watchdog；Edge hold 或 ramp-to-zero 並告警 | 一律宣告 cell FAULT、無條件開 contactor |
| Cloud↔Edge | Edge 繼續 local policy，拒絕新 remote command，持久化補傳 | 因 Internet 斷線停機 |

既有 BESS state-machine 草案的「任何通訊逾時一律 FAULT」過寬，正式化前必須依上表拆分。

---

## 4. 目標架構

### 4.1 C4 Level 1

~~~mermaid
flowchart LR
    OPS[現場操作員/維運]
    OWNER[業主/能源管理者]
    SERVICE[售後工程團隊]
    CLOUD[EMS Fleet Cloud]
    EDGE[Site EMS Edge]
    BMS[BMS/BCU]
    PCS[PCS]
    METER[電表/PCC]
    HVAC[HVAC]
    FIRE[消防/火警盤]
    STS[STS/ATS/保護電驛]
    IDP[OIDC IdP]
    NOTICE[通知服務]

    OPS -->|Local HTTPS/PWA| EDGE
    OWNER -->|HTTPS| CLOUD
    SERVICE -->|受控維運| CLOUD
    CLOUD <-->|Outbound mTLS MQTT/HTTPS| EDGE
    CLOUD --> IDP
    CLOUD --> NOTICE
    EDGE <-->|CAN/Modbus/DI-DO| BMS
    EDGE <-->|Modbus/SunSpec/vendor| PCS
    EDGE <-->|Modbus RTU/TCP| METER
    EDGE <-->|Modbus/BACnet| HVAC
    FIRE -->|Dry contact/Modbus read| EDGE
    EDGE <-->|DI-DO/Modbus status| STS
~~~

### 4.2 C4 Level 2

~~~mermaid
flowchart TB
    subgraph DEV[OT Devices / Safety Zone]
      BMS[BMS]
      PCS[PCS]
      METER[Meter]
      AUX[HVAC / Fire / STS]
    end

    subgraph EDGE[Site Edge Host]
      ADAPTER[Protocol Adapter Runtime]
      BROKER[(MQTT 5 Site Broker)]
      REG[Asset/Profile Service]
      CTRL[Site Controller]
      ALARM[Event/Alarm Service]
      HIST[(Local Timescale Historian)]
      SYNC[Store-and-Forward Sync]
      EDGEAPI[Local API/BFF]
      LOCALUI[Local Web/PWA]
      OTA[Update Agent]
      OBS[OTel/Prometheus Collector]
    end

    subgraph CLOUD[Central/Fleet]
      ING[Cloud Ingest]
      FLEET[Fleet/Tenant/Site]
      SCHED[Schedule/Optimization]
      CMD[Command Orchestrator]
      API[Product API/BFF]
      WEB[Web/PWA]
      TS[(Cloud Timescale)]
      OBJ[(Object Storage)]
      AUTH[OIDC/RBAC]
      NOTIFY[Notification]
      COBS[Logs/Metrics/Traces]
    end

    BMS --> ADAPTER
    PCS <--> ADAPTER
    METER --> ADAPTER
    AUX <--> ADAPTER
    ADAPTER <--> BROKER
    REG --> ADAPTER
    BROKER --> HIST
    BROKER --> CTRL
    CTRL --> BROKER
    BROKER --> ALARM
    HIST --> SYNC
    ALARM --> SYNC
    EDGEAPI --> REG
    EDGEAPI --> HIST
    EDGEAPI --> CTRL
    LOCALUI --> EDGEAPI
    OTA --> ADAPTER
    OBS --> SYNC

    SYNC <-->|outbound mTLS| ING
    ING --> TS
    ING --> FLEET
    WEB --> API
    API --> AUTH
    API --> FLEET
    API --> TS
    API --> CMD
    SCHED --> CMD
    CMD -->|signed desired intent| SYNC
    ALARM --> NOTIFY
    OTA <-->|signed manifest| OBJ
~~~

### 4.3 Data Flow：telemetry、alarm、command

~~~mermaid
sequenceDiagram
    autonumber
    participant D as BMS/PCS/Device
    participant A as Protocol Adapter
    participant B as Site MQTT
    participant H as Local Historian
    participant C as Site Controller
    participant S as Cloud Sync/API
    participant U as Web/PWA User

    loop poll/event cycle
      A->>D: Read profile-defined frames/registers
      D-->>A: Raw values/status
      A->>A: Decode + unit + quality + timestamps
      A-)B: telemetry/state/event
      B-)H: append locally
      B-)C: current state
      H-)S: store-and-forward when WAN available
    end

    C-)S: alarm/event + durable outbox
    S-)U: SSE/WebSocket + notification
    U->>S: Submit command intent
    S-)C: command_id + expiry + actor + desired value
    C->>C: auth proof, freshness, state, interlock, clamp
    alt accepted
      C->>A: validated command
      A->>D: allowlisted write
      A->>D: read-back
      D-->>A: actual value/state
      A-)C: ACK + evidence
      C-)S: CONFIRMED audit
    else rejected/expired
      C-)S: REJECTED/EXPIRED + reason
    end
~~~

### 4.4 部署原則

- MVP 單站：工業 IPC、Ubuntu LTS、Docker Compose + systemd watchdog、雙 SSD/UPS/雙 NIC；不先上 K3s。
- Pilot：單 Edge 主機 + cold spare image/config/replace SOP；Cloud 用 managed DB 與多個 stateless instances。
- Production：Edge 是否 active/standby 依 SLA；Cloud 才用 Kubernetes/managed containers、HA broker/DB、object storage。
- 站端只發 outbound mTLS；遠端維運走受控 bastion/Tailscale，MFA、短時憑證、audit。

---

## 5. OT/IT 網路分區

~~~mermaid
flowchart LR
    subgraph Z0[Zone 0 Safety]
      HW[EPO/Fire Trip/Relay]
      BMS[BMS]
      PCS[PCS Local Control]
    end
    subgraph Z1[Zone 1 OT]
      CAN[Isolated CAN]
      RS[Isolated RS-485]
      ETH[OT Ethernet VLAN]
    end
    subgraph Z15[Zone 1.5 Edge DMZ]
      GW[Protocol Gateways]
      CTRL[Site Controller]
      BUS[Broker/Historian]
      HMI[Local HMI]
    end
    subgraph Z2[Zone 2 Site IT]
      OPS[Ops Workstation]
      BASTION[Bastion/Update Cache]
    end
    subgraph Z3[Cloud]
      API[Cloud API/Fleet]
    end

    HW --> BMS
    HW --> PCS
    BMS --> CAN --> GW
    PCS --> ETH --> GW
    RS --> GW
    GW <--> CTRL
    GW --> BUS
    OPS -->|HTTPS| HMI
    BASTION -->|signed update| GW
    BUS -->|outbound mTLS| API
~~~

強制要求：

- 每個 field bus 只有指定 adapter 可達；Cloud/Web/Grafana/AI 不直接進 OT VLAN。
- Modbus TCP 以 firewall source/destination/port allowlist；RTU 用 isolated converter、single master、bus timeout。
- CAN 不橋接一般 LAN；adapter 只公開 normalized signals 與 allowlisted commands。
- 消防/EPO trip 保持硬線；EMS 僅 monitor/event log，不能唯一 trip，也不 remote reset。
- Production broker 禁 anonymous；client cert subject 綁 org/site/gateway，ACL 限 topic。
- Production DB/MQTT/PostgREST 不做 public host port，只允許 service network/bastion。

---

## 6. 設備與協定策略

### 6.1 選用原則

| 協定 | 適用 | 限制 | 決策 |
|---|---|---|---|
| CAN 2.0B/CAN FD | BMS↔PCS、BCU/rack | 不跨 Internet；需 DBC/vendor map、bus load/隔離 | Edge/local only |
| Modbus RTU | 電表、HVAC、I/O、RS-485 | 無 auth、single master、低速、endian 風險 | profile+HIL 後支援 |
| Modbus TCP | PCS、電表、STS、HVAC | 無 security、write risk | OT VLAN + FC/address allowlist |
| SunSpec Modbus | 支援 SunSpec 的 PCS/PV | vendor extension 常見 | 優先於全私有 map，仍需 HIL |
| MQTT 5 | Edge bus、Edge↔Cloud | 不承擔硬保護 | 內部標準 event bus |
| OPC UA | 北向 SCADA/MES、semantic/cert | 小設備成本高 | Pilot 後按案場提供 |
| BACnet/IP | HVAC/building system | 與 battery BMS 名稱易混淆 | HVAC 要求才支援 |
| IEC 61850/104 | Substation/utility | 合規成本高 | 僅 contract 要求立案 |
| REST/HTTPS | 管理、報表、batch sync | 不作 field-bus control | Web/Cloud |
| SSE/WebSocket | Browser live state | 不作 device protocol | UI only |

### 6.2 設備介面與控制界線

| 設備 | 主要介面 | 讀取 | 寫入 | 本地/硬線 |
|---|---|---|---|---|
| BMS/BCU | CAN；可另 Modbus | SOC/SOH、cell min/max、T、絕緣、allowable current、fault | 原則只讀；設定需 maintenance mode/local auth | fault/EPO/contactor 不依賴 EMS |
| PCS | Modbus TCP/SunSpec/vendor CAN | mode、P/Q、V/f、DC/AC、fault/capability | start/stop、P/Q、mode preference，經 site-controller | watchdog、relay、PLL、防孤島 local |
| PCC/Revenue meter | Modbus RTU/TCP | V/I/P/Q/PF/f/energy/demand | 通常不寫 | metering seal/calibration |
| HVAC | Modbus/BACnet | temp/humidity/fan/compressor/fault | non-safety setpoint/fan | over-temp/smoke local |
| Fire panel | Dry contact + read-only Modbus | alarm/trouble/release | 不 remote reset/release | trip/release hardwired |
| STS/ATS | DI/DO + Modbus status | source/position/ready/fault | Pilot 前預設 read-only | sub-20ms transition local |
| Environment/access | Modbus/MQTT/DI | leak/smoke/door/fan | case-specific | access/EPO independent |

### 6.3 Device Profile Contract

每個 Supported 型號交付 immutable/versioned profile：

- vendor/model/firmware range、protocol/connection；
- register/frame ID、type、byte/word order、scale、unit、valid range；
- read/write、allowed function code/address；
- poll groups：100 ms/1 s/10 s/on-change；
- timeout/retry/backoff/stale threshold；
- quality mapping、fault bitmap/severity；
- command precondition/read-back/watchdog/fallback；
- HIL fixture、golden capture、profile hash；
- firmware compatibility；unknown/incompatible firmware fail closed。

AI 可產生候選 profile，但不可發明 map；未經 HIL 不可標 Supported。

---

## 7. Canonical Data、品質與時間

### 7.1 Telemetry Envelope v1

MVP 採 JSON + JSON Schema；保留 content-type 升級到 Protobuf 的入口。

~~~json
{
  "schema_version": "1.0",
  "organization_id": "org-001",
  "site_id": "site-001",
  "gateway_id": "edge-001",
  "device_id": "pcs-001",
  "profile_version": "vendor-model@1.2.0",
  "sequence": 184225,
  "source_time": "2026-09-03T10:00:00.120Z",
  "acquired_time": "2026-09-03T10:00:00.145Z",
  "quality": "GOOD",
  "signals": [
    {"name": "active_power", "value": 42.1, "unit": "kW", "quality": "GOOD"}
  ]
}
~~~

DB 另加 ingested_time。禁止單一 time 同時代表設備事件與平台收件時間。

### 7.2 Quality Model

| Quality | 條件 | UI/控制 |
|---|---|---|
| GOOD | profile 合法、range/clock/communication 正常 | 可顯示；可參與 supervisory control |
| UNCERTAIN | clock drift、fallback timestamp、部分欄位缺失 | 黃色；按 signal policy 決定 |
| BAD | CRC/parse/range/device fault | 不參與 control，保留 evidence |
| STALE | 超過 profile threshold | 顯示 age，control fail closed |
| SUBSTITUTED | manual/algorithm replacement | 顯示來源，預設不進 auto control |

保留 quality_reason、source、profile/config version、sequence。Adapter 做入口驗證，DB 再 schema constraint。

### 7.3 時間同步

- Edge 用 chrony/NTP 至少兩個 source，外部時間中斷時靠 RTC。
- Device time 記 source_time；沒有則 source_time=null、用 acquired_time 並標 TIME_FALLBACK。
- Clock offset >100 ms 告警，>1 s 時依賴時間排序的控制輸入標 UNCERTAIN。
- PTP 僅在 sub-ms 確有需求時導入；NTP 不能宣稱 protection-grade。
- UTC storage，site timezone display；DST/跨時區列測試。

### 7.4 取樣與保留

| 資料 | Edge | Cloud | 備註 |
|---|---|---|---|
| PCS/PCC/BMS summary | 1 s，至少 90 天 | 1–10 s 或 1 min aggregate，13 個月 | 營運主資料 |
| 全 cell array | 5–10 s + event burst；依保固容量評估 | aggregate 或 Parquet bundle | 不盲目存 112×每秒窄列多年 |
| Fault black box | 前後各 30 s、100 ms/設備原生率 | raw/Parquet，至少保固期 | BMS 為 warranty source of truth |
| Alarm/Event/Command/Audit | append-only，Edge ≥12 月 | 3–7 年待合約確認 | 法規/保固待核 |
| Aggregates | 1 min/15 min/1 h | 13–36 月 | demand/tariff/report |

若業主要求全 cell 1 s 保存 12 個月，須先做容量、壓縮與 backup restore benchmark，不能直接塞一般 row-per-signal 熱表。

---

## 8. Event、Alarm 與控制閉環

### 8.1 Alarm State

~~~text
NORMAL → PENDING → ACTIVE → CLEARED
                    │
                    └── ACKED（確認不等於清除）
ACTIVE/ACKED 可 SHELVED（有期限、理由、actor、audit）
~~~

- Rule versioned：threshold/delay/hysteresis/severity/owner/runbook。
- Dedupe/suppression 避免 BMS/PCS/communication alarm storm。
- Notification 用 durable outbox、retry/dead-letter/delivery status/secondary channel；Telegram 不作唯一證據。
- ACK 不改 device fault、不代替 reset。
- P0/P1 有 runbook/escalation timer。

### 8.2 Command Lifecycle

~~~text
CREATED → AUTHORIZED → VALIDATED → DISPATCHED → ACKED → CONFIRMED
                ├→ REJECTED
                ├→ EXPIRED
                └→ FAILED / UNKNOWN（reconciliation）
~~~

必填：command_id、site_id、target、type、desired、issued_by/reason、issued_at/expires_at、idempotency_key、policy_version、expected_state_version。

流程：

1. Web/App 只送 intent 到 Product API。
2. API 驗 AuthN/AuthZ/site scope/MFA/approval。
3. 過 expires_at 的命令立即 EXPIRED。
4. Site Controller 驗 freshness、state、interlock、BMS/PCS limits、local override、ramp。
5. Adapter 只執行 profile allowlist write。
6. Write 後 read-back；actual 符合 tolerance 才 CONFIRMED。
7. Timeout 進 reconciliation，不盲目 repeat；僅 idempotent command 可 auto retry。
8. 每步 append audit，含 reject/clamp reason 與 requested/final setpoint。

### 8.3 AI/MCP

- 現有 kc-mcp-server 直接 Modbus write 只適合 dev simulator，不得成為 production control。
- Production MCP 先 read/diagnostic/advisory；控制工具只能呼叫 control-service，無 bypass。
- AI output 不直接成 command；經 deterministic schema/range/state/policy。高影響命令需人工或 dual approval。

---

## 9. Web/PWA 與 App

### 9.1 Information Architecture

| 模組 | MVP | Pilot | Production |
|---|:---:|:---:|:---:|
| OIDC/站點切換 | 基本 | MFA/role | federation/audit |
| Fleet/site overview | 單站 | 多站 | portfolio KPI |
| BESS single-line/asset topology | read | state-linked | maintenance history |
| P/Q/SOC/SOH/limits/mode | 必須 | 必須 | 必須 |
| Trends/query/export | 必須 | compare/aggregate | scheduled report |
| Alarm console | active/ack | suppress/escalate | SLA/report |
| Command center | 無寫 | controlled P/Q/start-stop | dual approval |
| Schedule/demand | display | edit/simulate/deploy | optimization |
| Device/profile/connection | 必須 | commissioning | fleet bulk |
| Audit/black box | query | export | compliance archive |
| OTA/config | 無 | canary | rings/rollback |
| User/role/site | 基本 | 完整 | delegated admin |

現有 frontend 可保留 design system/Auth/Device/Review 元件，但不足以證明 BESS 操作產品已完成。

### 9.2 Browser Communication

- CRUD/query/command：HTTPS REST /api/v1。
- Alarm/command/site summary：SSE 優先；需要雙向協作才 WebSocket。
- Cell array 不直接 high-rate push；API downsample/page/event bundle。
- Browser 不直連 MQTT/PostgREST/Timescale/Modbus。

### 9.3 App 決策

MVP/Pilot 用 responsive PWA：notification deep link、site summary、ACK、QR、work-note。手機不提供 contactor/fire reset/STS switching 或無二次確認 start-stop。

只有 BLE/NFC commissioning、background sync、MDM、可靠 push、camera inventory、fully-offline work order 被驗證後才做 native。若立案，React Native/Expo 共用 OpenAPI TS types 與 OIDC，不強求共用 UI。

---

## 10. API、MQTT 與資料模型

### 10.1 Product REST API

~~~text
GET    /api/v1/organizations
GET    /api/v1/sites
GET    /api/v1/sites/{site_id}/summary
GET    /api/v1/sites/{site_id}/assets
GET    /api/v1/assets/{asset_id}/signals
GET    /api/v1/assets/{asset_id}/measurements?from=&to=&resolution=&cursor=
GET    /api/v1/sites/{site_id}/events
GET    /api/v1/sites/{site_id}/alarms
POST   /api/v1/alarms/{alarm_id}/ack
POST   /api/v1/alarms/{alarm_id}/shelve
GET    /api/v1/sites/{site_id}/commands
POST   /api/v1/sites/{site_id}/commands
POST   /api/v1/commands/{command_id}/approve
GET    /api/v1/sites/{site_id}/schedules
POST   /api/v1/sites/{site_id}/schedules
POST   /api/v1/schedules/{schedule_id}/deploy
GET    /api/v1/device-profiles
POST   /api/v1/sites/{site_id}/config-deployments
GET    /api/v1/sites/{site_id}/audit-events
GET    /api/v1/stream
~~~

OpenAPI 3.1；cursor pagination、idempotency、ETag/expected version、error code、rate limit、actor/site scope/retry 逐 endpoint 標示。BFF runtime contract 也要納入 drift gate。

### 10.2 MQTT 5 Topics

~~~text
ems/v1/{org}/{site}/{gateway}/{device}/telemetry
ems/v1/{org}/{site}/{gateway}/{device}/state
ems/v1/{org}/{site}/{gateway}/{device}/events
ems/v1/{org}/{site}/{gateway}/availability
ems/v1/{org}/{site}/commands/{target}
ems/v1/{org}/{site}/command-acks/{target}
ems/v1/{org}/{site}/config/{gateway}
ems/v1/{org}/{site}/config-acks/{gateway}
~~~

- High-rate lossy telemetry 可 QoS0；state/event/ack QoS1 + persistent session + expiry + dedupe。
- Command QoS1 + expiry/idempotency，**不 retained**。
- Availability/current config 可 retained。
- Topic ACL 與 cert identity 綁 org/site/gateway。
- ILP 只留 legacy adapter input；product bus 用 storage-agnostic envelope。

### 10.3 Core Data Model

| Entity | 核心欄位 | 安全/保留 |
|---|---|---|
| organizations | id/name/policy | tenant root |
| sites | id/organization/timezone/grid_contract | RLS |
| assets | id/site/parent/type/lifecycle | rack/string/PCS/meter topology |
| gateways | id/site/cert/software/last_seen | Edge identity |
| device_profiles | vendor/model/version/schema/hash/status | immutable |
| device_connections | device/gateway/protocol/endpoint/profile | secret ref |
| signal_definitions | profile/name/unit/type/access/range/poll | version lineage |
| signal_measurements | time/site/device/signal/value/quality/sequence | hypertable |
| events | id/site/device/type/severity/times/detail | append-only |
| alarm_instances | rule/state/first/last/ack/clear | ACK≠clear |
| commands | id/site/target/type/requested/final/status/expiry/actor | append-only transitions |
| command_attempts | command/attempt/write/readback/error/time | append-only |
| schedules | site/version/window/strategy/status/approved_by | immutable versions |
| config_deployments | hash/targets/ring/status/rollback | immutable |
| audit_events | actor/action/resource/outcome/request/time/hash | WORM-like |

現有 devices(device_id PK) 應遷移為 UUID 或 UNIQUE(site_id, external_device_id)。產品表帶 site_id，DB RLS + service authorization 雙重強制；只靠 API filter 不算 tenant isolation。

---

## 11. RBAC、OIDC、多租戶

### 11.1 Roles

| Role | 權限 |
|---|---|
| platform_admin | 平台維運，不預設站端控制 |
| organization_admin | users/sites/reports |
| site_admin | site config/profile/maintenance |
| operator | monitor/ACK/low-risk command |
| dispatcher | schedule/PQ intent/approval |
| maintainer | commissioning/profile/diagnostic |
| auditor | audit/event/export read |
| viewer | dashboard/report read |

現有 OPS/INGEST/READONLY 是 service channel role，不足以作 product role。保留 channel credentials，但 user role 映射 permission，例如 command.pcs.setpoint、alarm.ack、config.deploy。

### 11.2 Auth

- OIDC Authorization Code + PKCE；Production MFA。
- HttpOnly/Secure/SameSite cookie、server-side refresh；SPA 不存 token/secret。
- Multi-instance 前把 in-memory session/state 換 Redis。
- High-impact command 要 step-up，必要時 dual approval；local key/switch 可 disable remote.
- Authorization 依 actor + org/site + permission + resource；role change 立即 revoke。
- Edge offline auth 另定：只 cache minimum identity/expiry；離線 high-impact command 預設禁用或需 physical authorization。

---

## 12. Offline、Recovery、OTA

### 12.1 Offline State

| WAN | Telemetry | Control | User | Sync |
|---|---|---|---|---|
| ONLINE | local + cloud | local executes approved intent | local/cloud UI | continuous |
| DEGRADED | local first | only unexpired downloaded policy | local UI | retry/batch |
| OFFLINE | local durable | local policy or profile ramp-to-zero | local ops | spool |
| RECOVERING | local | reconcile actual state first | show unsynced | ordered replay/dedupe |

復線以 actual device state 為權威，不把舊 desired state 覆蓋現場。Command 過期丟棄；telemetry/event 補傳保留 acquired time。

### 12.2 OTA/Config

- Artifact/manifest signed；Edge verify hash/signature/compatibility/minimum version。
- Dev→internal→pilot ring→production ring，health observation window。
- 保留 previous image/config；health gate fail auto rollback。
- DB migration 用 expand/migrate/contract。
- Config/profile immutable version，deployment 只切 active pointer。
- Offline 不做半套 update；第三方 PCS/BMS firmware 走 vendor process。
- 自研 BMS firmware 另需 secure boot、signed image、bootloader rollback、local recovery。

---

## 13. Observability 與 NFR

### 13.1 Metrics

| 類別 | 指標 |
|---|---|
| Device/Adapter | poll success、timeout、CRC/parse、RTT、stale age、bus load |
| Data | points/s、quality ratio、gap/duplicate、clock offset、spool depth/age |
| Control | validate/reject/dispatch/confirm latency、clamp count、unknown outcome |
| Alarm | eval、active/ack/clear、delivery/dead-letter、storm suppression |
| Edge | CPU/RAM/disk/SSD、restart、NTP、cert expiry、UPS |
| Cloud | ingest lag、API latency、tenant deny、sync backlog |
| OTA | ring、download/verify/install/rollback、version drift |

JSON logs 必帶 trace_id/request_id；command/event 加 command_id/event_id/site/device。採 Prometheus + OpenTelemetry + Loki/Tempo；Grafana 作 engineering ops。

### 13.2 Pilot NFR Gate

| 指標 | 目標 | 驗證 |
|---|---|---|
| adapter→broker p99 | ≤250 ms（不含 poll interval） | HIL timestamp |
| broker→historian p99 | ≤1 s | acquired/ingested diff |
| command accepted→write attempt p99 | ≤500 ms | command trace |
| read-back confirmation | ≤2 polling cycles | HIL |
| supervisory loop | 1 s；miss deadline <0.1% | 72h soak |
| safety loop | 不屬 EMS | boundary review |
| WAN loss | 72h local + no command replay | partition test |
| Offline buffer | ≥7 天負載，disk 80% 前 alarm | capacity/fill |
| Edge availability | 99.9%/月 | SLO |
| Cloud API p99 | <500 ms operational read | load test |
| Site scale | ≥5,000 points/s、200 logical devices | replay |
| Control audit | 100% terminal/reconciliation evidence | invariant query |
| Security | no anonymous broker/public DB/field bus | deployment scan |

Production 再鎖 RTO/RPO/HA；Pilot 前不承諾 500 sites × 5,000 points/s 直送 Cloud，應由 edge aggregation 與 benchmark 決定。

---

## 14. 現有程式：沿用、重構、新建

| 模組 | 沿用 | 重構 | 新建/取代 |
|---|---|---|---|
| services/simulator | fault injection | BMS/PCS/HVAC/STS scenario/replay | HIL harness/golden frames |
| Telegraf gateway | simple read telemetry | profile-driven、quality/time、least privilege | CAN/command adapter runtime |
| Mosquitto | broker | pin、mTLS、ACL、persistence/quota | edge-cloud bridge policy |
| Telegraf ingest | legacy fixed tables | remove superuser、TLS/buffering | canonical ingest-generic |
| TimescaleDB | historian | pin/compress/retain/tenant/backup | local/cloud tier + object bundle |
| PostgREST | internal legacy read | no public port/least privilege | product API semantics |
| device-service | registry/signals/audit/AI suggestion | org/site/asset/profile/health；AI provisioning only | profile/commissioning service |
| kc-mcp-server | simulator diagnostic | no production direct write | control-service/MCP bridge |
| BFF | same-origin/CSRF/OIDC/facade | Redis/product role/site/rate limit/OpenAPI | site/alarm/command/schedule facade |
| Frontend | design/Auth/Device/Review | stale comments、PWA、site scope | operation/alarm/trend/schedule/control/audit |
| Grafana | internal ops | datasource least privilege | customer UI stays React |
| OpenAPI/CI | drift/version | lint/diff/BFF/AsyncAPI | profile/schema conformance/HIL artifact |
| Compose | dev/MVP edge | prod override/secrets/networks | cloud deployment/signed release |

Immediate debt:

1. Implement ADR-026 BFF POST/PATCH + tests。
2. Correct PRD/ADR statuses and frontend stale comments with four-state tracking。
3. Complete/re-review PRD-0006/ADR-022 with tenant/capacity before BESS ingest。
4. Pin images; no default password in production。
5. Build BESS profile schema/simulator, then read-only hardware adapter。

---

## 15. PRD 拆分與依賴

以下編號暫定；合併前由 doc/prd/README 正式分配。

| PRD | 主題 | 依賴 | 核心交付 |
|---|---|---|---|
| 0007 | Device Profile & Protocol Adapter SDK | protocol docs/HIL | profile、Modbus/CAN、golden/HIL |
| 0008 | Organization/Site/Asset & Multi-tenancy | migration governance | tenant/site/RLS/API |
| 0009 | Edge Runtime & Store-and-Forward | 0007/0008 | broker/historian/sync/offline |
| 0010 | Alarm/Event/Notification | 0008/0009 | rule/state/outbox/escalation |
| 0011 | BESS Supervisory Control/Command | HIL + state ADR | lifecycle/arbiter/clamp/readback |
| 0012 | BESS Operations Web/PWA | 0008/0010；control page needs 0011 | operations console |
| 0013 | Fleet Cloud & Site Sync | 0008/0009 | multi-site ingest/fleet API |
| 0014 | Config/OTA Release | edge release | signed artifact/rings/rollback |
| 0015 | Production Security/Observability/DR | all | zones/SLO/DR/pentest |
| 0016 | Tariff/Demand/Optimization | clean data + controlled command | tariff/15-min demand/schedule |

~~~text
0007 Profiles/Adapters ─┐
0008 Tenant/Site ───────┼─→ 0009 Edge/Offline ─→ 0010 Alarm
                        │                    └─→ 0013 Fleet
BMS/PCS HIL + State ADR ┴──────────────────────→ 0011 Control
0010 + 0011 + 0013 ────────────────────────────→ 0012 Web/PWA
0009 + release pipeline ───────────────────────→ 0014 OTA
all ───────────────────────────────────────────→ 0015 Prod Gate
clean data + controlled command ───────────────→ 0016 Optimization
~~~

---

## 16. MVP→Pilot→Production 時程

### 16.1 團隊

Architect/Product 1、Edge/OT 2、Backend/Data 2、Frontend/PWA 1、QA/HIL 1、DevOps/SRE/Security 0.5–1。以下為 12 月 7–8 FTE；2–3 人則 18–24 月。

### 16.2 Phase 0：Week 0–4

| WP | 工作 | Exit |
|---|---|---|
| WP-00 | boundary/state/失聯策略 | Accepted ADR |
| WP-01 | BMS/PCS/meter/HVAC/fire/STS interface | model/protocol/write/watchdog/HIL matrix |
| WP-02 | canonical telemetry/event/command | JSON Schema/AsyncAPI v1 |
| WP-03 | Edge hardware/network | IPC/NIC/CAN/RS485/VLAN/storage sizing |
| WP-04 | test/safety case | bench BOM、hazard、trace matrix |

Gate：無正式 map/HIL 的型號不得列 Supported。

### 16.3 MVP：Week 5–16（單站 read-only）

| Week | WP | 工作 | 驗收 |
|---|---|---|---|
| 5–7 | WP-10 | profile SDK + replay | golden decode 100% |
| 5–8 | WP-11 | org/site/asset migration | tenant contract |
| 8–10 | WP-12 | BMS/PCS/meter read adapters | 24h continuous + quality |
| 8–11 | WP-13 | canonical ingest/compression | ≥5,000 points/s |
| 10–12 | WP-14 | mTLS broker/local historian | restart durable event |
| 11–14 | WP-15 | site/device/trend/alarm Web | desktop/mobile UAT |
| 12–15 | WP-16 | Alarm v1/durable outbox | delivery retry/status |
| 15–16 | WP-17 | SIL/HIL/partition/72h soak | MVP report |

Gate：read-only real hardware、offline collection、quality/time trace、Web alarm；no remote setpoint/start-stop。

### 16.4 Pilot：Week 17–32（受控單站閉環）

| Week | WP | 工作 | 驗收 |
|---|---|---|---|
| 17–20 | WP-20 | command store/state/idempotency/readback | property tests |
| 19–23 | WP-21 | Site Controller interlock/clamp/ramp | model + HIL |
| 21–25 | WP-22 | PCS P/Q/start-stop、HVAC adapter | timeout/fallback matrix |
| 22–26 | WP-23 | schedule/demand v1 + dry-run | intent trace |
| 24–27 | WP-24 | multi-site sync/Redis/OIDC/MFA | 3-site isolation |
| 25–29 | WP-25 | Web command/approval/alarm | RBAC/CSRF/IDOR E2E |
| 27–30 | WP-26 | signed config + rollback | failed-health rollback |
| 29–32 | WP-27 | field pilot | 30-day evidence |

Gate：限定範圍 P/Q/start-stop；命令可 trace/readback；WAN loss 不破壞 local；remote control 可 local-disable。

### 16.5 Production：Week 33–52

| Week | WP | 工作 | 驗收 |
|---|---|---|---|
| 33–38 | WP-30 | observability/capacity/soak | 30/90-day sizing/runbook |
| 35–40 | WP-31 | HA/backup/DR | RTO/RPO drill |
| 37–43 | WP-32 | IEC 62443 mapping/cert/SBOM/pentest | findings closed |
| 40–46 | WP-33 | OTA rings/A-B/config drift | canary/rollback |
| 42–48 | WP-34 | multi-site/report/authz | tenant escape/UAT |
| 46–50 | WP-35 | support/commissioning/training | field exercise |
| 50–52 | WP-36 | Release Candidate | traceability PASS/sign-off |

---

## 17. 測試與驗收

| 層 | 內容 | 頻率 |
|---|---|---|
| Unit/Property | codec/endian/quality/clamp/state/idempotency | every PR |
| Contract | OpenAPI/AsyncAPI/JSON Schema/profile/MQTT ACL | every PR |
| SIL | BMS/PCS/meter/HVAC/STS/fault/clock replay | PR/nightly |
| Integration | broker/DB/BFF/sync/RLS/outbox | CI/nightly |
| HIL | each model/firmware/read/write/timeout/watchdog/readback | release |
| System | WAN loss/restart/disk full/NTP drift/DB/broker/OTA | milestone |
| Security | SAST/SCA/SBOM/secret/ports/ACL/authz/pentest | CI/release |
| Field | 30-day SLO/alarm/command/manual workflow | Pilot gate |

不變式：

- 無 GOOD/fresh limit/state，command 不 dispatch。
- Cloud/Web/AI 不越 BMS/PCS/local interlock。
- Expired command 不執行；reconnect 不重放 retained command。
- Same idempotency key 不造成第二次 physical action。
- CONFIRMED 有 read-back；write ACK 不夠。
- 每個 command 有 terminal 或 UNKNOWN+reconciliation。
- Tenant A 無法看到/控制 Tenant B。
- WAN/Cloud/BFF/Grafana fail 不影響 hardware protection/local basic operation。
- Fire/EPO/STS speed/safety 不依賴 EMS。

新增 CI：BFF/Product OpenAPI drift+lint+diff、AsyncAPI/schema compatibility、profile/golden decode、SBOM/sign/CVE、compose integration、nightly SIL、HIL artifact、migration/backup restore。

---

## 18. 主要風險

| ID | 風險 | 機率/衝擊 | 對策 |
|---|---|---|---|
| E-R01 | vendor map 不全/firmware drift | H/H | contract/version/golden/HIL |
| E-R02 | EMS 誤作 protection controller | M/H | authority matrix/safety review |
| E-R03 | timeout semantics conflict | H/H | link-specific FMEA/HIL |
| E-R04 | anonymous broker/public ports 進 Pilot | M/H | prod gate/deploy scan/mTLS |
| E-R05 | multi-tenant late retrofit | H/H | site/org keys/RLS first |
| E-R06 | cell telemetry explosion | H/M | edge tier/object bundle/benchmark |
| E-R07 | retry causes duplicate action | M/H | idempotency/readback/reconciliation |
| E-R08 | reconnect overwrites actual state | M/H | actual-state authority/expiry |
| E-R09 | Web only has registry review | H/M | BESS Operations Console/UAT |
| E-R10 | Native App splits team | M/M | PWA first/gated native |
| E-R11 | 2–3 person unrealistic schedule | H/H | 18–24 months or reduce scope |
| E-R12 | AI/MCP bypass | M/H | advisory first/single policy API |
| E-R13 | OTA bricks site | M/H | signed/rings/A-B/local recovery |
| E-R14 | docs ahead of code | H/M | Decision/Implemented/Verified/Released |

---

## 19. 待 Stakeholder 決策

1. Pilot PCS/BMS model、firmware、map/HIL sample。
2. 是否需 island/black start/STS；切換 authority 在 PCS、microgrid controller 或 PLC。
3. Cloud loss 時 last schedule 保持多久、何時 ramp-to-zero、是否 local optimization。
4. Remote command scope：P/Q、start-stop、mode、alarm reset 分別定義。
5. BMS warranty 對 full-cell logging 的 sampling/retention/export，EMS 是否複製原始資料。
6. Multi-tenant business model 與 EPC/maintainer cross-org delegation。
7. Pilot/Production SLA、RTO/RPO、retention contract。
8. IdP/MFA/group claim 與 Edge offline login。
9. Edge IPC/storage/CAN/RS485/UPS benchmark。
10. IEC 61850/104、OPC UA、BACnet、utility dispatch 是否 contract-required。

---

## 20. 正式文件放置與命名建議

現有 repo 的有效慣例：

- 產品需求：doc/prd/PRD-NNNN-kebab-case-title.md
- 架構權威：doc/architecture/kebab-case.md
- 決策：doc/adr/ADR-NNN-title.md
- 治理：doc/governance/kebab-case.md
- doc/archive/plan 是原始過程紀錄，不適合新 master plan。

建議但本草案不建立：

- Master Program Plan：doc/program/EMS-BMS-Master-Program-Plan.md（需新建 doc/program 並加 README/index）
- EMS Design Spec：doc/architecture/ems-edge-cloud-platform-architecture.md
- 可執行需求拆入 doc/prd/PRD-0007...，重大決策另開 ADR。
- 若不想新增 doc/program，次佳是 doc/EMS-BMS-Master-Program-Plan.md；不建議放 archive。

---

## 21. Self-Review

| 檢查 | 結果 |
|---|---|
| Goals/Non-Goals | PASS |
| Quantified NFR | PASS at program level |
| Context/Container/Data Flow | PASS |
| Data model/retention | PASS；法規年限待決 |
| API/MQTT contract | Draft；實作前需 OpenAPI/AsyncAPI |
| OT/IT/security boundary | PASS at architecture；需 security/FMEA review |
| Rollout/rollback | PASS at program；per-PRD 需 trigger |
| Unit/Integration/E2E/HIL | PASS |
| Current implementation map | PASS；依 2026-09-03 worktree，未執行 test |
| Open questions | §19；不得自行視為承諾 |

**Status: DONE_WITH_CONCERNS.** 架構可作 Master PRD 骨架；PCS/BMS 型號、失聯策略、remote control、retention、Pilot SLA 未定前，不應轉成客戶承諾。
