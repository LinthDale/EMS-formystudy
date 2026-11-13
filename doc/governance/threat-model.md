# Threat Model — EMS

## 2026-11-13 ADR-045量測容量淘汰邊界

[ADR-045](../adr/ADR-045-newest-first-edge-retention.md)核定最新量測優先，本地受信採集器可因queue／audit／byte壓力淘汰最舊量測。遠端ACK／reconcile不新增任意刪除權，中央receipt與控制帳本不循環淘汰。所有新樣本型別／finite／hash與本地奈秒int64驗證在淘汰前完成；非法新樣本不造成刪舊。淘汰、新寫、seq與摘要同交易；摘要固定大小，不另造無界log表。

已淘汰原UUID收到真ACK返回False、不以seq／row位置解析為replacement；保留當前session／generation／batch／ID/hash與mTLS。schema3阻舊版開啟，部署須停舊writer與備份，不靠只改檔案版本號完成回滾。主機root／本地配置者仍受信；外部占滿磁碟／卡損無法保證最新可持久化，失敗必須回滾而不宣稱成功。中央上傳摘要／缺口UI與正式硬體／容量SLA仍未驗收。

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
| T-08 | **Information Disclosure** | Demo 訪客打到 PostgREST :3001 撈所有歷史資料 | 中 | PostgREST :3001 不對 docker host 公開（改 internal only）<br/>Cloudflare Tunnel 僅曝 :3000<br/>per-device facade（ADR-025）：瀏覽器經 `/api/devices/{id}/measurements` 取數，零 PostgREST operator 知識 |
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

### 3.6 BFF 與自建前端（PRD-0005，TB-6：Browser ↔ BFF session 邊界）

> 新邊界 TB-6：瀏覽器是唯一後端入口；X-API-Key（OPS/INGEST）只存在 BFF 伺服器側、永不過此邊界；AI key 不在 BFF。新資產：BFF channel keys（機密性高）、server-side session store（完整性高）。見 ADR-023。

| ID | 類型 | 威脅情境 | 等級 | 緩解 |
|----|------|---------|------|------|
| T-22 | **Spoofing** | 竊取 / 偽造 session cookie | 高 | HttpOnly+Secure+SameSite=Strict；opaque 256-bit id；idle 30min + max 8h；每請求驗證 |
| T-23 | **Tampering (CSRF)** | 跨站觸發 mutating `/api` 路由 | 高 | SameSite=Strict + Origin allowlist middleware（deny-by-default，含 login）|
| T-24 | **Elevation of Privilege** | INGEST/READONLY session 經 BFF 持有之 OPS key 提權 | 高 | endpoint 級 role authz（負向測試鎖定）；role 變更即 revoke；READONLY 無 key 通道 |
| T-25 | **Information Disclosure** | 上游 401/403 / 錯誤洩漏 key 或拓樸 | 中 | upstream 401/403→502；error body 無 key/host；log 不記 key/cookie |
| T-26 | **Information Disclosure / Credential** | BFF 本地憑證以快速雜湊（SHA-256 無 salt）儲存，env 外洩即可離線爆破 | 中 | ✅ 已緩解：改 **argon2id**（PHC 內嵌 salt+成本參數，memory-hard）；僅存 .env；constant-work + dummy verify 抗枚舉（`bff/credentials.py`，ADR-024）|

> T-26 戰略緩解：長期改接企業 IdP / OIDC（`BFF_AUTH_MODE=oidc`），BFF 不再自管密碼；argon2id 為無 IdP 環境的 fallback。見 ADR-024。
> OIDC 已實作（2026-06-16，`bff/oidc.py`）：Authorization-Code+PKCE；id-token 經 JWKS 簽章 + iss/aud/exp/iat + 顯式 nonce 驗證、**alg 鎖定 RS/ES（拒 alg:none / HMAC 混淆）**；state 單次用（此 GET flow 的 CSRF 防線）；claim→role fail-closed（無預設權限）；token/verifier/secret 不入 log。config fail-fast：post-login redirect 限同源 path（防 open-redirect）、issuer/redirect 強制 https（localhost 例外）。真接企業 IdP 僅需 env 提供 issuer/client。

> M-1（已實作）：BFF `/api` 回應（含 CSRF-deny 路徑）已加 §9.5 防禦性 header — `X-Frame-Options: DENY`、`Referrer-Policy: strict-origin-when-cross-origin`、`Content-Security-Policy: default-src 'none'; frame-ancestors 'none'`（＋既有 `Cache-Control: no-store`、`X-Content-Type-Options: nosniff`）。**SPA HTML 頁的 script/connect-src CSP 與 HSTS 屬前端 nginx / TLS terminator 層**（nginx layer 另處理）；此處僅涵蓋 JSON API 面。對應 T-22 clickjacking 防護。

