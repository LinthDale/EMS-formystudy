# 100 kWh 級電池儲能系統之電池管理／能源管理自研產品 Master Program Plan

版本：v0.1  
日期：2026-09-03  
文件狀態：Program Baseline v0.1（T／H 項仍待關閉）  
適用對象：產品、系統、電氣、機構、熱流、消防、BMS、EMS、驗證、採購、製造與案場整合團隊

---

## 摘要

本計畫建立 100 kWh 級電池儲能系統（Battery Energy Storage System, BESS）的產品開發基線。第一代參考產品採 1P112S、50 kW、0.5C，電池管理系統（Battery Management System, BMS）與能源管理系統（Energy Management System, EMS）為自研核心；電芯、功率轉換系統（Power Conversion System, PCS）、高壓元件、熱管理、消防、工業電腦與場域設備採外購整合。100 kW／1C 及微電網功能列為衍生型，不與第一代同時凍結。

開發以 24 個月、240-335 person-month、峰值 18-24 FTE 規劃。EMS 可於第 12 個月形成條件式軟體發行候選版本，但整機 Field Release 須完成 BMS、PCS、整櫃、認證與 Pilot 證據，目標為第 18-24 個月。Plan 級經濟成本為 NT$216.1M，屬未稅 P3／ROM（Rough Order of Magnitude）規劃值，不是一次性現金請款，也不含土地、台電外線、場址 EPC、DG 與 PV。

---

## 一、文件定位

### 1.1 目的

本文件用於：

1. 凍結第一代產品與衍生型的責任邊界。
2. 建立 BMS、EMS、PCS、BESS 與微電網控制層的共同架構。
3. 定義 PRD 組合、依賴、開發時程、資源、驗證 Gate 與經費模型。
4. 將型號選商由「規格表比對」提升為 RFQ、ICD、樣品、HIL 與 DVP 證據鏈。
5. 避免把研發驗證 EVT／DVT／PV 與客戶整櫃驗收 FAT／SAT 混為同一件事。

### 1.2 規範用語

- 「應」：進入對應 Gate 前必須滿足。
- 「基線」：目前核准的設計與規劃起點，變更須有 ADR 或變更單。
- 「條件式」：必要輸入尚未關閉，不得轉為對客承諾。
- 「待核」：須由業主、供應商、法規單位或正式設計輸入確認。
- 「Supported」：指定型號、韌體版本與介面已完成 profile、golden capture 及 HIL 驗證。

### 1.3 需求狀態

| 狀態 | 定義 | 設計處置 |
|---|---|---|
| A - Approved | 已有受控輸入與決策 | 可進設計凍結 |
| P - Preliminary | 可供分析與原型實作 | Gate 前須完成證據 |
| T - To be confirmed | 缺外部輸入或跨系統決策 | 不得作為量產放行依據 |
| H - Hold | 存在硬性 Gate 未關閉 | 不得釋出採購或設計凍結 |

---

## 二、產品基線與衍生型

### 2.1 第一代參考產品

| 項目 | 基線 | 狀態 |
|---|---|---|
| 電芯化學 | 314 Ah LFP | P；須取得受控最新版規格 |
| 組態 | 1P112S，7 個 1P16S 模組 | A |
| 標稱電壓／能量 | 358.4 V／112.5 kWh | P |
| 設計電壓窗 | 280-408.8 VDC | P；以單體保護優先 |
| 基準電流 | 157 A（0.5C） | A |
| 功率定位 | 50 kW-class | A |
| BMS | 自研 BMU ×7、BCU ×1、高壓控制 | A |
| EMS | 自研 Edge、Device Profile、Control、Web/PWA、Fleet | A |
| PCS | 外購；完整直流工作窗與 ICD 未關閉 | H |
| Microgrid | 選配，不屬 Base BESS | A |

112S／157 A 在 280 V 時的直流功率上限為 44.0 kW；達到 50 kW 至少需要約 318.5 V。對外文件應稱 50 kW-class，並將 survival、normal dispatch 與 full-power 三個工作窗口分開定義。

