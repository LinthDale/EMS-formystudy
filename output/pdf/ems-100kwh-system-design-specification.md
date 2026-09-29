# 100 kWh 級電池儲能系統能源管理系統設計規格書

### 適用單站 1P112S／50 kW 基線：Edge 自治、設備整合、Web 應用程式與 Cloud

作者：＿＿＿＿　　日期：2026-09-03　　版本：v0.1

---

## 摘要

本文提出一套適用於 100 kWh 級電池儲能系統（Battery Energy Storage System, BESS）的能源管理系統（Energy Management System, EMS）設計。系統採站端 Edge 為離線自治權威、Cloud 為跨站管理與長期資料服務的分層架構；透過版本化 Device Profile 與 Protocol Adapter 整合電池管理系統（Battery Management System, BMS）、功率轉換系統（Power Conversion System, PCS）、電表、熱管理、消防與選配微電網控制設備。

EMS 負責資料品質、歷史資料、告警、排程、需量與監督式功率請求，不承擔電芯保護、PCS 內環、接觸器直接驅動、消防跳脫或 protection-grade 切換。所有命令須經身分授權、期限、狀態、互鎖、能力夾箝、設備寫入、回讀與 reconciliation，並保留完整稽核。使用者介面採 Web／Progressive Web App（PWA）優先；原生 App 僅在 BLE/NFC、MDM、背景同步或完整離線工單需求成立後立案。

---

## 一、文件定位與使用方式

### 1.1 設計目標

本設計應完成下列閉環：

1. 在 WAN 或 Cloud 失效時，站端仍能依受控 local policy 監測、記錄、告警與維持安全的監督式運轉。
2. 以版本化 Device Profile 管理不同廠牌、型號與韌體的訊號、命令、故障及失聯行為。
3. 將 BMS 能力邊界、PCS capability、場站契約、SOC reserve、熱降載與 ramp rate 統一為可追溯的 command clamp。
4. 使每筆 telemetry、alarm、command、configuration 與 audit 可回溯到來源時間、取得時間、版本與品質。
5. 以同一產品架構支援單站 BESS，並以選配 PRD 擴充 Microgrid／DG／PV／ATS/STS，而不把選配責任混入 Base EMS。

### 1.2 規範用語

- 「應」：對應 Gate 前必須實作並驗證。
- 「目標」：優先達成；未達時須提出量測、替代方案與核准。
- 「初始值」：供 v0.1 實作與 sizing，Pilot 前須由 benchmark 確認。
- 「待核」：缺業主、供應商或法規輸入，不得作為正式承諾。
- 「Supported」：指定 model／firmware／profile 已通過 golden capture、SIL/HIL 與 fault matrix。

### 1.3 要求狀態

| 狀態 | 定義 | 設計處置 |
|---|---|---|
| A - 已核准 | 系統責任與設計原則已確定 | 可進入設計與驗證 |
| P - 初步 | 可供 v0.1 實作 | Pilot 前須 benchmark |
| T - 待確認 | 外部輸入尚未取得 | 不得形成對客 SLA／功能承諾 |

---

## 二、系統基準與範圍

### 2.1 參考系統

| 項目 | 基線 | 狀態 |
|---|---|---|
| BESS | 1P112S、50 kW-class、112.5 kWh nominal | A |
| BMS | 自研 BMU／BCU；發布 SOC、SOH、CCL、DCL、fault | A |
| PCS | 外購；型號與韌體待 RFQ/HIL | T |
| Site Edge | 工業 IPC、Ubuntu LTS、雙 NIC、TPM、watchdog、UPS | P |
| Cloud | Managed DB／object storage、Fleet API、IdP | P |
| 使用者介面 | Responsive Web／PWA | A |
| Microgrid | L1 PLC／relay／ATS／DG／PV 為選配 | A |

### 2.2 In Scope

- Device Profile、Modbus／CAN Adapter、設備 discovery 與 commissioning。
- Edge broker、historian、store-and-forward、Site Controller、local HMI。
- Canonical telemetry、event、alarm、command、schedule、configuration、audit。
- Web/PWA 的 site、single-line、trend、alarm、command、audit 與 administration。
- Cloud fleet、site sync、長期 archive、報表、release distribution。
- OIDC、RBAC、multi-tenancy、mTLS、SBOM、signed release、backup／restore。
- SIL、HIL、fault injection、network partition、72 h soak 與 30-90 日 Pilot 證據。

