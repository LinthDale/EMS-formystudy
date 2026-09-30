# Risk Register

> 對齊：`doc/PRD-架構設計-Guideline.md` §5  
> 維護方式：每月 review；新風險出現即追加；緩解完成標記 `Closed` 不刪除

## 機率 / 衝擊評等

- **機率（Likelihood）**：L = Low（< 10%）／ M = Medium（10-50%）／ H = High（> 50%）
- **衝擊（Impact）**：L = 局部不便／ M = 部分功能中斷／ H = 全系統中斷或資安事件
- **優先序**：H/H = P0、H/M 或 M/H = P1、M/M = P2、其他 = P3

---

## P0（立即處理）

### R-001：Cloudflare Tunnel demo 期間 Grafana 內網橫向存取

| 欄位 | 內容 |
|------|------|
| 機率 / 衝擊 | M / H |
| 描述 | demo 流量經 Cloudflare Access 認證後直達內網 Grafana。若 Grafana 仍為 admin/admin 預設或未啟用 viewer-only role，被認證後的訪客可進入編輯模式、改 datasource、甚至接觸內網其他服務 |
| 緩解 | 1) 強制改 admin 密碼為強隨機<br/>2) demo 帳號限定 viewer role<br/>3) Grafana datasource 設 read-only<br/>4) Cloudflare Access policy 收緊 email allow-list |
| Owner | EMS team |
| 觸發 ADR | ADR-008 |
| 狀態 | **Open** — Threat Model 已建立（`./threat-model.md`），對應 T-05/T-06/T-18；待 §5 checklist 落地 |

### R-002：TimescaleDB 單點無備援

| 欄位 | 內容 |
|------|------|
| 機率 / 衝擊 | M / H |
| 描述 | 全系統唯一 DB；硬碟故障 / volume 誤刪即全系統資料遺失。目前僅靠手動 `pg_dump` |
| 緩解 | 短期：cron 每日自動 `pg_dump` 並上傳異地（如 S3 / R2）<br/>長期：TimescaleDB streaming replica + WAL 歸檔 |
| Owner | EMS team |
| RTO/RPO 目標 | RTO < 4h、RPO < 24h（短期）／ RTO < 15min、RPO < 1min（長期） |
| 狀態 | **Open** |

---

## P1（盡快處理）

### R-003：Mosquitto 無認證、明文傳輸

| 欄位 | 內容 |
|------|------|
| 機率 / 衝擊 | M / M |
| 描述 | broker 為 anonymous、無 TLS。在內網信任邊界內可接受 dev；任何進入內網的攻擊者可發布偽資料、取消訂閱、污染 DB |
| 緩解 | 1) `password_file` 啟用使用者密碼<br/>2) TLS 加密<br/>3) ACL 按 ADR-007 topic 前綴切權限<br/>4) 評估替換為 EMQX（功能更全、ACL 更精細） |
| Owner | EMS team |
| 觸發 ADR | ADR-007 |
| 狀態 | **Open** — 已記錄於容器速查表 §2-3 production 升級清單 |


> **暴露面更新（2026-06-10，PRD-0006）**：P1 新增 ingest-generic 訂閱後，惡意發布的影響從「AI 分類污染（candidate 佇列）」擴大為「量測 DB 直接污染」（合法 shape 訊息逐列落庫；`ems_ingest` 無 DELETE，清除須 OPS/superuser `DELETE FROM signal_measurements WHERE device_id=...`，SOP 記操作手冊）。緩解疊加：PRD-0006 FR-603 per-device 速率保護 + FR-601 欄位約束。
### R-004：Mosquitto 重啟期間 QoS1 佇列遺失

| 欄位 | 內容 |
|------|------|
| 機率 / 衝擊 | L / M |
| 描述 | `persistence false`，broker 重啟後 in-flight QoS1 訊息消失。Ingest 在 broker 重啟期間發布的資料會丟 |
| 緩解 | 1) 啟用 `persistence true` + 加 volume<br/>2) Telegraf gateway 加 `output.file` 作為旁路落地（debug-only） |
| Owner | EMS team |
| 狀態 | **Open** |

### R-005：pymodbus 3.6.9 鎖死，新版 CVE 暴露

| 欄位 | 內容 |
|------|------|
| 機率 / 衝擊 | L / M |
| 描述 | ADR-002 鎖定 3.6.9。若 3.6.x 出現 security advisory 而 3.13+ 已修復，必須遷移到新 SimData API（重寫 simulator） |
| 緩解 | 1) 訂閱 pymodbus GitHub security advisory<br/>2) 預先做 spike：用新 API 重寫 simulator 一個 endpoint，估遷移成本<br/>3) 若 simulator 僅 dev-only，可接受較高 CVE 容忍度 |
| Owner | EMS team |
| 觸發 ADR | ADR-002 |
| 狀態 | **Open** |