### 2.2 衍生型管理

| 衍生型 | 立案條件 | 增量工作 |
|---|---|---|
| 96S 低壓版 | 取得可覆蓋 240-350.4 V 的 PCS 證據 | PCS、預充、電流與功率窗口重算 |
| 100 kW／1C | 第一代完成 DVT／Design Freeze 後另開 SRR/PDR | 熱平衡、匯流排、接觸器、熔斷器、HVAC、PCS、認證差異；工期另增約 6-9 個月 |
| Microgrid Open-transition | 場址 SLD、負載分級、接地、中性點、DG/PV/PCS 資料完成 | L1 PLC、PCC 保護、ATS、I/O、HIL、FAT、SAT |
| Closed-transition／Seamless | 電力公司與 AHJ 核准；同步與保護研究完成 | 25／32、同步盤、STS、保護協調與獨立 DVP |

### 2.3 24 張微電網範例的使用邊界

| 可借用 | 不可沿用／須重算 |
|---|---|
| L0-L3 分層、open-transition baseline、狀態機方法、PDR/CDR/HIL/FAT/SAT、負載分級 | 58/60 kWh、25/30 kW、PV/DG/油箱、220 V 3φ3W、SOC 20/80/95%、5 分鐘、72 小時等數值 |
| local fail-safe、手動 fallback、故障注入與可追溯 pass/fail | 原案 ATS 接法、DG start/stop、GFM/GFL 次序與燃料模型 |
| no-break、short-break、interruptible、sheddable 分流 | 將「5 分鐘內全黑切換」套用所有避難所負載 |

---

## 三、系統分層與責任邊界

### 3.1 L0-L3 控制架構

~~~mermaid
flowchart TB
    L3["L3 Fleet／Web／PWA\n報表、組態、排程意圖、稽核"]
    L2["L2 EMS Edge\n站端自治、資料、告警、P/Q 仲裁、離線運作"]
    L1["L1 Local Control\nPCS controller；Microgrid 選配 PLC／relay／ATS sequence"]
    L0["L0 Device／Protection\nBMS、PCS、relay、fuse、EPO、fire、switchgear"]
    L3 -->|"signed policy／intent"| L2
    L2 -->|"validated mode／setpoint request"| L1
    L1 -->|"bounded actuation"| L0
    L0 -->|"actual state／limits／events"| L1
    L1 -->|"read-back／state"| L2
    L2 -->|"telemetry／audit"| L3
~~~

### 3.2 Authority Matrix

| 層級 | 權威 | 可執行事項 | 上層可否覆寫 |
|---|---|---|---|
| L0 人身與硬體保護 | EPO、消防、熔斷器、保護電驛 | 立即切斷／跳脫 | 不可 |
| L0/L1 電池與功率保護 | BMS、PCS local controller | OV/UV/OT/OC、絕緣、CCL/DCL、V/I 內環 | 不可 |
| L1 微電網序列 | PLC／microgrid controller | ATS、DG、load shedding、mode sequence | EMS 只請求模式 |
| L2 站端監督 | EMS Edge／Site Controller | P/Q、排程、需量、SOC reserve、ramp、失聯策略 | 可被本地限制拒絕 |
| L3 Fleet／Web | Cloud service／使用者 | policy、schedule、ACK、報表 | Edge 可拒絕、過期、夾箝 |

### 3.3 功率命令夾箝

~~~text
P_final = clamp(
  P_requested,
  BMS_CCL_DCL,
  PCS_capability,
  site_contract_limit,
  SOC_reserve_policy,
  thermal_derate,
  ramp_rate,
  local_override
)
~~~

BMS 是唯一電池能力邊界發布者；EMS 只能收緊，不能放寬。資料缺失、過期或 quality 不足時，Edge 應依型號 profile 拒絕、保持受限穩態或 ramp-to-zero，不得猜值。