### 2.3 Out of Scope

- 電芯 OV/UV/OT/OC、絕緣、接觸器與預充的最終安全控制。
- PCS current/voltage inner loop、protection-grade relay 與快速切換。
- 消防釋放、EPO、breaker trip 的唯一控制路徑或遠端 reset。
- 未經獨立 PRD、ICD 與 DVP 的 DG、PV、ATS/STS、black-start 與 closed-transition。
- MVP 原生 App、AI 自主控制與未經 HIL 的自動產生設備 map。

---

## 三、控制分層與權責

### 3.1 Authority Matrix

| 優先權 | 權威 | 功能 | EMS 可否覆寫 |
|---|---|---|---|
| 1 | EPO／Fire／Fuse／Protection Relay | 人身與硬體保護 | 不可 |
| 2 | BMS／PCS Local Controller | 電池能力、OV/UV/OT/OC、V/I 內環 | 不可 |
| 3 | L1 PLC／Microgrid Controller（選配） | ATS、DG、load shed、deterministic sequence | 只接受 mode request |
| 4 | EMS Edge／Site Controller | P/Q、schedule、reserve、ramp、lost-link policy | 可被 local constraint 拒絕 |
| 5 | Cloud／Web／User | desired intent、ACK、configuration | Edge 可拒絕／過期／夾箝 |
| 6 | AI／Optimizer | 建議、預測、diagnostic | 預設不得直接執行 |

### 3.2 EMS-CTL 系統要求

| ID | 設計要求 |
|---|---|
| EMS-CTL-001 | EMS 不得成為 BMS、PCS、Fire、EPO 或保護電驛的唯一安全路徑。 |
| EMS-CTL-002 | Web／Cloud／AI 不得直接連線或寫入 CAN、Modbus 或硬線 I/O。 |
| EMS-CTL-003 | Site Controller 僅輸出經 profile allowlist 的 command，且不得超越 BMS CCL/DCL 或 PCS capability。 |
| EMS-CTL-004 | 任一 safety-critical input 為 STALE、BAD、缺失或版本不相容時，命令應拒絕或依 profile 受控 ramp-to-zero。 |
| EMS-CTL-005 | Cloud 失聯不得使 BESS 因 Internet 中斷而立即停機；Edge 應依已下載且未過期 policy 自治。 |

### 3.3 功率夾箝

~~~text
P_final = clamp(P_requested,
                BMS_CCL_DCL,
                PCS_capability,
                grid_contract_limit,
                SOC_reserve,
                thermal_derate,
                ramp_rate,
                local_override)
~~~

系統應同時記錄 requested setpoint、final setpoint、每個限制值、clamp reason、policy/profile version 與 actual read-back。

---

## 四、目標架構

### 4.1 C4 Context

~~~mermaid
flowchart LR
    OPS["Operator／Maintainer\nWeb／PWA"]
    EDGE["Site Edge EMS\n自治、資料、告警、控制"]
    DEV["BMS／PCS／Meter／HVAC／Fire\nMicrogrid Option"]
    CLOUD["Fleet Cloud\n跨站、報表、版本、archive"]
    IDP["Identity Provider\nOIDC／MFA"]
    OPS -->|HTTPS| EDGE
    OPS -->|HTTPS| CLOUD
    EDGE <-->|CAN／Modbus／DI| DEV
    EDGE -->|outbound mTLS| CLOUD
    CLOUD --> IDP
~~~

### 4.2 C4 Container

| Container | 部署 | 責任 |
|---|---|---|
| Protocol Adapter Runtime | Edge | CAN／Modbus／DI decode、quality、allowlisted write |
| Device Profile Registry | Edge＋Cloud | immutable profile、model/firmware compatibility、golden hash |
| Site Controller | Edge | state、interlock、clamp、schedule、lost-link policy |
| MQTT Broker | Edge | internal event bus；state/event/command ack |
| Historian／Event Store | Edge | telemetry、array、alarm、command、audit、outbox |
| Local API／HMI | Edge | local operations、offline visibility、commissioning |
| Fleet API／Sync | Cloud | multi-site ingest、desired policy、reports、release |
| Operations Web/PWA | Cloud／Edge | site/fleet UI、alarm、trend、command、audit |
| Identity／Authorization | Cloud＋Edge cache | OIDC、RBAC、MFA、site scope、offline policy |

