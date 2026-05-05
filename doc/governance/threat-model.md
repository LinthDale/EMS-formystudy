# Threat Model — EMS

> 對齊：`doc/PRD-架構設計-Guideline.md` §3 & §4.4  
> 方法論：STRIDE（Spoofing / Tampering / Repudiation / Information Disclosure / Denial of Service / Elevation of Privilege）  
> 範圍：Demo 階段（Cloudflare Tunnel 對外、mock 資料）與其過渡到 POC 的安全要求  
> 建立日期：2026-04-29

---

## 1. 系統資產（Assets）

| 資產 | 機密性 | 完整性 | 可用性 | 備註 |
|------|--------|--------|--------|------|
| 量測歷史資料（electricity / factory） | 低（mock）→ 中（POC 真實）| **高** | 中 | 真實資料含廠房用電行為，可推斷生產資訊 |
| TimescaleDB 連線密碼 | 高 | 高 | n/a | `.env` 內 |
| Grafana admin 帳密 | **高** | 高 | n/a | 控制儀表板 / datasource / 告警 |
| Cloudflare Tunnel 憑證 | **高** | 高 | n/a | 取得即可代理任何流量到內網 |
| Telegram Bot Token | 高 | 中 | n/a | 取得可冒充告警通道 |
| MCP Server tool 權限 | **高** | **高** | 高 | 直接讀寫 Modbus 設備（控制面） |
| Mosquitto broker | 中 | **高** | **高** | 全資料流中樞 |
| 維運主機 OS / Docker daemon | 高 | 高 | 高 | 全系統根本信任 |

---

## 2. Trust Boundaries（信任邊界）

```
[Internet]
    │  TB-1：Cloudflare WAF / Access
    ▼
[Cloudflare Edge]
    │  TB-2：Cloudflare Tunnel（mTLS, outbound only）
    ▼
[cloudflared on Host]──────────────┐
    │                              │
    │ TB-3：Host process boundary  │
    ▼                              ▼
[Docker Network "ems-net"]    [Host filesystem]
    │  TB-4：Container 間信任       │  .env、docker volumes
    ▼                              │
[Grafana :3000]                    │
[PostgREST :3001]   ◀──── 內網 ────┤
[Mosquitto :1883]                  │
[TimescaleDB :5432]                │
[MCP :8765 (127.0.0.1)] ◀─ TB-5 ──┘
[Telegraf gateways]
[Modbus simulators]
```

**信任假設**：
- TB-1：Cloudflare WAF 過濾常見 web attack；Access 過濾未授權 email
- TB-2：cloudflared outbound long-poll，**不開 inbound port**
- TB-3：Host root 與 Docker daemon 視為已信任；任何取得 host root 即遊戲結束
- TB-4：Docker network 內互信（無 service mesh / mTLS）
- TB-5：MCP 綁 127.0.0.1（不對 docker network 0.0.0.0 暴露）— 待驗證實作

---

## 3. STRIDE 威脅清單

### 3.1 對外 Demo 入口（TB-1、TB-2）

| ID | 類型 | 威脅情境 | 等級 | 緩解 |
|----|------|---------|------|------|
| T-01 | **Spoofing** | 攻擊者偽造 email 試圖通過 One-time PIN | 中 | Cloudflare Access email allow-list（白名單模式，非黑名單）；**禁用 catch-all** |
| T-02 | **Tampering** | 攻擊者透過 Cloudflare Edge 注入 / 改寫流量 | 低 | Cloudflare 提供 TLS 終止；信任 Cloudflare 為前提（風險已接受）|
| T-03 | **Information Disclosure** | demo 子網域被掃描 / 列舉，攻擊者得知內部架構 | 中 | 使用非可猜測的長隨機子網域（避免 `ems-demo.*`、改用如 `ems-demo-x9k7q.*`）；CT log 監控 |
| T-04 | **DoS** | 大量請求打爆 Cloudflare 配額或耗盡 Tunnel 頻寬 | 中 | 啟用 Cloudflare Rate Limiting；Tunnel 配額監控；停用後降級告警 |
| T-05 | **Elevation of Privilege** | 通過 Access 認證的訪客取得 Grafana editor 權限後改 datasource 指向惡意源 / 執行任意 SQL via Grafana SQL editor | **高** | 1) Demo 帳號限定 viewer role（**provisioning 強制**）<br/>2) Grafana datasource 設 read-only<br/>3) 停用 SQL editor 直接編寫權限 |
| T-06 | **Spoofing** | Cloudflare 帳號被盜，攻擊者改 Tunnel 路由到自己服務（cookie steal）| 高 | Cloudflare 帳號 2FA + hardware key；定期 audit Tunnel 路由 |

### 3.2 內網橫向（TB-4）— 通過 Cloudflare Access 後