### 3.4 四套狀態機

以下狀態機互相關聯，但不得合成一張圖：

1. Microgrid System State：Grid-connected、Islanding、ESS-forming、DG-forming、Reconnect、Degraded、Fault Lockout。
2. PCS Mode State：Stopped、Precharge-ready、Grid-following、Grid-forming、Fault。
3. BMS High-voltage State：Off、Self-test、Insulation Check、Precharge、Run、Controlled Open、Lockout。
4. EMS Dispatch State：Observe、Local Auto、Remote Scheduled、Hold、Ramp-to-zero、Recovering。

任何跨狀態轉移須在 Interface Control Document（ICD）列出 request、permissive、timeout、read-back、fallback 與 owner。

---

## 四、電力與微電網架構基線

### 4.1 Base BESS 單線責任

~~~text
Battery Modules -> BMU/BCU -> Fuse/MSD/Contactors/Precharge -> DC Bus -> PCS -> AC Breaker -> PCC/Load Bus
                         |                                  |
                         +-- hardwired Permit/EPO ---------+
~~~

- BMS 控制主正、主負與預充，並讀取接觸器輔助接點、HVIL、IMD 與 pack／DC-link 電壓。
- PCS 控制 DC/AC 內環、防孤島、過流與模式切換；不得超越 BMS CCL/DCL。
- EMS 不直接驅動接觸器，也不承擔 protection-grade trip。
- 預充元件須待 PCS 提供 DC-link capacitance、inrush、target ratio、zero-current、reverse feed 與 retry duty 後凍結。

### 4.2 Microgrid 選配

~~~text
Grid/PCC breaker --+
ESS PCS breaker ---+--> Critical AC Bus --> Tier 1/2 feeders
DG breaker --------+          |
PV breaker --------+          +--> Tier 3 sheddable feeders
                              +--> Online UPS/DC no-break bus for Tier 0/1 controls
~~~

- 第一代採 break-before-make／open-transition。
- ATS、breaker、DG start、PCS GFM/GFL 與 load shedding 的 deterministic sequence 由 L1 PLC／microgrid controller 執行。
- Closed-transition 必須另增 sync-check、25、32、utility approval 與 DVP。
- 3φ3W 孤島的接地與中性點、PCS 限流下保護選擇性、PV island compatibility 為 PDR 必關項。

### 4.3 服務分級

| 等級 | 典型負載 | 供電目標 |
|---|---|---|
| Tier 0 No-break | EPO／消防盤、BMS/PCS/PLC 控制電源、通訊、必要照明 | DC 或 online UPS；不得依賴 BESS 預充完成 |
| Tier 1 Short-break | 醫療／避難關鍵通訊、門禁、必要泵浦控制 | UPS bridge 至 ESS/DG 恢復 |
| Tier 2 Essential | 主要避難照明、插座、通風與必要生活負載 | 定義秒至分鐘恢復時間 |
| Tier 3 Interruptible | 非關鍵空調、一般插座、可延後負載 | 最多 5 分鐘或依 load-shed policy |

「5 分鐘內切換」只能作 Tier 3／部分 Tier 2 的恢復上限，不能作所有避難所負載的服務目標。

---

## 五、網路、通訊與資料架構

### 5.1 實體與邏輯網路

| 區域 | 元件 | 主要連線 | 原則 |
|---|---|---|---|
| Zone 0 Safety | BMS、PCS、EPO、Fire、Relay | isolated CAN、hardwire | 不依賴 LAN／Cloud |
| Zone 1 OT | PCS、meter、HVAC、PLC、ATS/DG | CAN、RS-485、OT Ethernet VLAN | allowlist、single-master、禁止直接上網 |
| Zone 1.5 Edge DMZ | protocol gateway、Site Controller、broker、historian、local HMI | dual NIC／firewall | 所有 field bus 經 adapter |
| Zone 2 Site IT | 維運工作站、bastion、update cache | HTTPS／SSH via controlled path | MFA、短時憑證、audit |
| Zone 3 Cloud | Fleet API、DB、object storage、IdP | outbound mTLS from Edge | 不直通 field bus |