### 4.3 部署要求

| ID | 設計要求 |
|---|---|
| EMS-DEP-001 | MVP Edge 應採 Ubuntu LTS、Docker Compose 與 systemd watchdog；不以 K3s 作第一代必要條件。 |
| EMS-DEP-002 | Edge 應具雙 NIC、TPM、工業溫度規格、SSD endurance 資料、硬體 watchdog 與 UPS shutdown 介面。 |
| EMS-DEP-003 | Pilot 應提供 cold spare image/config、備份還原與現場替換 SOP。 |
| EMS-DEP-004 | Edge 對 Cloud 只建立 outbound mTLS 連線；遠端維運須經 bastion／Tailscale、MFA、短時憑證與 audit。 |
| EMS-DEP-005 | Production 是否採 Edge active/standby 由 SLA、RTO/RPO 與現場替換時間決定。 |

---

## 五、OT／IT 網路與資安分區

### 5.1 分區

| Zone | 元件 | 存取規則 |
|---|---|---|
| Zone 0 Safety | BMS、PCS local、EPO、Fire、Relay | 無 Cloud 依賴；hardwire／isolated bus |
| Zone 1 OT | PCS、meter、HVAC、PLC、ATS/DG | 僅指定 adapter 可達；VLAN／firewall allowlist |
| Zone 1.5 Edge DMZ | gateway、controller、broker、historian、HMI | 雙 NIC；禁止任意 routing |
| Zone 2 Site IT | Ops workstation、bastion、update cache | HTTPS、MFA、maintenance window |
| Zone 3 Cloud | Fleet、DB、object store、IdP | tenant isolation、mTLS、no field-bus route |

### 5.2 EMS-SEC 系統要求

| ID | 設計要求 |
|---|---|
| EMS-SEC-001 | Production MQTT broker 禁止 anonymous，client certificate 應綁定 organization/site/gateway 與 topic ACL。 |
| EMS-SEC-002 | Production DB、MQTT、PostgREST 不得直接暴露 public host port。 |
| EMS-SEC-003 | Modbus TCP 僅允許指定 source、destination、port、function code 與 address；RS-485 採隔離、single master 與 bus timeout。 |
| EMS-SEC-004 | CAN 不得橋接一般 LAN；adapter 僅發布 normalized signals 與 allowlisted commands。 |
| EMS-SEC-005 | Web 使用 OIDC Authorization Code + PKCE；Production 啟用 MFA、HttpOnly/Secure/SameSite cookie 與 server-side refresh。 |
| EMS-SEC-006 | 所有產品表應帶 site_id；DB Row-Level Security（RLS）與 service authorization 皆須強制。 |
| EMS-SEC-007 | High-impact command 應支援 step-up authentication、dual approval 與 local physical disable。 |
| EMS-SEC-008 | Release 應產生 SBOM、signature、hash、provenance；部署前驗證 compatibility 與 minimum version。 |

---

## 六、設備與協定

### 6.1 協定選用

| 協定 | 用途 | 設計決策 |
|---|---|---|
| CAN 2.0B／CAN FD | BMS↔PCS、BCU↔Edge | 僅 Edge/local；需 DBC、隔離與 bus-load analysis |
| Modbus RTU | meter、HVAC、I/O | profile＋HIL；single master、timeout、endian 明確 |
| Modbus TCP／SunSpec | PCS、meter、PV、STS | OT VLAN＋address allowlist；SunSpec 優先但不忽略 vendor extension |
| MQTT 5 | Edge event bus、Edge↔Cloud | telemetry QoS0；state/event/ack QoS1；command 不 retained |
| REST／HTTPS | 管理、查詢、batch sync | 不作 field-bus protocol |
| SSE／WebSocket | Browser live state | SSE 優先；不得直連 MQTT/DB |
| OPC UA | SCADA／MES northbound | Pilot 後依案場提供 |
| IEC 104／61850、BACnet | Utility／building integration | 僅合約要求時另立 PRD |

### 6.2 設備介面責任