| ID | 類型 | 威脅情境 | 等級 | 緩解 |
|----|------|---------|------|------|
| T-07 | **Tampering** | Demo 訪客（或 Grafana RCE）打到 Mosquitto :1883 發布偽訊息汙染 DB | **高** | Mosquitto 啟用 username/password + ACL（限定 publish topic）— R-003<br/>短期：Mosquitto 不對 docker host 公開 :1883（移除 ports 對外） |
| T-08 | **Information Disclosure** | Demo 訪客打到 PostgREST :3001 撈所有歷史資料 | 中 | PostgREST :3001 不對 docker host 公開（改 internal only）<br/>Cloudflare Tunnel 僅曝 :3000 |
| T-09 | **Tampering** | Demo 訪客打到 MCP :8765 控制 Modbus 設備 | **高** | MCP 綁 127.0.0.1（不對 docker host 公開）— **必須驗證 docker-compose 的 ports binding** |
| T-10 | **Information Disclosure** | Grafana datasource credential 在 panel SQL 中外洩 | 中 | Grafana datasource credential 設為 admin-only 可見；query history 限制 |
| T-11 | **DoS** | 訪客在 Grafana 建立極重 query（cross-join 整個 hypertable） | 中 | TimescaleDB query timeout（如 30s）；連線池限額 |

### 3.3 設備層（OT）— TB-4 內

| ID | 類型 | 威脅情境 | 等級 | 緩解 |
|----|------|---------|------|------|
| T-12 | **Tampering** | 攻擊者進入內網 docker network 後，透過 MCP / 直連 Modbus :5020/:5021 寫入暫存器 | 高 | 1) MCP 加 token 認證（R-009）<br/>2) Modbus simulator 視為 dev-only，prod 不暴露<br/>3) prod 階段引入 OT/IT 邊界 firewall |
| T-13 | **Spoofing** | 攻擊者偽裝成 simulator 連 mosquitto 發布偽資料 | 中 | Mosquitto 啟用 ACL 後，按 client_id 限定可發布 topic |
| T-14 | **DoS** | 大量寫入 / coil flip 觸發告警 storm | 中 | Grafana alert rule 加 inhibition；告警去重 |

### 3.4 資料層（TB-3 host filesystem）

| ID | 類型 | 威脅情境 | 等級 | 緩解 |
|----|------|---------|------|------|
| T-15 | **Information Disclosure** | `.env` 被誤 commit、誤 backup、誤上傳 | **高** | 1) `.env` 在 `.gitignore`（已執行）<br/>2) `pre-commit` hook 掃描敏感字串<br/>3) backup 流程明示排除 `.env`<br/>4) 啟用 secret manager（POC 階段） |
| T-16 | **Tampering** | `docker volume timescale_data` 被替換 / 注入惡意資料 | 低 | host root 信任假設；定期 `pg_dump` 對照 hash |
| T-17 | **DoS** | 攻擊者刪除 docker volume 或關鍵 config | 高 | 主機帳號管理 + 操作審計；off-host backup（R-002 緩解項）|

### 3.5 帳號與密鑰

| ID | 類型 | 威脅情境 | 等級 | 緩解 |
|----|------|---------|------|------|
| T-18 | **Spoofing** | Grafana `admin/admin` 預設未改 | **嚴重** | Demo 上線 checklist 強制：改強隨機密碼 + 啟用 2FA；提供 viewer-only demo role |
| T-19 | **Spoofing** | Telegram Bot Token 外洩，攻擊者冒充告警 | 中 | Token 走 `.env`；定期 rotate；建立可信告警驗證流程（如附時間戳 + nonce） |
| T-20 | **Repudiation** | 操作者否認執行的操作（誰改了 dashboard / alert） | 低 | Grafana audit log 啟用；POC 階段接 Loki |
| T-21 | **Elevation of Privilege** | `authenticator` PostgreSQL role 取得 superuser | 低 | role 權限明確：`SET ROLE web_anon`，無 BYPASSRLS / SUPERUSER（init.sql 已限）|

---

## 4. 風險矩陣（依等級分組）

| 等級 | 威脅 ID | 對應 Risk Register |
|------|---------|-------------------|
| **嚴重** | T-18 | R-001 |
| **高** | T-05、T-06、T-07、T-09、T-12、T-15、T-17 | R-001、R-003、R-009、R-002 |
| **中** | T-01、T-03、T-04、T-08、T-10、T-11、T-13、T-14、T-19 | R-003、R-006、R-009 |
| **低** | T-02、T-16、T-20、T-21 | — |

---

## 5. Demo 上線前 Mandatory Checklist

下列項目於 Cloudflare Tunnel 對外啟用前**必須完成**，否則禁止對外：