### 5.2 協定基線

| 介面 | 協定 | 設計決策 |
|---|---|---|
| BMU↔BCU | 隔離 daisy-chain／AFE transport | CRC、序號、逾時、節點定位 |
| BMS↔PCS | 專用 isolated CAN 2.0B；NC Permit/EPO hardwire | 100 ms class limits／state；DBC 受控 |
| BCU↔EMS Edge | 第二路 isolated CAN 優先 | BCU Ethernet 需另做 threat model 與 WCET 證據 |
| PCS／meter／HVAC | Modbus TCP、SunSpec、Modbus RTU | OT VLAN／address allowlist／profile＋HIL |
| Edge internal／Cloud | MQTT 5、HTTPS REST、SSE | mTLS、topic ACL、expiry、idempotency |
| SCADA northbound | OPC UA；IEC 104/61850 按合約 | 不列 Base 必須項 |

### 5.3 資料分層

- BCU NVM：安全關鍵故障摘要、參數版本、累積量與 reset reason。
- Edge historian：站端 1 s summary、全 cell versioned array、告警、命令與 audit；alarm/event/command 至少 12 個月。
- Edge outbox：WAN 中斷至少 7 天負載，disk 80% 前告警。
- Cloud archive：摘要 13-36 個月；alarm/event/audit 3-7 年由合約與法規凍結。
- Black box：故障前後各 30 s、100 ms 或設備原生率；BMS 為 warranty source of truth。

---

## 六、PRD 架構與依賴

### 6.1 系統 PRD Family

| ID | 主題 | 主要輸出 |
|---|---|---|
| SYS-01 | Program baseline／variants／requirements | 產品基線、成功指標、範圍 |
| SYS-02 | Safety goals／FSC／TSC／Fault Matrix | hazard、safe state、diagnostic coverage |
| SYS-03 | Electrical／HV／thermal／fire／mechanical | SLD、short-circuit、heat balance、消防介面 |
| SYS-04 | Interface Control Document | signal、state、timeout、read-back、fallback |
| SYS-05 | Verification／DVP／traceability | requirement-test-evidence matrix |
| SYS-06 | Manufacturing／quality／field service | DFM/DFT、EOL、calibration、RMA、service |

### 6.2 BMS PRD Family

| ID | 主題 | 主要輸出 |
|---|---|---|
| BMS-01 | System／Safety requirements | BMU/BCU/HV scope、safe state |
| BMS-02 | BMU hardware／AFE／harness | 16S measurement、open-wire、balance、thermal |
| BMS-03 | BCU／HV box／power tree | current/voltage/IMD、contactor、24 V、black-start decision |
| BMS-04 | Firmware／Boot／Diagnostics | scheduler、watchdog、NVM、secure boot、service update |
| BMS-05 | SOC／SOH／SOP／CCL-DCL | estimation、calibration、derate、uncertainty |
| BMS-06 | DVP／Manufacturing／Service | 112ch HIL、EVT/DVT/PV、ICT/FCT/EOL、RMA |

### 6.3 EMS PRD Family

正式編號由 `doc/prd/README.md` 分配；以下暫以功能編號管理，避免與既有 PRD-0001 至 PRD-0006 衝突。

