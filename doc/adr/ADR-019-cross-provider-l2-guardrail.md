# ADR-019：跨-provider L2 Guardrail（L1 / L2 不同廠商的 defense-in-depth）

## Status
Proposed（2026-06-09；已過 architect + security 審視，APPROVE-WITH-CHANGES 修正完成：fail-closed 啟動拒啟語義、pricing 列同級 blocker、allowlist 精確網域）。雙阻塞：Anthropic key + 定價 seed。

> 源於 PRD-0003 §8.7.3 與 Phase 1.4 guardrail E2E 的 carried follow-up。是 [PRD-0004](../prd/PRD-0004-device-service-observability-alerting.md) 明確排除的 Non-Goal，獨立成本 ADR 處理。**卡使用者提供 Anthropic key**，故為 Proposed（未實作、未驗證）。

## Context

PRD-0003 的 Two-Layer AI Guardrail（§8.7）目前：

- L1 classifier 與 L2 guardrail 各自可獨立設定 provider / model / key（FR-338）。`factory.make_guardrail` 已支援 `mock` / `openai` / `local`。
- 但 G1/G2 實機 E2E 走的是**同一廠商**（L1 + L2 都 OpenAI `gpt-4o-mini`）。

弱點：當 L1 與 L2 同屬一個廠商 / 模型家族時，**單一廠商層級的失效模式**（某個對該家族通用的 jailbreak、廠商端模型更新導致的行為退化、或廠商帳號 / 端點被影響）可能**同時削弱兩層**，使「雙層」退化為「實質單層」。LLMGuardrail 的 deterministic 後盾（MockGuardrail regex）仍在、fail-closed 仍在，但語意層防線的獨立性不足。

Defense-in-depth 原則要求：L2 應可來自**不同廠商**（如 L1 OpenAI + L2 Anthropic），使單一廠商的失效不致同時擊穿兩層語意防線。

`anthropic` 作為 guardrail provider 在 `make_guardrail` 當初被標為 follow-up（未接線）。

## Decision

> 待 Anthropic key 到位後實作；本 ADR 先鎖定方向與契約。

**1. `factory.make_guardrail` 增加 `anthropic` 分支**
- 比照既有 `openai` / `local` 分支，回傳以 Anthropic 模型為後端的 `LLMGuardrail`（雙階段不變：deterministic 後盾 → 模型判語意；fail-closed BLOCK 不變）。
- 預設 model：`guardrail_default_model_anthropic`（建議 `claude-haiku-4-5`，最便宜夠用）。

**2. Config（沿用既有 guardrail_* 模式，無新機密管道）**
- `GUARDRAIL_PROVIDER=anthropic` 啟用；`GUARDRAIL_API_KEY` 放 Anthropic key。
- **fail-closed 啟動語義（security HIGH，精確定義）**：當 `GUARDRAIL_PROVIDER=anthropic` 且 `GUARDRAIL_API_KEY` 空 / 缺時，**整個 device-service 必須在 lifespan startup 拒啟（exit non-zero）**。**不得**沿用 `LLM_API_KEY`（跨廠商 key 不可共用，否則把 OpenAI key 送往 `api.anthropic.com`）、**不得**靜默停用 guardrail、**不得**未經顯式 `GUARDRAIL_PROVIDER=mock` 就降級為 mock-only。此為可測驗收（啟動測試：anthropic + 空 key → service 拒啟）。
- `guardrail_base_url` 仍走 FR-342 allowlist：**精確加入 `api.anthropic.com`（完整網域字串，無 wildcard，port 443）**，比照既有 `api.openai.com` 條目；不得用 `*.anthropic.com`。

**3. 預算計量沿用 FR-340（pricing 為與 key 同級之啟用前置條件）**
- L2 成本仍進 `provider='guardrail'` ledger row、獨立月預算、fail-closed —— 跨廠商不改 FR-340 機制，只是 g_model / pricing 換成 Anthropic 定價。
- **pricing 是 gating blocker（architect/security，非軟性 consequence）**：`claude-haiku-4-5` 定價**必須**先補進 `llm_pricing_json` 或內建表，否則 cost 計 0 → `provider='guardrail'` ledger 永不累積 → **FR-340 預算 fail-closed gate 與 PRD-0004 FR-402 guardrail 告警雙雙靜默失效**（成本硬上限這個安全控制被繞過）。部署無定價資料視為 misconfiguration，須於啟動 fail-closed 警告（同缺 key 處理）。

**4. 驗收：跨-provider 實機 E2E**
- 新增 opt-in 整合測試：L1=OpenAI、L2=Anthropic，跑三情境（乾淨 / 明顯 injection 後盾擋 / 語意 injection 真 L2 擋），證明異廠 L2 仍正確 BLOCK，且 `provider='guardrail'` ledger 以 Anthropic 定價計量。
- 無真 key 則 skip（比照 `test_device_service_guardrail_live.py`）。

## Consequences

**正面**
- L1 / L2 語意防線分屬不同廠商，單一廠商失效不同時擊穿兩層 → 真正的 defense-in-depth。
- 不改 FR-338 / FR-340 既有架構，只擴 provider 分支 + 定價，增量小。

**負面**
- 需維運**兩個廠商帳號 / key / 額度**（成本與 key 管理複雜度上升）。
- L2 延遲取決於 Anthropic 端點，與 L1 不同 SLA。
- 內建 pricing 表需補 Anthropic 模型，否則 cost 計 0（沿用既有 warn）。

**已知風險（殘留）**
- 跨廠商不保證「不同弱點」——兩家若對同一類 prompt 有相似盲點，獨立性仍有限；以 deterministic 後盾 + fail-closed 兜底。
- key 誤用（GUARDRAIL_API_KEY 空時若沿用 OpenAI key 打 Anthropic 端點）→ 啟動驗證須 fail-closed 拒絕，列實作 checklist。

**阻塞 / 後續觸發**
- **雙阻塞（並列，缺一不可啟用）**：(1) Anthropic API key；(2) `claude-haiku-4-5` 定價已 seed。兩者皆到位前維持 Proposed。
- **啟用前 checklist（皆為可測驗收）**：① anthropic + 空 key → 拒啟；② allowlist 僅 `api.anthropic.com`（無 wildcard、443）；③ 定價就位，guardrail ledger 確實以 Anthropic 定價累積；④ 跨-provider 實機 E2E（L1 OpenAI + L2 Anthropic）三情境通過。
- 落地後：更新 `tunable-parameters.md`（guardrail_default_model_anthropic）、`config/device-service.toml`、PRD-0003 §8.7.3 附錄變更註記指向本 ADR、risk-register。
- **與 PRD-0004 之關係**：無**排程**相依，可獨立排程；但**共用 guardrail-ledger / 定價契約**——本 ADR 落地後 PRD-0004 FR-402 即開始計量 Anthropic spend，故 pricing 與「比例分母取 ledger `budget_usd`」（PRD-0004 FR-400~402）兩者須跨文件保持一致。