| 設備 | 讀取 | 允許寫入 | 本地責任 |
|---|---|---|---|
| BMS／BCU | SOC/SOH、cell min/max、T、IMD、CCL/DCL、fault | Base 原則只讀；maintenance setting 另管 | contactor、precharge、fault/EPO |
| PCS | mode、P/Q、V/f、DC/AC、fault、capability | start/stop、P/Q、mode request，經 Site Controller | watchdog、PLL、inner loop、anti-islanding |
| PCC／Revenue Meter | V/I/P/Q/PF/f/energy/demand | 通常唯讀 | calibration／seal |
| HVAC | temperature、fan、compressor、fault | non-safety setpoint／fan | over-temp／smoke local |
| Fire Panel | alarm／trouble／release status | 不 remote reset／release | hardwired trip/release |
| ATS／STS | source、position、ready、fault | Base read-only；Microgrid PRD 定義 | transfer speed、interlock local |

### 6.3 Device Profile Contract

每個 Supported model／firmware 應具 immutable、versioned profile，至少包含：

- vendor、model、firmware range、protocol、connection 與 profile hash；
- register/frame ID、data type、byte/word order、scale、unit、valid range；
- read/write、allowed function code/address、poll group；
- timeout、retry、backoff、stale threshold 與 quality mapping；
- fault bitmap、severity、command precondition、read-back、watchdog、fallback；
- HIL fixture、golden capture、firmware compatibility 與 unsupported behavior。

AI 可協助產生候選 profile，但不得發明 map；未經 HIL 不可標示 Supported。

---

## 七、Canonical Data、品質與時間

### 7.1 Telemetry Envelope

每筆資料至少包含 schema_version、organization_id、site_id、gateway_id、device_id、profile_version、sequence、source_time、acquired_time、ingested_time、quality、signal name、value 與 unit。

### 7.2 品質模型

| Quality | 條件 | 顯示與控制 |
|---|---|---|
| GOOD | profile、range、clock、communication 正常 | 可顯示；可參與 supervisory control |
| UNCERTAIN | clock drift、fallback time、部分欄位缺失 | 顯示警示；按 signal policy 決定 |
| BAD | CRC、parse、range 或 device fault | 不參與 control；保留 evidence |
| STALE | 超過 profile threshold | 顯示 age；control fail closed |
| SUBSTITUTED | manual／algorithm replacement | 顯示來源；預設不進 auto control |

### 7.3 時間同步

| ID | 設計要求 |
|---|---|
| EMS-TIME-001 | Edge 應使用 chrony/NTP 至少兩個 time source，並具 RTC holdover。 |
| EMS-TIME-002 | 有設備時間時保存 source_time；無設備時間時使用 acquired_time 並標 TIME_FALLBACK。 |
| EMS-TIME-003 | Clock offset >100 ms 應告警；>1 s 時依時間排序的控制輸入標 UNCERTAIN。 |
| EMS-TIME-004 | 儲存採 UTC，顯示採 site timezone；DST 與跨時區須列測試。 |
| EMS-TIME-005 | NTP 不得宣稱為 protection-grade；有 sub-ms 需求時另評估 PTP。 |

### 7.4 取樣與保存

| 資料 | Edge | Cloud | 備註 |
|---|---|---|---|
| PCS/PCC/BMS summary | 1 s，至少 90 天 | 1-10 s 或 1 min aggregate，13 個月 | 營運主資料 |
| Full-cell array | 5-10 s＋event burst | aggregate／Parquet bundle | 不採 112×每秒窄列多年 |
| Fault black box | 前後各 30 s、100 ms／設備原生率 | raw bundle，至少保固期 | BMS 為 source of truth |
| Alarm/Event/Command/Audit | append-only，Edge 至少 12 個月 | 3-7 年待合約 | ACK 不等於 clear |
| Aggregate | 1 min／15 min／1 h | 13-36 個月 | tariff／demand／report |

若業主要求 full-cell 1 s 保存 12 個月，應先完成容量、壓縮、查詢、backup 與 restore benchmark。

---

## 八、告警、事件與命令閉環

### 8.1 Alarm State

~~~text
NORMAL -> PENDING -> ACTIVE -> CLEARED
                       |
                       +-> ACKED