| ID | 主題 | 依賴 | 主要輸出 |
|---|---|---|---|
| EMS-01 | Device Profile／Adapter SDK | vendor map、HIL | profile schema、Modbus/CAN adapters、golden replay |
| EMS-02 | Organization／Site／Asset | migration governance | tenant、site、asset topology、RLS |
| EMS-03 | Edge Runtime／Store-and-forward | EMS-01/02 | broker、historian、offline、sync |
| EMS-04 | Alarm／Event／Notification | EMS-02/03 | rule state、outbox、escalation、runbook |
| EMS-05 | Supervisory Control／Command | SYS-04、HIL | lifecycle、arbiter、clamp、read-back |
| EMS-06 | Operations Web／PWA | EMS-02/04/05 | single-line、trend、alarm、command、audit |
| EMS-07 | Fleet Cloud／Site Sync | EMS-02/03 | multi-site ingest、fleet API、reports |
| EMS-08 | Config／OTA Release | Edge release | signed artifact、rings、rollback |
| EMS-09 | Security／Observability／DR | all | zones、OIDC、SBOM、SLO、backup／restore、pentest |
| EMS-10 | Tariff／Demand／Optimization | clean data＋control | schedule、15-min demand、optimizer dry-run |

### 6.4 依賴關係

~~~text
SYS-01/02/03 -> SYS-04 ICD -> BMS-01..05 and EMS-01..05
BMS/PCS HIL + SYS-04 -> EMS-05 Control
EMS-01 + EMS-02 -> EMS-03 -> EMS-04 and EMS-07
EMS-04 + EMS-05 + EMS-07 -> EMS-06 Web/PWA
EMS-03 + release pipeline -> EMS-08 OTA
All -> EMS-09 Production Gate
Clean data + bounded command -> EMS-10 Optimization
~~~

---

## 七、24 個月開發時程與 Gate

### 7.1 整合時程

| 期間 | BMS | EMS | BESS／PCS | 主要 Gate |
|---|---|---|---|---|
| M0-M2 | AFE/MCU PoC、Safety concept | architecture、ICD、simulator | PCS RFQ、SLD、thermal/short inputs | G0 SRR／G1 Feasibility |
| M2-M5 | Alpha schematic／firmware start | profile SDK、tenant/site、read-only adapters | PCS sample decision、HV concept | G2 PDR／G3 CDR |
| M5-M9 | 112S HIL、Alpha、EVT | real-hardware MVP、historian、alarm、offline | precharge/HV plant、P0/P1 integration | G4 EVT |
| M9-M13 | Beta、diagnostics、algorithm calibration | command store、Site Controller、P/Q controlled HIL | 50 kW P1 cabinet、fault injection | G5 P1／TRR |
| M13-M18 | DVT、EMC/environment/HV、Design Freeze | multi-site、MFA、OTA、security/DR | DVT units、cert test、FAT design | G6 DVT／DF、G7 PV readiness |
| M18-M24 | PV/PVT、production test、service | Software RC integration、field SLO | rolling Pilot 1＋4、SAT、30-90 d observation | G8 Pilot／G9 Field Release |

### 7.2 四階段架構計畫

| 階段 | 進入條件 | 主要輸出 | 退出門檻 |
|---|---|---|---|
| 1. 需求凍結／PDR | Reference product、cell input、初步 PCS envelope、場景與 load tier | SRS、C4、SLD、authority matrix、Safety Goals、risk、RFQ | 所有 safety owner 明確；無未標示的 50/100 kW 承諾 |
| 2. ICD 與控制設計／CDR | PDR 核准；PCS/BMS/protection 資料可用 | ICD、四套 state machine、timeout/fallback、precharge、fault matrix、HIL model | 每個轉移具 permissive、owner、read-back 與 safe fallback |
| 3. HIL／EVT/DVT／FAT | Alpha/Beta 硬體、adapter profile、測試治具完成 | 112S HIL、Co-HIL、fault injection、thermal/EMC/HV、整櫃 FAT | requirement-test-evidence trace 完整；重大偏差關閉或核准 |
| 4. SAT／Pilot／72h | cert readiness、Site SLD、method statement、rollback/manual SOP | site interlock、通信、black-start（若選配）、30-90 d SLO、72h service model/test | 實測與模型一致；RTO/RPO/SLO、RMA、service、as-built 完成 |

### 7.3 Gate 定義

