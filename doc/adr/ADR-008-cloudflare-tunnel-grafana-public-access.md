# ADR-008：Grafana 對外採 Cloudflare Tunnel + Access

## Status
Accepted（2026-04-28）

## Context

EMS Grafana dashboard 需對外 demo（mock 資料），預期短期向客戶 / 合作方展示，網址規劃為 `https://ems-demo.synaiq-ai.com`。

可選方案：

| 方案 | 改動範圍 | 風險 | 適合期 |
|------|---------|------|-------|
| A. 走既有 DGX Nginx + Let's Encrypt | 改 nginx 路由、申請 cert、開 inbound port | 影響 synaiq-ai.com 主站、Coturn、iptables | 長期正式 |
| B. Cloudflare Tunnel + Access | 新增子網域、安裝 cloudflared、不開 inbound port | 依賴 Cloudflare 服務 | 短期 demo |
| C. Grafana 直接 expose 公網 | 開 inbound port | Grafana admin/admin 預設值、無 WAF | ❌ |
| D. VPN（WireGuard / Tailscale） | 客戶端需安裝 | 客戶體驗差 | 內部用途 |

需求是「短期 demo、不影響既有 production 入口、訪客零安裝」。

## Decision

採 **B：Cloudflare Tunnel + Access**：

```
外部訪客 → https://ems-demo.synaiq-ai.com
        ↓
Cloudflare Access（要求 email + One-time PIN）
        ↓
Cloudflare Tunnel（cloudflared 守護程序，主動連 CF edge）
        ↓
內網 Grafana（:3000）
```

範圍限制：
- **僅曝 Grafana**；PostgREST :3001、MCP :8765、MQTT :1883、TimescaleDB :5432、Modbus :5020/:5021 一律不對外
- Grafana 啟用 **viewer-only** 模式（demo 帳號無編輯權）
- Cloudflare Access policy：Email allow-list + One-time PIN

## Consequences

**正面**
- 不開 inbound port（Tunnel 為 outbound long-poll 連線）
- 不動既有 DGX nginx / Let's Encrypt
- 訪客體驗：瀏覽器即可，無 VPN 安裝
- Cloudflare 提供 WAF、DDoS、TLS 終止
- 子網域分離；demo 廢止只需移除 tunnel 與 DNS record

**負面**
- 依賴 Cloudflare 服務（單點故障：Cloudflare 出事即 demo 中斷）
- demo 流量計入 Cloudflare 配額
- One-time PIN 對非技術訪客需引導
- 無法用既有 SSO（若未來公司導入）

**已知風險（待 Threat Model 補強）**
- Grafana admin/admin 預設密碼若未改即被 Cloudflare 後內網訪問存在橫向移動風險
- cloudflared 服務帳號權限與啟動穩定性（systemd 守護）
- 子網域被掃描 / 列舉的曝光面

**後續觸發**
- demo 結束後關 tunnel + 收回 DNS record + Access policy
- 若轉為長期對外服務，啟動 ADR 評估遷移到方案 A（DGX Nginx）
- Grafana 必須改 admin 密碼、啟用 viewer-only role；列入 PR checklist
- Threat Model 文件補強（待辦項目 D，由 risk register 追蹤）
