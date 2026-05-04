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
| 描述 | KC 來源目前為一般 clone 置於 `external/`，**尚未轉為 git submodule**（EMS 目錄尚未為 git repo）。上游 force-push 或刪 branch、本地 clone 又不慎重新 pull，build 行為即可能不可重現 |
| 緩解 | 短期：本地保留現有 clone 不做 `git pull`；記錄當下 commit SHA<br/>中期：將 EMS 目錄 git init 並把 `external/*` 轉為 submodule + commit pin<br/>長期：上游若停更，fork 到自己 org |
| Owner | EMS team |
| 觸發 ADR | ADR-006 |
| 狀態 | **Open**（待 EMS git init + submodule 轉換） |

---

## P3（觀察）

### R-011：Windows 端 EMS 備份目錄混淆開發

| 欄位 | 內容 |
|------|------|
| 機率 / 衝擊 | M / L |
| 描述 | `C:\Users\User\synaiq\EMS\` 為 stage 1 殘留備份；新人或 Claude 可能誤改 |
| 緩解 | 1) `project_rules.md §6` 已規定 WSL 為唯一真相<br/>2) 刪除 Windows 備份 |
| 狀態 | **Open** — 計畫近期清理 |

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

---

## 統計摘要

| 優先序 | 數量 |
|--------|-----|
| P0 | 2 |
| P1 | 4 |
| P2 | 4 |
| P3 | 3 |
| 總計 | **13** |

| 狀態 | 數量 |
|------|-----|
| Open | 10 |
| Mitigated | 2 |
| Accepted | 1 |
| Closed | 0 |
