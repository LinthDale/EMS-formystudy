# ADR-009：LLM Provider 抽象層 + SanitizedSample 強制入參

## Status
Accepted（2026-05-29）

> 來源：PRD-0003 §6.4 / §8.3；DL-002 鎖定 Provider 範圍、DL-003 引入 SanitizedSample 強制條款。本 ADR 將 PRD 鎖定之決策正式化。

## Context

device-service 需對 candidate 裝置做自動分類（device_type + suggested_signals + confidence）。分類引擎須滿足：

1. **可切換**：AI 工程師要能在 Anthropic / OpenAI / 本地 Ollama / 測試 Mock 間切換，做成本優化或離線部署
2. **去敏化**：外送 external LLM 的內容不可含 raw MQTT payload / 自由文字 / PII（資安 + OT 偵察前置情報保護）
3. **可測試**：純函數合約可單元測試，不依賴真實 API
4. **成本可控**：相同 signal shape 不重複 call（cache）

可選方案：

| 方案 | 說明 | 取捨 |
|------|------|------|
| A. 各 provider 寫死於 service | 直接 import SDK | 不可切換、難測試、易把 raw payload 送出 ❌ |
| B. `LLMProvider` Protocol + `SanitizedSample` 強制入參 | 介面注入、去敏化在 service 層完成 | 可切換 / 可測試 / 去敏化集中強制 ✅ |
| C. 用 LangChain 之類框架 | 第三方抽象 | 過重、依賴鏈大、與 open-source-first 但精簡原則衝突（ADR-001）❌ |

## Decision

採 **方案 B**：定義 `LLMProvider` Python `Protocol`，所有實作 **入參一律 `SanitizedSample`**，禁止接受 raw payload 字串 / dict。

- **介面**：`classify_device(device_id, topic, sanitized: SanitizedSample) -> ClassificationResult`
- **去敏化資料結構**：`SanitizedSample`（schema_version / device_id / topic / payload_format / sample_count / `fields: list[FieldSummary]` / `human_corrections: list[CorrectionContext]`）；只含 numeric / bool 統計摘要（min/max/count/distinct/bool_true_ratio），不含原始讀值與字串
- **Sanitizer**（`src/sanitizer.py`，service 層執行）：欄位白名單（string 一律剝除）+ 欄位數 ≤ 64 + 樣本 ≤ 20 筆 + PII 黑名單欄位名剝除；property test 證明 sanitized 輸出 substring 不出現於 LLM prompt（FR-328）
- **Output Validator**（`src/output_validator.py`）：reasoning ≤ 500 字、禁含 raw payload substring、禁含黑名單字（password/token/api_key/secret/credential）；違反走 system_fallback、不計 budget（FR-333）
- **四個實作**：`AnthropicProvider`（預設 `claude-haiku-4-5`，可切 `claude-sonnet-4-6`）、`OpenAIProvider`（OpenAI-compatible，含 Together / Groq）、`LocalLLMProvider`（共用 OpenAI-compatible code path，對 Ollama）、`MockProvider`（deterministic，測試 / fallback 共用）
- **切換**：`LLM_PROVIDER` / `LLM_MODEL` / `LLM_API_KEY` / `LLM_BASE_URL` 四個 env var
- **Cache**：key = `sha256(device_id + topic_pattern + signal_shape_hash + provider + model + prompt_version)`；shape 未變不重 call；`?force=true` / MCP `classify_with_context` 強制 cache miss（FR-316）

## Consequences

**正面**
- provider 切換僅需改 1 個 env var（NFR 達標）
- 去敏化集中於單一 sanitizer，強制經 type system（入參型別即 `SanitizedSample`），raw payload 結構上送不出去
- `MockProvider` 讓全鏈路可離線測試 + 作為 budget 100% / LLM 全失敗的 fallback
- cache 降低重複 candidate 的 token 成本

**負面**
- 每個新 provider 都要實作 sanitized → API payload 的轉換
- `SanitizedSample` 為 frozen dataclass，schema 變更須走 ADR（schema_version 版本化）

**已知風險**
- Sanitizer 規則遺漏新型 PII 欄位名 → 以白名單（只留 numeric/bool）為主、黑名單為輔降低風險
- LLM 可能在 reasoning 回吐 raw payload → Output Validator substring 反射檢查擋下

**後續觸發**
- AnthropicProvider 預設 model（haiku-4-5 vs sonnet-4-6）待跑 5 例 candidate 抽樣比較後定（PRD §14 待釐清）
- `LLM_BASE_URL` 安全驗證見 ADR-016 / FR-342（allowlist）
- LocalLLMProvider 的 Ollama E2E 不在 Phase 1 範圍（DL-002）