### R-006：Grafana → Telegram 告警單向、無重試

| 欄位 | 內容 |
|------|------|
| 機率 / 衝擊 | M / M |
| 描述 | Telegram 不可達或 Bot Token 失效，告警靜默丟失，值班無從察覺 |
| 緩解 | 1) 加副通知通道（email / 第二個 chat）<br/>2) 定期（每日）發 heartbeat 訊息驗證鏈路<br/>3) Grafana Alertmanager 配重試策略 |
| Owner | EMS team |
| 狀態 | **Open** |

---

## P2（規劃處理）

### R-007：Telegraf gateway 強殺丟失 5s buffer

| 欄位 | 內容 |
|------|------|
| 機率 / 衝擊 | L / L |
| 描述 | ingest 5s flush buffer，容器強殺即丟。對 1s 取樣率影響有限（最多 5 點） |
| 緩解 | 接受現況；若日後改 100ms 取樣，調短 flush_interval |
| 狀態 | **Accepted（風險可接受）** |

### R-008：TimescaleDB 預設 UTC、跨時區顯示誤差

| 欄位 | 內容 |
|------|------|
| 機率 / 衝擊 | H / L |
| 描述 | DB 存 UTC，Grafana / 本機工具顯示時區不一可能誤判時段 |
| 緩解 | 文件統一聲明「DB 一律 UTC，UI 端 localize」；操作手冊已記錄 |
| 狀態 | **Mitigated** |

### R-009：MCP server 對 AI Agent 無強身份驗證

| 欄位 | 內容 |
|------|------|
| 機率 / 衝擊 | L / M |
| 描述 | MCP 為控制入口（讀寫 Modbus）。當前內網信任，未來若曝外或多租戶，token 認證機制不足 |
| 緩解 | 短期：限制 :8765 僅內網；長期：mTLS / OAuth + per-tool ACL |
| Owner | EMS team |
| 狀態 | **Open** |

### R-010：External KC repos 上游變更失控

| 欄位 | 內容 |
|------|------|
| 機率 / 衝擊 | M / M |
| 描述 | KC 來源置於 `external/`，已轉為 **git submodule + commit pin**（`external/kc_iot_gateway`、`external/kc_modbus_mcp`，見 `.gitmodules`）。本地 build 可重現性已受 commit pin 保護；殘餘風險為上游 force-push / 刪 branch 致 pinned SHA 無法 fetch，或上游停更 |
| 緩解 | 短期（已完成）：EMS 目錄 git init + `external/*` 轉 submodule 並 pin commit SHA<br/>長期：上游若停更或刪除 pinned commit，fork 到自己 org |
| Owner | EMS team |
| 觸發 ADR | ADR-006 |
| 狀態 | **Mitigated**（git init + submodule pin 已完成 2026-04-28；殘餘為上游可用性，待長期 fork 對策） |

### R-014：FR-334「提高當期 LLM 預算」端點未實作（預算告警 remediation 缺口）

| 欄位 | 內容 |
|------|------|
| 機率 / 衝擊 | M / M |
| 描述 | PRD-0003 §10/FR-334 規格了 `POST /admin/budget/extend`（OPS only、必填 reason ≥30 字、audit log、per-IP 1/min），但**實際未實作**（無 route、`budget_ledger.py` 無 extend 函式）。當期 `budget_usd` 一旦該期 ledger row 建立即固定（`get_period_budget` 回現有值；改 env `*_MONTHLY_BUDGET_USD` 只影響尚未建立 row 的新期）。故 PRD-0004 預算告警（FR-401/402）達 100% fail-closed 後，**運維無 API 可提高當期預算**——只能切 mock 或手動 SQL UPDATE（後者無 audit、繞過 OPS 鑑權 / rate-limit） |
| 緩解 | 短期：操作手冊 §3.7 已記手動 SQL workaround + 切 mock SOP（誠實標為臨時手段）<br/>中期：實作 FR-334 端點（帶 audit log / OPS 鑑權 / per-IP rate-limit，照 PRD-0003 §10 規格）<br/>長期：budget 調整全走有稽核的 API，禁手動 SQL |
| Owner | EMS team |
| 觸發 ADR | — （PRD-0003 FR-334 spec 既存，屬實作補齊；與 PRD-0004 告警 remediation 直接相關）|
| 狀態 | **Open** — 缺口於 2026-06-09 寫 PRD-0004 budget-alert SOP 時發現並記錄；待排入實作 |

---

## P3（觀察）

### R-011：Windows 端 EMS 備份目錄混淆開發