> T-08 強化：§9.3 決策後，PostgREST 唯一瀏覽器讀取面 = BFF（:3001 維持內網）。

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

### 歷史查詢增量（2026-09-23，ADR-027）
T-08/T-11/T-24：history/records 仍 OPS-gated；domain 只依 gateway 解析。RPC SECURITY INVOKER，只讀既有 api views；拒絕 PUBLIC EXECUTE，僅 web_anon 執行。新 RPC 增加內網查詢面但不增加可讀資料欄位；需維持 PostgREST 網路隔離。SQL 與 BFF 雙層最多 7 天、1200 桶/頁1000列，未知或重複參數拒絕。現階段尚無每使用者限流，併發濫用仍是剩餘風險；BFF 既有 timeout 不等同 DB statement_timeout。

### PRD-0019 Telegram 出站邊界（2026-09-23）
威脅：未授權通知、CSRF、任意收件者/文字濫發、Token 因 URL log 洩漏、重複送出。控制：OPS session、Origin allowlist、UUID4-only extra-forbid、固定 host/chat/message、不跟隨 redirect、限速/去重、HTTPX URL filter + httpcore WARNING、固定錯誤而非 provider body。ASGI 測試覆蓋認證/CSRF/輸入/失敗/遮蔽/併發。前端與公開 proxy 不接受使用者指定 Token。

### PRD-0024 Telegram 訪客綁定入口（2026-10-13，ADR-036）
新信任邊界：任何 Telegram 使用者都能向 Bot 傳訊，BFF 以 getUpdates **出站**拉取（無 webhook、無新入站埠、代理白名單不變）。
- Spoofing：拍照／轉傳 QR 遠端冒綁 → start code 128-bit 隨機、60 秒輪替、300 秒有效、訊息逾 120 秒忽略；面板顯示遮罩名稱供工作人員按鈕前確認。deep link 只回給 OPS session。剩餘：有效窗內的遠端綁定仍可能（衝擊為示範訊息送錯人，無設備控制）。
- Tampering：Bot 指令只接受私人對話、非 bot、≤64 字的 `/start [code]`、`/stop`；只能改變「唯一綁定」，不能指定文字或其他收件者；`/stop` 只能解除自己的綁定。
- Repudiation：log 只記事件類型（bound/unbound/rejected/state），刻意不記身分；屬隱私優先取捨。
- Information disclosure：狀態只回遮罩名稱與當日人數；原始 chat id 只在綁定期間（≤10 分鐘）存於 0600 SQLite；訪客以每日隨機 key HMAC 假名化、午夜銷毀 key 與名單、secure_delete；getUpdates 請求行不入 log、Token URL 遮蔽、provider 回應不記錄。
- DoS：每使用者 3 秒 1 指令、全域每分鐘 ≤20 回覆、batch 上限 100、錯誤退避 1→60 秒；狀態檔被鎖或失敗時 fail closed（綁定停用，固定對象示範仍可用）。
- Elevation：Bot 指令無法觸發發送；發送仍需 OPS + Origin + 冷卻 + UUID 去重。webhook／第二個輪詢者只回報狀態，不自動 deleteWebhook。

## PRD-0020 Delta edge 信任邊界
新OT路徑只FC04、無公網Modbus或遠端命令。Field MQTT強制驗cert與hostname，帳密env或mTLS、ACL按device topic；client限制無法替代接收端payload身份綁定（後者仍是field gate）。Pi不持有DB/OPS金鑰；SQLite0600/專用目錄0700、定長payload與row上限。Demo明示plaintext且新增容器不publishhostports；既有demo broker設定沒有變動。

## Delta v2 提案信任邊界（Draft，2026-09-29）
[PRD-0021 §9](../prd/PRD-0021-multi-device-edge-reliability.md)：OT唯讀、Pi出站TLS、gateway憑證→topic→device授權、server-only ACK、pending ID/hash驗證、bounded payload與重放時間窗。主要新增威脅是偽造committed ACK導致本地刪資料，以及跨gateway注入／receipt與量測復原不一致。控制措施尚未部署；既有匿名demo broker不得視為field接收端。