| Gate | 時點 | 必要證據 | 可釋出 |
|---|---|---|---|
| G0 SRR | M0-M1 | 112S/50 kW、BESS/microgrid SKU、RACI、cost owner | EVM、test cells、RFQ |
| G1 Feasibility | M1-M3 | 兩家 PCS envelope、GFL、black-start／control power 決策 | PoC、lab reservation |
| G2 PDR | M3-M5 | SLD、Safety Goals、thermal/short model、EMS I/O | Alpha、112ch HIL |
| G3 CDR | M5-M7 | schematic、ICD、state／fault matrix、test plan | Alpha build |
| G4 EVT | M7-M10 | 112S/56 NTC HIL、Alpha、open-wire/watchdog/precharge | Beta、P1 long-lead |
| G5 P1／TRR | M9-M13 | 50 kW cabinet、PCS stop/read-back、aux interfaces | DVT units |
| G6 DVT／DF | M13-M18 | thermal、EMC、HV、IMD、fault、control HIL、AVL-1 | PV／cert／Pilot wave 1 |
| G7 PV readiness | M16-M21 | PVT、traceability、FAT、cert readiness | Site deployment |
| G8 Pilot／SAT | M18-M24 | 先 1 台、field evidence、RMA/service | rolling 4 units |
| G9 Field Release | Pilot 30-90 日後 | SLO、FPY、RMA、AVL-2、as-built、training | Production release |

---

## 八、人力與治理

### 8.1 資源基線

| 團隊 | 建議配置 |
|---|---:|
| System Architect／Product | 1-2 |
| BMS HW／HV／FW／Algorithm | 8-11 |
| EMS Edge／Backend／Frontend／SRE | 6-8 |
| Validation／HIL | 3-4 |
| Safety／Compliance／Cyber | 2-3＋顧問 |
| Mechanical／Thermal／Harness | 2 |
| Sourcing／SQE／NPI | 2-3 |
| Field／Service | 1-2 |
| Microgrid protection/control（選配） | 1-2 |

整體以 240-335 person-month、峰值 18-24 FTE 規劃。BMS 核心 12-15 FTE；EMS 7-8 FTE 可在 12 個月形成 Software RC。若 EMS 僅 2-3 人，合理工期為 18-24 個月。

### 8.2 決策與變更

- PRD 先於實作，Approved 後的重大介面與安全變更以 Architecture Decision Record（ADR）管理。
- Gate owner 不得同時作唯一驗證人；Safety、Validation、Commercial 至少一方獨立簽核。
- 需求、ICD、profile、firmware、configuration、test report 與 release manifest 均須版本化。
- 每項偏差記錄 owner、風險、期限、補償措施與批准者。

---

## 九、選商與 Benchmark 計畫

### 9.1 優先序

1. PCS／DC-DC：先關閉 280-408.8 V、157 A、50 kW、DC-link、DBC、black-start 與本地服務。
2. Cell：受控規格、批次追溯、GFL warranty logging、運輸與供應生命週期。
3. BMS AFE／MCU：兩條 architecture alternate 做 PoC，EVT 前 down-select 一條主線。
4. HV current／IMD／contactor／fuse／MSD：以 break curve、L/R、I2t、溫升與 fault energy 評估。
5. HVAC／Fire：以 heat balance、偵測、聯鎖、洩壓、propagation 與 AHJ 設計，不以單一標稱 kW 或藥劑量判定。
6. EMS Edge／network／UPS：以 dual NIC、TPM、watchdog、SSD endurance、driver、5 年 TCO 與替換 SOP 評估。
7. Lab／HIL：112S HIL、DAQ、hipot 自有；100 kW cycler、環境、EMC、消防優先租用或委外。

### 9.2 AVL 階段

| 狀態 | 用途 | Exit |
|---|---|---|
| Candidate／LAB | EVM／PoC | official data、active、basic envelope |
| AVL-0 Nominated | Alpha／EVT | compliance、sample、商務／交期初審 |
| AVL-1 Qualified | DVT／PV | DVP、exact suffix、PCN、quality、traceability |
| AVL-2 Production | Pilot／MP | PVT、FPY、capacity、EOL、spares、RMA/change control |

