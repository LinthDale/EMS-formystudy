# Non-Functional Requirements (NFR) — 量化版

> 對齊：`doc/PRD-架構設計-Guideline.md` §3.4  
> 原則：避免「高效能」「高可用」這類模糊敘述，全部量化到可驗證指標。

## 0. 階段定義

| Stage | 用途 | NFR 適用 |
|-------|------|---------|
| **Dev** | 本機 / WSL，僅自己使用 | 寬鬆（驗收時通過即可） |
| **Demo** | Cloudflare Tunnel 對外，mock 資料 | 中等（demo 期間 SLA） |
| **POC** | 真實設備接入、客戶試用 | 嚴謹（試用合約等級） |
| **Prod** | 正式商用 | 完整（合約等級 + 災難復原） |

當前實際處於 **Dev → Demo 過渡期**。本文件 NFR 分階段標示適用值。

---

## 1. 效能 — Latency

| 指標 | Dev | Demo | POC | Prod | 量測方式 |
|------|-----|------|-----|------|---------|
| Modbus 輪詢週期 | 1s | 1s | 1s | 1s（可調至 100ms） | gateway telegraf interval |
| MQTT publish → DB 寫入 (p50) | < 10s | < 5s | < 3s | < 1s | timestamp diff |
| MQTT publish → DB 寫入 (p99) | < 30s | < 15s | < 10s | < 5s | 同上 |
| PostgREST 查詢 (p50) | < 500ms | < 300ms | < 200ms | < 100ms | API access log |
| PostgREST 查詢 (p99) | < 2s | < 1s | < 500ms | < 200ms | 同上 |
| Grafana panel 渲染 (p50) | < 3s | < 2s | < 1s | < 500ms | 瀏覽器 devtools |
| Cloudflare Tunnel 額外延遲 | n/a | < 200ms | < 100ms | n/a（不適用） | curl timing |
| 告警評估週期 | 1min | 1min | 30s | 30s | Grafana rule interval |
| 告警觸發 → Telegram 送達 | < 30s | < 30s | < 15s | < 10s | 時間戳對比 |

---

## 2. 吞吐量 — Throughput

| 指標 | Dev | Demo | POC | Prod | 量測方式 |
|------|-----|------|-----|------|---------|
| 單一設備寫入頻率 | 1 point/sec | 1 point/sec | 1 point/sec | 10 points/sec | gateway interval |
| 同時設備數 | 2（sim + plc） | 2 | 50 | 500 | 容器資源評估 |
| DB 寫入吞吐 | 10 rows/sec | 10 rows/sec | 500 rows/sec | 5,000 rows/sec | TimescaleDB pg_stat |
| API QPS（單實例） | n/a | 5 | 50 | 200 | PostgREST log |
| Grafana 並發使用者 | 1 | 5 | 20 | 100 | Grafana metrics |

---

## 3. 可用性 — Availability

| 指標 | Dev | Demo | POC | Prod |
|------|-----|------|-----|------|
| 月度 SLO（資料寫入） | n/a | 99.0%（~7h/月停機） | 99.5%（~3.6h/月） | 99.9%（~43min/月） |
| 月度 SLO（查詢 API） | n/a | 99.0% | 99.5% | 99.9% |
| 月度 SLO（Grafana） | n/a | 95.0%（~36h/月） | 99.0% | 99.5% |
| 計畫性維護視窗 | 隨意 | 提前 24h 公告 | 提前 7d 公告 | 提前 30d 公告，限假日凌晨 |

---

## 4. 災難復原 — DR

| 指標 | Dev | Demo | POC | Prod | 緩解策略 |
|------|-----|------|-----|------|---------|
| RTO（從災難到恢復服務） | n/a | < 24h | < 4h | < 15min | streaming replica + failover |
| RPO（資料遺失容忍） | n/a | < 24h | < 1h | < 1min | WAL 歸檔 |
| 備份頻率 | 手動 | 每日 cron pg_dump | 每小時 incremental | 即時 streaming | TimescaleDB 標準工具 |
| 異地備份 | 無 | 同主機 | 異 region 物件儲存 | 多 region + 冷備 | S3/R2/B2 |
| 災難復原演練 | 不需 | 半年 1 次 | 季度 1 次 | 月度 1 次 | runbook 對照 |