PRD-0021對帳補充：reconcile回覆不能刪queue；page/cursor須限自有gateway/device/stream及session/range、固定大小與速率，拒絕retained／舊session回覆。缺筆重送只操作既有資料，不允許OT控制或遠端SQL。控制仍為Draft。

採樣設定提案（Draft）：僅授權OPS／管理者可改preset，中央與gateway均驗證身份、版本、速率及資源；拒絕重放／過期／並發覆蓋，離線不偽裝已生效。samples/reconcile通道不接受設定命令；正式設定傳遞介面須另實作與審查。

### ADR-031 RTU simulator 增補
僅operator指定的本機COMn或/dev路徑，拒絕網路serial URL；RTU不啟動TCP listener。single=False與單站context、ignore_missing_slaves、broadcast disabled防止回應其他站號；FC04白名單維持唯讀。串口啟動失敗不以ready假成功。實體RS485無認證能力，只在隔離實驗總線使用模擬器；TLS/接收端身分驗證的既有待辦不因本增量而完成。

### PRD-0022 Simulator 管理面（2026-09-29）
Spoofing/Elevation：OPS session、Origin、service token、固定ID/目的地，actor不接受body；真機/Pi不在registry。
Tampering/Repudiation：intent先commit、append-only events與防update/delete trigger、UUID/hash/CAS/receipt對帳；非密碼學防竄改。
Information disclosure：錯誤固定碼、credentials不進audit、capabilities不暴露host；OPS才可查actor/reason。
DoS：4096-byte body、16KiB串流response、3秒hop總期限、单台busy立即拒絕、100000 commands上限、4096 target receipts上限、缺token不開控制。
舊REST與FC05/06/15/16/22/23在target封鎖；profile read僅為提示，真正防線在Modbus接收層。
信任假設：同一Docker host的四個固定container、無負載平衡；service credential/host管理員受信任。認證內部HTTP不是現場OT遠控，也不替代4G/TLS field gate。

### PRD-0022 CLI loopback cookie 修正
僅 CLI 明確選定的數字 loopback HTTP origin（127.0.0.1／::1、相同有效port）可回送其 Secure cookie；不更改 Secure flag，仍驗 domain/path/expiry。localhost/DNS名稱、userinfo、異port、外部HTTP均不能取得例外；無環境proxy/redirect與cookie持久化。BFF仍以原Secure session與OPS/Origin驗證。受信任本機服務被冒名的風險沿用原本local HTTP開發邊界；外部連線須TLS。

## PRD-0023：local 帳號信任邊界

- 帳號與audit只存在 private bff_auth；PostgREST web_anon/PUBLIC無USAGE。
- Runtime reader不可寫；account-admin只執行固定SECURITY DEFINER函數，search_path固定pg_catalog，表全限定。
- DB actor為session_user；共享管理DSN不是個人EMS登入身分。受控DB owner可復原，並非抵抗DB owner的防竄改存證。
- 密碼輸入getpass、Argon2id；輸出/稽核無hash。legacy明確一次性匯入，無env auth fallback。
- 角色、密碼及enable/disable更新version；每請求驗UUID/version/role/enabled；DB outage 503，OIDC provider分流。
- 共同transaction advisory lock + READ COMMITTED、atomic audit、UUID重送抑制、拒絕NULL/非法PHC匯入。
- 審查發現的RR舊快照、PHC解碼、重複取消資源上限已以回歸測試覆蓋；詳account-management-verification.md。


### 2026-11-12 台架回覆新鮮度補充（未修改runtime邊界）

合法CRC、站號與長度只驗格式，不能單獨證明回覆屬當前RTU查詢；R20-BENCH-01已有記憶體與實體台架重現、真機尚未驗證。資料品質與現場准入需保留這個限制，不能以本機正常採樣PASS宣稱抗舊封包／重播能力已完成。既有串口隔離、唯讀操作及PUBACK非DBACK限制維持。
### ADR-040 串口恢復邊界

重開僅限operator明確指定的原本機端點，沿用local_serial_port限制，不自動枚舉或切換COM，不增加網路listener。首次開啟失敗退出；同端點移除後再現可能是不同設備，COM號不提供密碼學身分驗證，現場仍需設備profile與盤點。CRC／站號／長度及R20-BENCH-01遲到封包限制保持，恢復不構成資料新鮮度保證。

2026-11-12新鮮度證據更新：第5關已用兩顆實體USB-RS485確認20/20舊回覆可被下一次Poller.read接受；R20-BENCH-01未解除。僅CRC／站號／長度及收包現在時間不提供交易身分／來源新鮮度；完整sample與真機仍需另驗。現有資料不能宣稱抵抗遲到／重播，測試沒有將故障值發往EMS。