NXP／TI 與不同 PCS 路線是 architecture alternate，不應宣稱為 pin-compatible second source。

---

## 十、經費使用計畫

### 10.1 Funding Envelope

| 成本池 | Low | Plan | High |
|---|---:|---:|---:|
| 人力／NRE | 43.2 | 68.4 | 107.2 |
| 原型、試製、驗證、認證與 Pilot | 36.5 | 72.5 | 140.5 |
| Cloud、資安、characterization、landed cost 等補列 | 7.0 | 22.2 | 53.5 |
| 風險前小計 | 86.7 | 163.1 | 301.2 |
| Contingency | 17.3 | 40.8 | 105.4 |
| Management reserve | 4.3 | 12.2 | 30.1 |
| Funding envelope | **108.3** | **216.1** | **436.7** |

單位為 NT$ 百萬元、未稅、P3／ROM。此表是經濟成本，不是一次性現金請款；財務須以公司 rate card、實際 RFQ、匯率與稅務更新。

### 10.2 Plan 分期授權

| 階段 | 建議上限 | 主要用途 |
|---|---:|---|
| G0-G2／M0-M5 | 18.0 | 核心人力、EVM、test cells、RFQ、顧問、lab reservation、Edge lab |
| G3-G4／M5-M10 | 42.0 | Alpha BMU/BCU/HV、112ch HIL、EMS MVP、PCS sample、P0 fixtures |
| G5-G6／M9-M18 | 64.0 | P1、DVT units、pre-compliance、thermal/HV/EMC、controlled EMS HIL |
| G7-G9／M16-M24 | 46.0 | PV/PVT、認證、Pilot 1＋4、FAT/SAT、field/service/NPI |
| Central contingency／reserve | 46.1 | 依 risk ID 與 Gate 釋出，不自動轉成 scope |
| 合計 | **216.1** | |

### 10.3 選配與排除

- Microgrid open-transition Plan allowance：另加 NT$6.5M；不含 DG、PV、油箱、feeder 與土建。
- Closed-transition／sync／25／32：另加 Plan allowance NT$5.0M，須先有 utility/AHJ 條件。
- 完整 100 kW 自有實驗室：另增 NT$22.3-65.5M；基線採 hybrid lab。
- 100 kW／1C 衍生型成本須於第一代 G6 後另開 SRR/PDR，不先併入本計畫。

---

## 十一、驗證策略

| 層級 | 核心內容 | 主要證據 |
|---|---|---|
| Unit／Property | codec、CRC、endian、state、clamp、idempotency、algorithm | CI report、coverage、property trace |
| SIL | BMS/PCS/meter/HVAC/ATS/fault/clock replay | deterministic log、golden capture |
| HIL／EVT | 112S、56 NTC、open-wire、watchdog、precharge、link loss | raw trace、pass/fail、deviation |
| DVT | HV、thermal、EMC、environment、IMD、fault energy | controlled report、sample matrix |
| Co-HIL | BMS limits、PCS mode、PLC、ATS feedback、VT/CT、24 V brownout | cross-system state trace |
| FAT | 整櫃 BMS＋PCS＋HVAC＋fire＋EMS 組態與故障注入 | FAT record、as-built config |
| SAT／Pilot | site interlock、manual fallback、network partition、30-90 d SLO | site trace、SLO、RMA/runbook |

關鍵不變式：

- Cloud、Web、AI 與 EMS 不得越過 BMS／PCS／local interlock。
- 無 GOOD、fresh limit 與合法 state 時，不 dispatch command。
- Expired command 不執行；復線不重放 retained command。
- CONFIRMED 必須有 actual read-back；write ACK 不等於完成。
- Fire／EPO／protection／fast transfer 不依賴 EMS。

---

## 十二、主要風險與 Top 8 決策