ACTIVE/ACKED -> SHELVED (有期限、理由、actor、audit)
~~~

| ID | 設計要求 |
|---|---|
| EMS-ALM-001 | Alarm rule 應版本化 threshold、delay、hysteresis、severity、owner 與 runbook。 |
| EMS-ALM-002 | ACK 不得修改 device fault，也不得代替 reset。 |
| EMS-ALM-003 | Notification 應採 durable outbox、retry、dead-letter、delivery status 與 secondary channel。 |
| EMS-ALM-004 | Telegram 可作通知通道，但不得作唯一稽核或唯一事件證據。 |
| EMS-ALM-005 | 應具 dedupe／suppression／storm control，避免同一根因產生多層告警洪水。 |

### 8.2 Command Lifecycle

~~~text
CREATED -> AUTHORIZED -> VALIDATED -> DISPATCHED -> ACKED -> CONFIRMED
                         |              |             |
                         +-> REJECTED   +-> FAILED    +-> UNKNOWN -> RECONCILED
                         +-> EXPIRED
~~~

命令至少包含 command_id、site_id、target、type、desired、issued_by、reason、issued_at、expires_at、idempotency_key、policy_version 與 expected_state_version。

| ID | 設計要求 |
|---|---|
| EMS-CMD-001 | Product API 應驗證 AuthN、AuthZ、site scope、MFA/approval 與 expiry。 |
| EMS-CMD-002 | Site Controller 應驗證 freshness、state、interlock、BMS/PCS limits、local override 與 ramp。 |
| EMS-CMD-003 | Adapter 只能執行 profile allowlist write，完成後須 read-back。 |
| EMS-CMD-004 | Actual state 在 tolerance 內才可標 CONFIRMED；API 200 或 write ACK 不足。 |
| EMS-CMD-005 | Timeout 應進 reconciliation；只有已證明 idempotent 的命令可自動 retry。 |
| EMS-CMD-006 | 每一步應 append audit，記錄 reject／clamp reason 與 requested/final setpoint。 |
| EMS-CMD-007 | 相同 idempotency key 不得造成第二次 physical action。 |

---

## 九、Web／PWA 與 App

### 9.1 資訊架構

| 模組 | MVP | Pilot | Production |
|---|---|---|---|
| OIDC／site switch | 基本 | MFA／role | federation／audit |
| Fleet／site overview | 單站 | 多站 | portfolio KPI |
| BESS single-line／asset topology | read | state-linked | maintenance history |
| P/Q/SOC/SOH/limits/mode | 必須 | 必須 | 必須 |
| Trend／query／export | 必須 | compare／aggregate | scheduled report |
| Alarm console | active／ack | suppress／escalate | SLA／report |
| Command center | 無寫入 | controlled P/Q/start-stop | dual approval |
| Schedule／demand | 顯示 | edit/simulate/deploy | optimization |
| Device／profile／connection | 必須 | commissioning | fleet bulk |
| Audit／black box | query | export | compliance archive |
| OTA／config | 無 | canary | rings／rollback |

### 9.2 Browser Requirements

- CRUD、query、command 採 HTTPS REST `/api/v1`。
- Alarm、command 與 site summary 採 Server-Sent Events（SSE）優先；需要雙向協作才使用 WebSocket。
- Cell array 不作高頻全量 push；API 應提供 downsample、pagination 與 event bundle。
- Browser 不得直連 MQTT、PostgREST、TimescaleDB、CAN 或 Modbus。

### 9.3 App 決策

MVP／Pilot 採 responsive PWA，支援 notification deep link、site summary、ACK、QR 與 work note。手機介面不得提供 contactor／fire reset／STS switching，也不得提供無二次確認的 high-impact start-stop。

只有在 BLE/NFC commissioning、MDM、reliable push、background sync、camera inventory 或 fully offline work order 被驗證後，才建立原生 App PRD。

---

## 十、API、MQTT 與資料模型

### 10.1 Product API 基線