### ADR-041：隔離恢復的信任假設

未知回覆上界的不確定交易不再送下一個讀取；field必須核定上界且啟動等待，防重啟清除記憶體鎖定的旁路。受信operator提供response_lifetime_source只作依據紀錄，不能防錯誤核定、設備超界或惡意延遲／重播。此機制不增加來源認證、遠端解鎖、總線多主仲裁或DB ACK；單主與本機端點邊界保持。台架值不得當成Delta真機核定值；詳[ADR-041](../adr/ADR-041-rtu-uncertainty-and-bounded-recovery.md)。

### 送達／重放測試邊界（2026-11-12）

[第9關](../../output/delta-no-pi-validation-20261112/ack-isolated-01/README.md)以私有真broker與受控SQLite重現v1遺失／重複，未新增認證、receipt或去重。UI按量測時間拒標歷史補傳為live的synthetic API測試，不等於全系統heartbeat分離或防重播完成。PRD-0021未部署控制維持Open。

### TLS拒絕與時間邊界實證（2026-11-12）

[隔離實測](../../output/delta-no-pi-validation-20261112/field-security-02/README.md)驗證production Publisher拒絕不受信憑證及認證失敗時保留資料，未增加權限。私有ACL不證明field gateway/device身分綁定；注入UTC只驗現有ClockGuard，不能取代可信時間來源。無production契約或共享runtime變更。

### 實際接收程式反例補證（2026-11-12）

[私有實際接收副本](../../output/no-pi-ingest-20261112/README.md)重現重複入庫及接收停機時 PUBACK 後缺筆；未實作中央 receipt、去重或新認證。另一 network-none namespace 的 IP 丟包恢復不證明抗重播或 4G／field ACL 完成。所有故障限自有副本與 namespace，production／共享設定不變，既有 Open 控制保持。

### ADR-043 已實作可靠送達子集（2026-11-12）

v2四欄canonical樣本strict schema、bytes/depth/finite/重複key限制；DB UTC時間窗與server重算hash後原子receipt／投影，衝突不覆寫。ACK只接受當前gateway/session/generation/batch/pending ID/hash，reconnect與驗證／SQLite刪除共lock，retained／混合結果拒絕；PUBACK只計診斷。field mandatory mTLS、CN→gateway、權威device/stream/revision/profile／生效時段，只有receiver可發布ACK/sessionresponse。獨立TLS topic plane的真ACL正反測試見[證據](../../output/committed-delivery-fix-20261112/README.md)，不向Pi交DB／OPS金鑰。

demo v2驗namespace且只有lo；驗證worker不掛Docker socket／COM／hostports，PKI臨時清除；入站queue與registry／速率有界。初始化／執行錯誤只記類型，DSN不進log。正式部署不得留匿名listener繞過v2 ACL；主機root／DB管理員仍受信任，非防管理員竄改。PITR須外置generation換代與強制重連，實站撤權輪替／PITR／中央備援未驗；未切共享v1。

### 2026-11-13 私有生命週期測試與空庫防護（ADR-045）

[本輪](../../output/no-pi-lifecycle-20261113/README.md)新host-worker測試控制僅三個固定op映射本run owned IDs，不接受CID／host path／任意命令；worker無Docker socket／serial／hostport。request／XML／proof拒symlink／非regular／超限，host writes採exclusive random FD→rename、stdout持匿名FD讀，不follow worker替換路徑。此為受信測試程式邊界；worker可讀測試CA材料，不宣稱正式最小憑證部署或完全不受信worker隔離。私有CA撤client serial後CRL verify error23，restart broker迫使活動old連線斷／重連拒，新cert同CN可用；非正式撤權SLA。

production store不自動重建已存在的zero／empty／damaged queue；只對精確SQLITE_READONLY_ROLLBACK以mode=rw交SQLite原生回滾，其他損壞不fallback、不刪journal、不resetseq。未知尾端仍須復原／新stream治理，不能以建空庫讓資料完整性檢查假PASS；wire／認證與中央DB邊界不變。

### 2026-11-13 ADR-048與私有DB restore控制

sender只改原pending選取，latest／oldest依固定ASC/DESC，不接受SQL排序輸入、不改UUID/hash或當前session/generation/batch驗證；只有本地resolved committed換成功輪次，retiredACK不冒充成功。host DB控制只固定op→當輪owned database，ems備份到新ems_restore、不drop原庫，worker無任意SQL／DSN／path／CID權。