- [ ] **Grafana admin 密碼**：改為 ≥ 20 字元隨機（密碼管理器產生）
- [ ] **Grafana 2FA**：啟用 admin 帳號 2FA
- [ ] **Demo viewer role**：建立 `demo-viewer` role（read-only），demo 帳號僅綁此 role
- [ ] **Datasource read-only**：TimescaleDB datasource 設為 read-only
- [ ] **SQL editor 限制**：viewer role 不可使用 query editor 自由 SQL
- [ ] **PostgREST 內網化**：`ports: 3001:3000` 移除或改 `127.0.0.1:3001:3000`
- [ ] **Mosquitto 內網化**：`ports: 1883:1883` 移除或改 `127.0.0.1:1883:1883`
- [ ] **MCP 內網化**：`ports: 8765:8765` 改 `127.0.0.1:8765:8765` 並驗證 `nmap` 從 host 外側掃不到
- [ ] **Modbus 內網化**：`ports: 5020/5021` 移除（dev-only 驗收後）或限 127.0.0.1
- [ ] **Cloudflare Access allow-list**：明確 email 列表，禁止 catch-all
- [ ] **Cloudflare account 2FA**：hardware key 強制
- [ ] **TimescaleDB query timeout**：`statement_timeout = '30s'`
- [ ] **Grafana audit log**：啟用 + log 檔位置記錄於操作手冊
- [ ] **Telegram Bot Token rotate**：drift token 已撤銷
- [ ] **`.env` 確認不在 Git history**：`git log --all --full-history -- .env` 為空（待 git init 後）
- [ ] **子網域非可預測**：`ems-demo-<random>.synaiq-ai.com`（取代易猜的 `ems-demo`）
- [ ] **Tunnel 路由 audit**：Cloudflare Zero Trust → Tunnels → 確認只有 ems-demo 一條路由

完成簽核：`__________`（操作人）`__________`（覆核人）`__________`（日期）

---

## 6. 殘餘風險（Residual Risks）

即使完成 §5 checklist，下列風險仍存在；接受作為 demo 階段的成本：

| 殘餘風險 | 接受理由 | 升級為 POC 時的對策 |
|---------|---------|-------------------|
| 信任 Cloudflare（T-02） | 短期 demo 必要；切換成本太高 | POC 評估自架 reverse proxy + 自管 cert |
| Mosquitto anonymous（T-07）若未啟密碼 | 改造成本中；demo mock 資料容忍度高 | POC 強制 user/pass + ACL |
| Docker network 平面信任（TB-4） | 加入 mTLS / service mesh 改造大 | POC 評估 Linkerd / Consul Connect |
| MCP token 缺失（T-12） | 內網限定即降至可接受 | POC 啟用 token + per-tool ACL |
| 單一主機（無 HA） | demo 階段可接受 | POC 至少加 replica + 快照 |

---

## 7. 後續行動（Action Items）

### 立即（demo 上線前）
1. 建立 Demo 上線 checklist 對照流程（§5）
2. 修正 `docker-compose.yml`：PostgREST / MCP / Mosquitto / Modbus 的 ports 綁定收斂
3. Grafana 加 demo-viewer role provisioning（記錄於 `infra/grafana/provisioning/`）

### 短期（一週內）
4. Mosquitto 加 password_file（R-003）
5. cron pg_dump + 異地備份（R-002）
6. Grafana → Telegram heartbeat（R-006）
7. EMS 目錄 git init + `.env` 進 .gitignore 驗證（T-15）

### 中期（POC 啟動前）
8. Mosquitto TLS + ACL by topic prefix（ADR-007 對應）
9. MCP token / mTLS（R-009）
10. PostgREST 寫入 endpoint 啟用前先設計 RBAC
11. 結構化 log + Loki + Prometheus（NFR §7）

---

## 8. Review Cadence

- 每月 review 一次 §5 checklist 完成度
- 每季 review 整個 threat model
- 任何新對外介面（端口、API、tunnel）上線前必須補對應 STRIDE 分析

---

## 9. Appendix：未涵蓋的攻擊面（Out of Scope）

- 供應鏈攻擊（Docker base image 被植入）— 接受 Docker Hub 信任假設
- 物理層攻擊（拔網路線、偷主機）— host 已在受控環境
- Side-channel attack（CPU timing 等）— 攻擊複雜度遠超 demo 收益
- DNS hijack（Cloudflare DNS 被入侵）— Cloudflare 帳號 2FA 為主要防線

---

## 10. Related

- `doc/governance/risk-register.md` — 對應風險條目（R-001、R-002、R-003、R-006、R-009、R-013）
- `doc/adr/ADR-008-cloudflare-tunnel-grafana-public-access.md` — 對外架構決策
- `doc/operations/network/Cloudflare_Grafana_Demo_對外公開操作指南.md` — 操作層指引
