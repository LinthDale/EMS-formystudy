# PRD-0003 Phase 1.4 實作計畫 — Human-Review / MCP / Observability / Audit

| 欄位 | 內容 |
|------|------|
| 對應 PRD | [PRD-0003](PRD-0003-Device-Registry-Auto-Discovery.md) §12.4 / §8.4 / §10 / §8.7 |
| 決策紀錄 | [decision-log](../governance/decision-log.md) DL-012 |
| 狀態 | Planned（2026-05-29） |
| 前置 | Phase 1.1+1.2+1.3 已合併 dev（merge 38581f1） |

> 記錄文件，不重述 spec；衝突以 PRD-0003 為準。

## ⚠️ 從 Phase 1.3 帶過來的 MUST-DO（非可選 — 旁路監控確認）

這兩項在 Phase 1.3 是**實質 deferred**，必須在 Phase 1.4 補完，且**接真 provider 上線前為硬前置**：

1. **`record_usage` / FR-329 budget fail-closed 完整化**
   - 現況（保守表述）：pre-call budget gate（`evaluate_budget`）已接上分類管線，但 **token/cost 從未寫回 `llm_budget_ledger`**（`record_usage` 僅為 `budget_ledger.py` 的 TODO）。對 Anthropic/OpenAI 真 provider，spent 永遠是 0，**budget gate 不會真的 trip**。Mock 免費故無影響。
   - Must-do：在每次**真實（非 mock）LLM call 後**寫回用量（tokens_in/out、cost_usd）到 `llm_budget_ledger`（含 L1 與 `provider='guardrail'` 的 L2 各自 row）；80% Telegram alert、100% fail-closed 走 fallback；對應 unit + integration 測試（模擬 80%/100% 門檻）。**接真 provider 啟用前 block。**

2. **MQTT subscriber reconnect / error branch 測試覆蓋**
   - 現況（保守表述）：`run_subscriber` 已加 defensive reconnect loop + lifespan task done-callback，但 **reconnect 路徑與 per-message error branch 尚無單元/整合測試**（commit 已註明 uncovered）。
   - Must-do：補測試 — (a) broker 斷線觸發 reconnect（可用 fake aiomqtt client 模擬 raise→重試）；(b) 單則訊息 `process_message` 拋例外不殺 loop；(c) done-callback 在 task 異常結束時記 error。

## Phase 1.4 其餘範圍（§12.4）

- **Human-review endpoint**：`GET /devices/{id}/human-review` 回 §8.4 digest（讀 `device_review_digests`，不現呼 LLM；fallback 路徑亦回 200）。
- **`/ai-feedback` + correction loop 寫入**：`device_corrections` 寫入（FR-330，含 NFKC/injection allow-list、rate-limit FR-343）、deactivate（FR-341）、retrieval 注入（FR-331）、衝突偵測串接（FR-332 已在 classifier，需接 DB correction 來源）。
- **`device_audit_log` 表 + FR-339 告警**：override token（reject/override/delete）、L2 guardrail BLOCK、AI status 推進的 audit 持久化（取代目前的結構化 log line）；連續 BLOCK / 大量 deactivate alert。
- **MCP server**：device-service 自帶 127.0.0.1:8766，AI 通道僅 `list_low_confidence_candidates` / `get_device_digest` / `classify_with_context`（ADR-012）。
- **Grafana panel**：鎖定 4 個（pending count / status distribution / error & latency / cost）。
- **真實跨 provider L2 guardrail E2E**（§8.7.3，production 強制跨 provider，Promotion P-1）。
- **§15.C 文件同步**：`api/openapi.yml`、`doc/operations/容器速查表.md`（容器數 12→13，加 ems-device-service）、操作手冊 — 見 [[feedback_ems_doc_sync]]。

## 流程（不變）
每批 TDD + **合併前 code review agent**（[[feedback_review_before_merge]]）；計畫/決策落 repo 記錄（[[feedback_plans_need_record_doc]]）；測試在 throwaway 容器跑（[[reference_ems_test_runtime]]）。

## 覆蓋率 / 測試的保守表述（沿用）
所報數字為 throwaway `python:3.11-slim` 容器內、device_service 模組之 pytest-cov 量測，**非 CI/production 全面保證**；整合測試在 DB/mosquitto 不可達時會 skip；`tests/Makefile` 的 coverage target 仍只量 simulator（待補 device-service target）。