docker cp可把容器symlink帶到host，本輪因此改fresh private copydir＋NOFOLLOW|NONBLOCK FD／regular／16MiB雙限binary讀、核SHA256後原子發布，拒symlink／FIFO／oversize。worker是受信測試程式，可讀私有PKI，不宣稱完整惡意worker隔離。還原後外generation與新session拒真舊ACK，但已ACK且dump未含／localpayload已刪仍不可補，不能當RPO0／WAL PITR防護。[本輪證據](../../output/no-pi-restore-load-20261113/README.md)。

### ADR-049 同步WAL信任／私有工具邊界

020以pg_catalog固定search_path／SECURITY DEFINER僅回boolean，撤PUBLIC execute，只授receiver；不授read_all_stats或複寫憑證。field禁止local降級，具名唯一sync peer／固定LSN覆蓋後ACK。flush報告仍信任DB管理員及受限TLS複寫端，不能靠application_name證明真fsync或獨立失效域。archive按systemID/timeline隔離，basebackup/WAL含營運資料須限權。

PITR工具只用本輪owned IDs／固定op，prepare非root，WAL/base檔名白名單＋NOFOLLOW有界讀，postworker create的commands.json也改exclusive random FD→rename避免symlink外檔覆寫。恢復點未達／缺WAL不能promote當成功；外generation與重連保護未決樣本。正式部署仍待驗，詳[ADR049](../adr/ADR-049-synchronous-wal-ack-and-pitr.md)。

### 2026-11-13 無Pi切換短測信任邊界

受限field DB LOGIN僅繼承ems_edge_receiver，四個真管理／刪除／改內容操作拒絕；撤INSERT故障限當輪私有DB固定表，finally恢復，產品權限未改。v1轉換SIGKILL僅當輪Popen子PID、驗marker PID/stage，來源bytes不變；同mTLS principal用相同clientID造成的可用性中斷仍可能發生，但真inflight斷線清session、新challenge／舊ACK拒／來源保留已驗。不是抵抗持有合法私鑰者DoS；正式私鑰治理仍需維運。控制器只增cutover測試白名單／閘門，無新host op。[證據](../../output/no-pi-cutover-20261113/README.md)。

### 2026-11-13 量測本地語意一致性防護

reliable_store對已存在庫不止quick_check：驗queue/audit／水位與重複seq；enqueue同BEGIN IMMEDIATE且退休前比現存audit MAX，ACK同write tx對sample/hash/SQL/audit/window再驗才刪；pending一致read snapshot並驗選中payload。固定SQL／參數化ID，不新增角色／遠端控制／自動修復。retention累加後先驗界避免提交不可讀摘要；optional audit_time只是效能index，FULL fallback不放寬安全。

測試限當輪自建DB、TCP模擬器、broker與owned Popen子程序；五malformed MQTT批次真parser零部分入庫，SIGTERM真DBlock仍存時退出、再啟全edge，ledger／receipt／projection逐ID/hash/time/device/四值一致。不能防DBadmin完整偽造或整份一致舊備份替換，也不是全庫持續cryptographic bitrot掃描／實體SD驗收。[證據](../../output/no-pi-integrity-20261113/README.md)。

### 2026-11-13 DB／WAL與備份邊界

DB TLS client與archive principal分離，驗CA／hostname／client cert；固定WAL角色＋pg_stat_ssl/client_dn納入受限SECURITY DEFINER boolean，沒有統計全讀。缺021拒絕。restore將bundle視為不可信：先bounded tar header拒PAX/sparse/link/device/穿越，再外置可信system ID＋pg_verifybackup，才PG到核定target；同ID分支仍需timeline核定。server key在PGDATA外，證據不得封私鑰。QA控制只接受owned固定op；沒有主張防受管PG／CA管理員偽造或正式撤權SLA。[ADR-050](../adr/ADR-050-database-tls-and-recovery-identity.md)。

### 2026-11-13 還原分支與新保護鏈

還原目標不從untrusted archive的latest自動推定；CLI外置timeline正uint32／target安全ASCII63字白名單，拒引號／換行及缺值，設定輸出不自動寫檔或起PG。新slot在base之前reserve，全段保留到接手，外置generation換代才開ACK；同ID錯分支由維運核定與實際還原資料核對，並非checksum可證。critical控制6固定op＋UUID、無worker選CID/SQL/path/timeline，中央資料僅owned16MiB quota。server key仍外置PGDATA；[ADR-051](../adr/ADR-051-pinned-recovery-and-slot-reseed.md)。