當前缺口：R-002 風險登記中。

---

## 5. 容量 — Capacity

| 指標 | Dev | Demo | POC | Prod |
|------|-----|------|-----|------|
| 資料保留期 | 無限（不刪） | 30 天 | 90 天 | 13 個月（含跨年比對） |
| TimescaleDB volume 預期成長 | < 100MB | < 1GB | < 50GB | < 1TB（壓縮後） |
| TimescaleDB 壓縮策略 | 不啟用 | 不啟用 | 7 天前壓縮 | 7 天前壓縮 + 90 天前降頻 |
| Mosquitto 訊息 retention | 不持久化 | 不持久化 | 持久化、24h | 持久化、7d |

---

## 6. 安全 — Security

| 指標 | Dev | Demo | POC | Prod |
|------|-----|------|-----|------|
| Mosquitto 認證 | anonymous | anonymous（內網） | username + password | mTLS |
| Mosquitto TLS | 否 | 否 | 是 | 是 |
| Grafana admin 密碼 | 可預設 | **強隨機（強制）** | 強隨機 + 2FA | 強隨機 + SSO + 2FA |
| Grafana 對外帳號 | n/a | viewer-only | viewer + editor 分離 | RBAC 完整 |
| PostgREST 對外 | 內網 | **不對外** | 內網 + token | API Gateway + JWT |
| MCP Server 認證 | 無 | 內網限定 | token | mTLS |
| Secret 管理 | `.env` | `.env` | Docker secrets | Vault / SOPS |
| TLS 憑證 | n/a | Cloudflare 提供 | Let's Encrypt | 商業 cert |
| OWASP Top 10 對照 | 不做 | 自查 | 第三方掃描 | 第三方滲透測試 |

---

## 7. 可觀測性 — Observability

| 指標 | Dev | Demo | POC | Prod |
|------|-----|------|-----|------|
| Log 格式 | 預設 | 預設 | 結構化 JSON | 結構化 JSON + trace_id |
| Log 集中化 | docker logs | docker logs | Loki / ELK | Loki / ELK + 30d 保留 |
| Metrics | 無 | Grafana 內建 | Prometheus | Prometheus + 13mo 保留 |
| Distributed Tracing | 無 | 無 | OpenTelemetry | OpenTelemetry + Tempo |
| 黃金訊號（Latency / Traffic / Errors / Saturation） | 部分（Grafana） | Grafana | 完整 4 指標 dashboard | 完整 + alerting |
| 告警 Runbook | 無 | 文字描述 | 連結到 wiki | 完整 SOP + 自動化 |

---

## 8. 相容性 — Compatibility

| 項目 | 規格 |
|------|------|
| Modbus 協定 | TCP / RTU；FC1/2/3/4/5/6/15/16 |
| MQTT 版本 | v3.1.1 / v5.0 |
| PostgreSQL 版本 | 15.x（TimescaleDB 對應版） |
| Telegraf 版本 | 1.30.x 鎖定 minor |
| Browser 支援（Grafana） | Chrome / Edge / Firefox 最近 2 年版本；不支援 IE |

---

## 9. 法規 / 合規（Taiwan）

| 項目 | Demo | POC | Prod |
|------|------|-----|------|
| 個資法（電力資料若可識別個人） | n/a | 評估 | 完整盤點與 DPA |
| 台電併聯規範 | n/a | 規格對齊 | 取得認證 |
| IEC 61850（變電所層） | n/a | n/a | 視應用評估 |
| ISO 27001 | n/a | n/a | 內部對照 |

---

## 10. 量測機制

| 指標類別 | 工具 |
|---------|------|
| API latency | PostgREST log + 自製 collector → Grafana panel |
| DB write throughput | `pg_stat_statements` |
| 資料延遲 (publish→write) | Telegraf gateway 埋 timestamp tag → ingest 寫入時 diff |
| 容器健康 | docker healthcheck + Grafana panel |
| 告警送達時間 | Grafana annotation + Telegram timestamp |

---

## 11. 變更管理

- 升級階段（Dev → Demo → POC → Prod）必須走 ADR，明示哪些 NFR 等級切換
- 任一指標未達當前階段最低值 = release blocker
- 季度 review 一次 NFR 表，依實況調整