~~~text
GET  /api/v1/organizations
GET  /api/v1/sites
GET  /api/v1/sites/{site_id}/summary
GET  /api/v1/sites/{site_id}/assets
GET  /api/v1/assets/{asset_id}/measurements
GET  /api/v1/sites/{site_id}/events
GET  /api/v1/sites/{site_id}/alarms
POST /api/v1/alarms/{alarm_id}/ack
POST /api/v1/alarms/{alarm_id}/shelve
GET  /api/v1/sites/{site_id}/commands
POST /api/v1/sites/{site_id}/commands
POST /api/v1/commands/{command_id}/approve
GET  /api/v1/sites/{site_id}/schedules
POST /api/v1/schedules/{schedule_id}/deploy
GET  /api/v1/device-profiles
POST /api/v1/sites/{site_id}/config-deployments
GET  /api/v1/sites/{site_id}/audit-events
GET  /api/v1/stream
~~~

API 應採 OpenAPI 3.1，逐 endpoint 定義 cursor pagination、idempotency、ETag／expected version、error code、rate limit、actor/site scope 與 retry。

### 10.2 MQTT 5 Topic 基線

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

- High-rate telemetry 可用 QoS0。
- State、event 與 ack 使用 QoS1、persistent session、expiry 與 dedupe。
- Command 使用 QoS1、expiry 與 idempotency，禁止 retained。
- Availability 與 current config 可 retained。

### 10.3 核心資料實體

organizations、sites、assets、gateways、device_profiles、device_connections、signal_definitions、signal_measurements、events、alarm_instances、commands、command_attempts、schedules、config_deployments 與 audit_events 均應具 immutable/version lineage、site scope 與 retention policy。

---

## 十一、Offline、Recovery 與 OTA

### 11.1 WAN 狀態

| 狀態 | Telemetry | Control | User | Sync |
|---|---|---|---|---|
| ONLINE | local＋Cloud | 執行核准 intent | local／Cloud UI | continuous |
| DEGRADED | local first | 只執行未過期 local policy | local UI | retry／batch |
| OFFLINE | local durable | local policy 或 profile ramp-to-zero | local ops | spool |
| RECOVERING | local | 先 reconcile actual state | 顯示 unsynced | ordered replay／dedupe |

復線時以 actual device state 為權威，不得用舊 desired state 覆蓋現場。過期命令丟棄；telemetry/event 補傳保留 acquired_time。

### 11.2 OTA／Configuration

| ID | 設計要求 |
|---|---|
| EMS-OTA-001 | Artifact／manifest 應簽章，Edge 驗證 hash、signature、compatibility 與 minimum version。 |
| EMS-OTA-002 | Release 應經 dev、internal、pilot、production rings 與 health observation window。 |
| EMS-OTA-003 | Edge 應保留 previous image/config，health gate 失敗時自動 rollback。 |
| EMS-OTA-004 | DB migration 應採 expand／migrate／contract。 |
| EMS-OTA-005 | Profile/config 應 immutable，deployment 只切 active pointer。 |
| EMS-OTA-006 | Offline 時不得執行半套 update；第三方 BMS/PCS firmware 依 vendor process。 |

---

## 十二、非功能需求

### 12.1 Pilot NFR Gate

| ID | 指標 | 目標 | 驗證 |
|---|---|---:|---|
| EMS-NFR-001 | adapter->broker p99 | <=250 ms，不含 poll interval | HIL timestamp |
| EMS-NFR-002 | broker->historian p99 | <=1 s | acquired/ingested diff |
| EMS-NFR-003 | accepted->write attempt p99 | <=500 ms | command trace |
| EMS-NFR-004 | read-back confirmation | <=2 polling cycles | HIL |
| EMS-NFR-005 | supervisory loop | 1 s；deadline miss <0.1% | 72 h soak |
| EMS-NFR-006 | WAN loss | 72 h local operation；no command replay | partition test |
| EMS-NFR-007 | Offline buffer | >=7 日設計負載；disk 80% 前 alarm | fill/capacity test |
| EMS-NFR-008 | Edge availability | 99.9%／月 | Pilot SLO |
| EMS-NFR-009 | Cloud API operational read p99 | <500 ms | load test |
| EMS-NFR-010 | Site scale | >=5,000 points/s、200 logical devices | replay benchmark |
| EMS-NFR-011 | Control audit | 100% terminal 或 UNKNOWN＋reconciliation | invariant query |
| EMS-NFR-012 | Safety loop | 不屬 EMS | boundary review |

Production RTO/RPO、HA 與站點規模須依 Pilot benchmark 與商務 SLA 再凍結。

