# C4 Level 1 — System Context

> 範圍：EMS 作為一個整體，與外部 Actor / System 的互動關係。

```mermaid
flowchart TB
    %% Actors
    operator(["維運人員<br/>（OT）"])
    demo_user(["Demo 訪客<br/>（外部）"])
    ai_agent(["AI Agent<br/>（Claude / MCP Client）"])
    oncall(["值班工程師"])

    %% External Systems
    cf["Cloudflare<br/>Tunnel + Access"]
    telegram["Telegram<br/>Bot"]
    cf_dns["Cloudflare DNS<br/>synaiq-ai.com"]

    %% External Devices (現/將來)
    meters["真實電表<br/>（未來：Modbus RTU/TCP）"]
    plc["工廠 PLC<br/>（Modbus TCP）"]
    sensors["IoT 感測器<br/>（MQTT JSON）"]

    %% The system
    ems["<b>EMS 系統</b><br/>能源管理平台<br/>（量測 / 儲存 / 視覺化 / 告警）"]

    operator -- "操作 Grafana 儀表板<br/>(內網)" --> ems
    demo_user -- "瀏覽 demo<br/>https://ems-demo.synaiq-ai.com" --> cf
    cf --> ems
    cf_dns -. "DNS resolution" .-> cf

    plc -- "Modbus TCP" --> ems
    sensors -- "MQTT (JSON)" --> ems
    meters -. "未來接入" .-> ems

    ai_agent -- "MCP（自然語言<br/>操作設備）" --> ems

    ems -- "告警通知" --> telegram
    telegram --> oncall

    classDef actor fill:#e8f4ff,stroke:#2563eb,stroke-width:2px,color:#000
    classDef external fill:#fff4e6,stroke:#ea580c,stroke-width:2px,color:#000
    classDef system fill:#dcfce7,stroke:#16a34a,stroke-width:3px,color:#000
    classDef device fill:#f3e8ff,stroke:#9333ea,stroke-width:2px,color:#000

    class operator,demo_user,ai_agent,oncall actor
    class cf,telegram,cf_dns external
    class ems system
    class meters,plc,sensors device
```

## 圖例與說明

| 顏色 | 類別 | 範例 |
|------|------|------|
| 🟦 藍 | Human Actor | 維運、訪客、值班 |
| 🟧 橘 | External System | Cloudflare、Telegram |
| 🟩 綠 | The System (EMS) | 本次設計範圍 |
| 🟪 紫 | External Device | PLC、感測器、電表 |

## 關鍵互動

| 互動 | 通道 | 同步性 | 認證 |
|------|------|--------|------|
| 維運操作 Grafana | HTTP 內網 | 同步 | Grafana 帳密 |
| Demo 訪客瀏覽 | HTTPS / Cloudflare | 同步 | One-time PIN（CF Access） |
| PLC 量測上行 | Modbus TCP | 輪詢（同步） | 無（內網） |
| MQTT 感測器上行 | MQTT | 非同步 | 目前 anonymous（dev） |
| 告警下行 | Telegram Bot API | 非同步 | Bot Token |
| AI Agent 控制 | MCP（HTTP/stdio） | 同步 | Token（待強化） |

## 邊界備註

- 本圖為 **L1 概念圖**，不畫容器/服務細節（見 `c4-container.md`）
- 「未來接入」的真實電表已在 ADR-006 規劃同模式（domain-pipeline）擴展
- Cloudflare Tunnel 為 outbound long-poll，**不開 inbound port**（見 ADR-008）
