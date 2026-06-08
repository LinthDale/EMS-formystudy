# PRD-0003 Phase 1.3 實作計畫 — MQTT Subscribe + Auto-Discovery

| 欄位 | 內容 |
|------|------|
| 對應 PRD | [PRD-0003](PRD-0003-Device-Registry-Auto-Discovery.md) §12.3 / §8.5 / §4 |
| 決策紀錄 | [decision-log](../governance/decision-log.md) DL-011 |
| 狀態 | Planned（2026-05-29） |
| 前置 | Phase 1.1 + 1.2 已合併 dev（device-service REST/雙池/providers/freeze 就緒） |

> 實作層任務計畫，不重述 spec；衝突以 PRD-0003 為準。

## 範圍

被動 MQTT 訂閱 → 偵測未登錄 device_id → 建 candidate → AI 分類 → 信心門檻自動 confirmed / 留待人工。

## 分批（每批 TDD + 合併前 code review）

### 3a — `topic_parser.py`（純函數，≥95% 覆蓋）
Parser Matrix v3（§8.5）：訂閱 `ems/+/+/measurements` + `factory/sensor/+`；規則 #1–#4 解析 device_id（含 #4a payload device_id / #4b normalize / legacy `temp_01→sensor-001`）；deny-by-default 檢查 1–4（topic shape、id regex `^[a-zA-Z0-9_-]{1,64}$`、payload ≤16KB、欄位 ≤64），各自 metric。Rules 5–7（dedupe/rate-limit/status）屬 subscriber 執行期，不在純 parser。FR-301/322/323/324/327、ADR-013。

### 3b — 分類管線 `classifier.py` + `budget_ledger.py`
candidate → `sanitize` → **budget gate**（ADR-014/FR-329，pre-call，100%→MockProvider fallback）→ **L2 guardrail pre**（§8.7/FR-336，mock_guardrail）→ L1 provider → **L2 post**（FR-337）→ `output_validator` → 信心門檻（>0.9 自動 confirmed，§8.6.8 advisory lock；≤0.9 留 candidate）→ 持久化 `device_review_digests`（FR-317，失敗走 deterministic fallback）。LLM cache（FR-316，shape hash）；retry 3 次 + last_error（FR-312）；correction 衝突強制 candidate（FR-332）。

### 3c — `mqtt_subscriber.py`（整合 mosquitto）
aiomqtt 訂閱 loop；對每則訊息跑 parser → deny 規則 5–7（dedupe 60s、rate-limit ≤60/min、status=candidate）→ 已存在 device 則只 update last_seen_at → 新 device 建 candidate（AI pool）→ 觸發 3b 分類。整合測試：mosquitto pub 新 device → DB candidate → MockProvider → confirmed/human-review 分流。接進 `main.py` lifespan（背景 task）。

## 不在範圍（Phase 1.4）
human-review endpoint、MCP server、Grafana panel、`device_audit_log` 表 + FR-339 告警、§15.C 文件同步、真實 Anthropic/OpenAI guardrail provider 的 E2E。

## 驗證
- `topic_parser` / `classifier` / `budget_ledger` unit ≥95%（純函數）
- 整合：throwaway container + mosquitto + timescaledb，pub→candidate→classify→confirmed
- 既有測試不破

## 建議起步
3a `topic_parser.py`（純函數、TDD、無 DB/MQTT 依賴）。