| 欄位 | 內容 |
|------|------|
| 機率 / 衝擊 | M / L |
| 描述 | `C:\Users\User\synaiq\EMS\` 為 stage 1 殘留備份；新人或 Claude 可能誤改 |
| 緩解 | 1) `project_rules.md §6` 已規定 WSL 為唯一真相（2026-06-11 修正權威路徑字串 emsuser→dalelin）<br/>2) 刪除 Windows 備份 |
| 狀態 | **Open** — §6 路徑字串已校正（2026-06-11）；Windows 備份刪除待執行 |

### R-012：openapi.yml 與實際 endpoint 漂移

| 欄位 | 內容 |
|------|------|
| 機率 / 衝擊 | M / L |
| 描述 | 三同步義務（§3）依賴自律；若忘記更新，外部使用者按 spec 呼叫會失敗 |
| 緩解 | 短期：PR template + checklist；長期：CI 跑 schema diff（contract test） |
| 狀態 | **Open** |

### R-013：MQTT Topic 命名不一致

| 欄位 | 內容 |
|------|------|
| 機率 / 衝擊 | H / L |
| 描述 | kc-mqtt-sim 第三方來源直發 `factory/sensor/temp_01`，與主規範 `ems/<domain>/{device_id}/measurements` 不一致；增加 ACL 設計、通配符訂閱、新人理解的負擔。kc-gateway 實際 topic 為 `ems/factory/...`，與舊文件記載的 `kc/factory/...`、`factory/devices/...` 皆不符 |
| 緩解 | 短期：本 ADR-007 v3 + 文件同步校正<br/>中期：在 kc-ingest 加 processor 重發到 `ems/factory/sensor-001/measurements`<br/>長期：fork KC repo、改上游 topic |
| Owner | EMS team |
| 觸發 ADR | ADR-007 |
| 狀態 | **Mitigated（文件已校正，實作改造待規劃）** |

### R-015：BFF 本地憑證雜湊強度不足（已緩解）

| 欄位 | 內容 |
|------|------|
| 機率 / 衝擊 | L / M |
| 描述 | BFF P1 以 SHA-256（無 salt、快速雜湊）儲存本地登入密碼；env 外洩時可離線爆破 |
| 緩解 | 已完成：改 argon2id（`argon2-cffi`，PHC 內嵌 salt+成本參數），constant-work + dummy verify 抗枚舉；密碼僅存 `.env`；提供 `python -m bff.hashpw` 產雜湊 |
| Owner | EMS team |
| 觸發 ADR | ADR-024 |
| 狀態 | **Closed（緩解）** — argon2id 已上線（`services/bff/`，測試覆蓋）；長期改接 OIDC（Phase-1）徹底移除 BFF 自管密碼 |

### R-016：前端 dev-toolchain npm audit high findings（dev-only，追蹤中）

| 欄位 | 內容 |
|------|------|
| 機率 / 衝擊 | L / L |
| 描述 | `npm audit`（含 dev）回報約 9 項 high，集中在 Vite / Vitest / esbuild / openapi 等 **dev-toolchain**；`npm audit --omit=dev` 乾淨（runtime 相依無 high）。不影響 prod artifact（nginx 只服務靜態 build，image 不含 node_modules） |
| 緩解 | 追蹤上游修補、定期 `npm audit fix`（dev）；收緊供應鏈 gate（如 CI 加 `npm audit --omit=dev` 門檻）前先清掉或豁免 dev 項 |
| Owner | EMS team |
| 觸發 ADR | — |
| 狀態 | **Open（追蹤）** — prod runtime 不受影響；dev-toolchain 待上游修補 / 升級 |

### R-017：Starlette TestClient / httpx(2) deprecation（測試環境，追蹤中）

| 欄位 | 內容 |
|------|------|
| 機率 / 衝擊 | L / L |
| 描述 | BFF 測試以 Starlette `TestClient` 執行，發出 deprecation warning（`Using httpx with starlette.testclient is deprecated; install httpx2 instead`）。僅警告，不影響測試結果或 runtime；但 FastAPI / Starlette / httpx / httpx2 之間的相容矩陣需先釐清，貿然升級恐破壞測試環境 |
| 緩解 | 維持現版（warning-only，可接受）；升級前先查 FastAPI × Starlette × httpx(2) 相容矩陣，確認 TestClient 用法與版本 pin，再更新 `services/bff` 測試依賴 |
| Owner | EMS team |
| 觸發 ADR | — |
| 狀態 | **Open（追蹤）** — 僅測試環境警告；待相容矩陣釐清後更新測試依賴 |

---

## 統計摘要

| 優先序 | 數量 |
|--------|-----|
| P0 | 2 |
| P1 | 4 |
| P2 | 4 |
| P3 | 6 |
| 總計 | **16** |

| 狀態 | 數量 |
|------|-----|
| Open | 11 |
| Mitigated | 3 |
| Accepted | 1 |
| Closed | 1 |

### R-018：歷史彙整查詢負載（ADR-027）
機率 M / 衝擊 M；Owner EMS；狀態 Mitigated for local preview。7 天/1200 桶、圖表30s預設、同頁不併行刷新；資料庫 read-only RPC、時間/設備索引。剩餘風險：BFF timeout 不一定取消 DB 查詢、尚無每帳號限流，公網上線前須補 statement timeout / rate limit 並作高密度負載測試。

### PRD-0019 通知風險（2026-09-23）
外部 timeout 可能已送達：顯示結果不確定，同 UUID 快取失敗且不自動重送。重複點擊以 30 秒全域冷卻/10 分鐘 UUID 去重/前端 disabled 緩解。DEMO 固定標示無需處置。記憶體限制為單程序，重啟會清空；若擴為多 worker，需先改共用去重儲存。Owner：EMS 維運；詳細風險表見 PRD-0019 §11。

## PRD-0020 Delta edge 增量風險
動態scale/地址/word-order以PDF literal測試與現場交叉比對控制；queue有界且滿時拒收並記錄；NTP未同步或倒退不採樣；sim與field使用不同ID。PUBACK非DBACK、既有DB不去重；接收端payload身分綁定、真機RS485、SIM7600供電/APN/TLS是未完成field gate。完整8項風險見PRD-0020 §11。

## Delta 多設備可靠性提案（Draft，2026-09-29）
[PRD-0021 §11](../prd/PRD-0021-multi-device-edge-reliability.md)登錄10項提案風險，Owner EMS team，狀態均Open／待實作驗收：型號map、雙master、bus timeout、broker ACK窗口、SD電源、偽造ACK、時鐘、queue滿、v1/v2雙寫及WAL版本。現有v1限制維持，不將研究結果標為風險已關閉。

PRD-0021 FR-2113～2116補充：對帳count相同但ID不同、末尾整段遺失、receipt在而量測被刪、audit超窗均為Open風險；以封存manifest、實際投影核對、範圍明示及不可恢復狀態處理，尚未部署。

採樣間隔提案風險（Open，FR-2117/2118）：較快設定可能造成bus超載、pending/audit容量不足、补傳永遠追不上、revision切換誤算漏筆；由requested/effective分離、整體admission、容量規劃與slot邊界驗收處理。此為規格，控制措施尚未部署。

### ADR-031 RTU 從站模擬風險
Owner EMS team：PC/Pi兩顆隔離轉接器、同參數、總線單一主站及端點終端需到貨核驗。PTY僅驗證軟體，Windows COM驅動、電氣極性/訊號地、M70A-262/RPI-M30A型號映射及4G仍Open。錯串口/無權限/被占用須失敗退出；模擬上傳另用測試身分，避免混入實機歷史。

### PRD-0022 統一 simulator 控制（2026-09-29）
Owner EMS；已控制：未認證REST/Modbus寫入旁路（target拒絕）、重放（durable UUID）、併發覆蓋（CAS/單台串行）、未知結果（receipt/instance對帳）、磁碟不可寫（派送前commit/fail closed）、回應無界（16KiB/3秒總期限）。
剩餘：受信任Docker host/root可繞過應用；設定重啟還原；SQLite單機磁碟/備份風險；未建長期歸檔、達100000 commands需停寫規劃；無前端控制頁/多副本/實機寫入。PRD-0022 §11及操作手冊列明限制。

### PRD-0022 CLI Secure cookie 相容性
機率 M／衝擊 M；Owner EMS；狀態 Mitigated。原 CLI 在 login200 後因未回送 Secure cookie 而遭401；只為 exact numeric loopback HTTP origin 增加 CookieJar 例外，不降低 BFF Secure 或外部TLS要求。跨host/port、userinfo、expiry/path 測試與真實HTTP往返已通過；同主機惡意服務仍屬受信任本機環境的剩餘風險。

## 2026-09-30：PRD-0023 帳號資料庫

| Risk | Impact | Mitigation | Residual / Owner |
|---|---|---|---|
| DB outage | local 登入及 session 驗證不可用 | 5s timeout、503 fail closed、DB復原 | 可用性依賴DB / EMS ops |
| 並行停用最後OPS | 無維運帳號 | READ COMMITTED +共用transaction lock；拒絕其他隔離級 | DB owner受信任 / EMS ops |
| 服務憑證外洩 | 帳號hash或管理權限外洩 | reader/admin分離、DSN不進log、.env權限600、備份保護 | 主機/Docker管理人員仍有權限 / EMS ops |
| 變更後舊session有效 | 離職或舊權限仍能存取 | immutable UUID/version，逐請求驗DB，無快取回退 | 已在執行中的請求不回溯取消 / EMS |
| 惡意PHC／HTTP重複取消 | 資源耗盡 | 編碼與成本上限、2 workers、completion callback釋放 | 需部署流量限制 / EMS ops |