### 12.1 Top Risks

| ID | 風險 | 處置 |
|---|---|---|
| R1 | PCS 直流工作窗與 50/100 kW 承諾未閉合 | 同一 envelope RFQ 至少四家；兩家通過才 nominate |
| R2 | 1C thermal 與 HV fault energy 未證明 | 50 kW reference 先行；1C 另立 derivative |
| R3 | black-start、ATS/STS、接地／中性點條件不明 | Base 與 Microgrid SKU 分開 |
| R4 | GFL cell、PCS、fire、protocol 受控資料不足 | Gate 前取得 exact version、ICD、DVP |
| R5 | EMS 現況僅為 Dev/Demo | Device Profile、Edge authority、offline、control、security 補齊 |
| R6 | 認證、外測與場址成為關鍵路徑 | M0-M2 預約 lab；Pilot rolling 1＋4 |
| R7 | 預算重複或漏算 | 單一 WBS/cost ledger；BMS 35-70M 不另加 |
| R8 | 單點 IPC／switch／gateway／UPS | 定義 local autonomy、cold spare、restore drill、manual fallback |

### 12.2 必須由業主／供應商決策

1. 第一代是否正式凍結 112S／50 kW，並將 100 kW／1C 移至衍生案。
2. PCS 目標型號、韌體、完整 DC envelope、GFM/GFL、black-start 與 DBC。
3. 是否需要 Microgrid、DG、PV、ATS/STS；open 或 closed transition。
4. Site SLD、接地／中性點、critical load list、短路容量與保護協調。
5. Tier 0-3 服務時間，以及 72 小時能力的 load/PV/DG/fuel/weather/EOL 假設。
6. Remote command 範圍、local disable、dual approval 與離線策略。
7. 保固要求的全 cell 取樣、保存、導出與 archive 年限。
8. Pilot／Production SLA、RTO/RPO、Cloud residency、IdP/MFA 與法規清單。

---

## 十三、未來 90 日行動

### 0-30 日：輸入與 RFQ

- 核准 Reference Product、BESS／Microgrid SKU 與 owner。
- 取得 GFL controlled cell specification 與 warranty logging 條款。
- 對至少四家 PCS 發送相同 DC envelope／ICD／sample RFQ。
- 啟動兩條 BMS AFE／MCU PoC、Safety/AHJ gap review 與 112ch HIL RFQ。
- 凍結 PRD family、ID allocation 流程與單一 cost ledger。

### 31-60 日：PDR

- 完成 SRS、C4、SLD、control authority、Safety Goals、初版 Fault Matrix。
- 決策 pack-derived 24 V／black-start；若保留，電源須位於主接觸器上游並隔離、保險與 OR-ing。
- 完成 PCS shortlist、precharge input list、heat balance、short-circuit model skeleton。
- EMS 完成 Device Profile v1、canonical data、command schema 與 Edge BOM。

### 61-90 日：Alpha Start

- 完成 BMS 主路線 down-select、BMU schematic start、BCU resource／power budget。
- 啟動 112S HIL 採購、fixture 設計與 calibration plan。
- EMS 完成 profile SDK、golden replay、read-only lab adapters 與 offline historian skeleton。
- 核准 Alpha build、lab slot 與下一階段 funding。

---

## 十四、交付與追溯

每個 Gate 至少交付：

1. Baseline／PRD／ADR／ICD 的核准版本。
2. BOM／AVL／RFQ／型號與韌體版本矩陣。
3. Requirement-to-test trace matrix。
4. 原始 trace、測試報告、偏差、風險與核准記錄。
5. Release manifest、configuration hash、SBOM 與變更紀錄。
6. 製造、校正、EOL、FAT、SAT、commissioning、rollback、RMA 與 service 文件。

本 v0.1 為正式規劃基線，不代表所有 T/H 項已關閉。任何對外功率、續航、切換、黑啟動、法規或量產成本承諾，須以對應 Gate 的受控證據為準。