### 12.2 Observability

系統應監測 adapter poll success、timeout、CRC/parse、RTT、stale age、bus load、points/s、quality ratio、clock offset、spool depth、command latency、clamp count、alarm delivery、Edge CPU/RAM/disk/UPS、Cloud ingest/API、certificate expiry 與 OTA drift。

Log 應使用 structured JSON，包含 trace_id、request_id、site_id、device_id；command/event 另含 command_id/event_id。工程觀測採 Prometheus、OpenTelemetry、Loki／Tempo 與 Grafana；客戶操作介面不得以 Grafana 取代產品 Web。

---

## 十三、失聯與 Fail-safe

| 失聯 | 權威反應 | 禁止行為 |
|---|---|---|
| BMS↔PCS | BMS/PCS 本地 derate、stop、trip；依 DBC/watchdog | 等 Cloud 決定 |
| Edge↔PCS | PCS watchdog；Edge hold 或 ramp-to-zero，產生 alarm | 無條件把 cell 標 Fault 或直接開 contactor |
| Cloud↔Edge | Edge 繼續 local policy、拒絕新 remote command、持久化補傳 | 因 Internet 斷線立即停機 |
| NTP loss | RTC holdover、quality 降級、time alarm | 偽造 source_time |
| Disk pressure | retention policy、backpressure、alarm、保留 event/audit | 靜默刪除未同步 alarm/command |
| Process restart | durable state、reconcile actual device state | 假設先前 write 已成功 |

---

## 十四、驗證策略

| 層級 | 驗證內容 | 頻率／Gate |
|---|---|---|
| Unit／Property | codec、endian、quality、clamp、state、idempotency | Every PR |
| Contract | OpenAPI、AsyncAPI、JSON Schema、profile、MQTT ACL | Every PR |
| SIL | BMS/PCS/meter/HVAC/ATS、fault、clock replay | PR／nightly |
| Integration | broker、DB、BFF、sync、RLS、outbox | CI／nightly |
| HIL | 每一 model/firmware、read/write、timeout、watchdog、read-back | Release Gate |
| System | WAN loss、restart、disk full、NTP drift、DB/broker、OTA | Milestone |
| Security | SAST、SCA、SBOM、secret、ports、ACL、authz、pentest | CI／Release |
| Field | 30-day SLO、alarm、command、manual workflow | Pilot Gate |

### 14.1 必測不變式

1. 無 GOOD／fresh limit／合法 state 時，command 不 dispatch。
2. Cloud／Web／AI 不越過 BMS／PCS／local interlock。
3. Expired command 不執行；reconnect 不重放 retained command。
4. 相同 idempotency key 不造成第二次 physical action。
5. CONFIRMED 具有 read-back；write ACK 不足。
6. 每個 command 有 terminal status 或 UNKNOWN＋reconciliation。
7. Tenant A 無法看見或控制 Tenant B。
8. WAN／Cloud／BFF／Grafana 故障不影響 hardware protection 與 local basic operation。
9. Fire／EPO／STS speed 與安全不依賴 EMS。

### 14.2 研發與案場驗證邊界

- EMS Unit／Contract／SIL／HIL／System／Security test 屬自研產品驗證。
- BMS EVT／DVT／PV 與 EMS Software RC 共同形成整機整合輸入。
- FAT 驗證整櫃組態、通訊、故障注入與 as-built；SAT 驗證案場 SLD、interlock、manual fallback、network partition 與 Pilot SLO。
- 72 h 測試不得只以「不中斷」判定，應同時檢查 deadline miss、data gap、spool、alarm delivery、command terminal state、CPU/RAM/disk 與 recovery。

---

## 十五、開發時程與 PRD 拆分

### 15.1 團隊

Architect/Product 1、Edge/OT 2、Backend/Data 2、Frontend/PWA 1、QA/HIL 1、DevOps/SRE/Security 0.5-1。7-8 FTE 可在 12 個月形成 conditional Software RC；2-3 人則合理工期為 18-24 個月。

### 15.2 Phase 0：Week 0-4

- 凍結 authority、state、失聯與 remote command scope。
- 完成 BMS／PCS／meter／HVAC／fire／ATS interface matrix。
- 發布 telemetry／event／command JSON Schema／AsyncAPI v1。
- 完成 Edge BOM、VLAN、storage、HIL 與 safety case。

Exit：無正式 map／HIL 的型號不得列 Supported。

### 15.3 MVP：Week 5-16

- Device Profile SDK、golden replay、tenant/site/asset migration。
- BMS／PCS／meter read-only adapters。
- Canonical ingest、compression、mTLS broker、local historian。
- Site／device／trend／alarm Web 與 durable outbox。
- SIL/HIL、network partition 與 72 h soak。

Exit：read-only real hardware、offline collection、quality/time trace、Web alarm；不得提供 remote setpoint/start-stop。

### 15.4 Pilot：Week 17-32

- Command store、state、idempotency、read-back 與 Site Controller。
- PCS P/Q/start-stop、HVAC adapter、schedule/demand dry-run。
- Multi-site sync、Redis、OIDC/MFA、Web approval、signed config rollback。
- 單站 30 日 field evidence。

Exit：限定範圍 command 可 trace/read-back；WAN loss 不破壞 local；remote control 可 local-disable。

### 15.5 Production Gate：Week 33-52

- Capacity、30/90-day sizing、HA／backup／DR drill。
- IEC 62443 mapping、SBOM、pentest、findings closure。
- OTA rings、A/B rollback、multi-site report／authz。
- Commissioning、support、training 與 Release Candidate traceability。

正式整機 Field Release 仍受 BMS／PCS／整櫃 M18-24 Gate 約束。

### 15.6 PRD Family

| ID | 主題 | 核心交付 |
|---|---|---|
| EMS-01 | Device Profile／Adapter SDK | profile、CAN/Modbus、golden/HIL |
| EMS-02 | Organization／Site／Asset | tenant/site/RLS/API |
| EMS-03 | Edge Runtime／Store-and-forward | broker/historian/sync/offline |
| EMS-04 | Alarm／Event／Notification | rule/state/outbox/escalation |
| EMS-05 | Supervisory Control／Command | lifecycle/arbiter/clamp/read-back |
| EMS-06 | Operations Web／PWA | operations console |
| EMS-07 | Fleet Cloud／Site Sync | multi-site ingest/fleet API |
| EMS-08 | Config／OTA Release | signed artifact/rings/rollback |
| EMS-09 | Security／Observability／DR | zones/SLO/DR/pentest |
| EMS-10 | Tariff／Demand／Optimization | tariff/15-min demand/schedule |

正式 PRD 編號由 `doc/prd/README.md` 分配，不在本規格中直接占用 0007-0016。

---

## 十六、待核項目

1. Pilot PCS/BMS model、firmware、map、DBC 與 HIL sample。
2. 是否需要 island、black-start、DG/PV、ATS/STS；L1 owner 與 open／closed transition。
3. Cloud loss 時 last schedule 有效期、ramp-to-zero 與 local optimization policy。
4. Remote command scope：P/Q、start-stop、mode、alarm reset 分別定義。
5. BMS warranty 對 full-cell logging 的 sampling、retention 與 export。
6. Multi-tenant business model 與 EPC／maintainer cross-org delegation。
7. Pilot／Production SLA、RTO/RPO、retention 與 data residency。
8. IdP、MFA、group claim 與 Edge offline login。
9. Edge IPC、storage、CAN、RS-485、switch、firewall 與 UPS benchmark。
10. OPC UA、IEC 104/61850、BACnet 與 utility dispatch 是否為合約必要項。

---

## 十七、設計凍結與交付

EMS 發布基線至少包含：

- 核准 PRD、ADR、C4、data flow、network zone、threat model 與 ICD。
- Versioned Device Profile、golden capture、supported model/firmware matrix。
- OpenAPI、AsyncAPI、JSON Schema、DB migration 與 topic ACL。
- Edge image、container manifest、config hash、SBOM、signature 與 rollback package。
- Unit／SIL／HIL／Security／System／Pilot report 與 requirement traceability。
- Commissioning、backup/restore、offline、lost-link、alarm runbook、RMA 與 service SOP。

本 v0.1 是 EMS 設計與實作基線。PCS/BMS 型號、remote control、Microgrid、retention、SLA 與法規條件未完成前，不得轉為對外承諾。
