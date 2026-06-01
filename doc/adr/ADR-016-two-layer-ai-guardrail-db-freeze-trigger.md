# ADR-016：Two-Layer AI Guardrail + DB Freeze Trigger

## Status
Accepted（2026-05-29）

> 來源：PRD-0003 §8.7 / §8.6.2；DL-005 引入雙層 guardrail + DB freeze trigger（S1/S2 三層防禦）。

## Context

§8.6 bounded autonomy 讓 AI 可自動改 registry 並注入人類 corrections 進 prompt。注入點（`human_explanation` / corrections）即是 prompt injection 攻擊面。單靠 sanitizer + output validator（字串規則）擋不住語義級 jailbreak（如「ignore previous instructions」「跳出 delimiter」）。

同時，若 device-service 容器被 RCE，攻擊者可直接用 DB 連線 UPDATE 凍結紀錄，繞過所有應用層防護。

需要：(1) 語義級的 AI 守衛；(2) 即使 RCE 也擋得住的 DB 層防線。

## Decision

採 **雙層 AI Guardrail（L1 分類 + L2 守衛）+ DB Freeze Trigger**：

### Two-Layer Guardrail（§8.7）
- **L2 GuardrailProvider** 介面與 `LLMProvider` 完全分離；**不**共用 prompt template、**不**接受任何外部 input 影響其 system prompt（hardcoded）
- **流程**：SanitizedSample → **L2 pre-check**（看 prompt 查 injection）→ PASS → **L1 classifier** → **L2 post-check**（看 L1 output 查越界 / 逃逸）→ PASS → Output Validator → 寫 DB
- 任一 L2 BLOCK → 立即走 system_fallback、`last_error='guardrail_blocked'`、**不算 budget consumed**（FR-336/337）
- **介面**：`check_input(sanitized, rendered_prompt)` / `check_output(sanitized, l1_response, rendered_prompt)` → `GuardrailVerdict{decision, threat_category, reasoning<=200字, confidence}`
- **威脅分類**：`prompt_injection` / `instruction_hijack` / `output_command` / `scope_escape` / `other`
- **獨立 env**：`GUARDRAIL_PROVIDER` / `GUARDRAIL_MODEL`（預設 `claude-haiku-4-5`）/ `GUARDRAIL_API_KEY`，切換不影響 L1（FR-338）
- **跨 provider 取捨**：production 強烈建議 L1 ≠ L2 provider（真正 defense in depth，L1 被 jailbreak ≠ L2 被 jailbreak）；Phase 1 dev 同 provider 可接受，但 production promotion 強制跨 provider（P-1）
- **獨立 budget**：L2 token 寫 `llm_budget_ledger` `provider='guardrail'` row；L2 budget 100% → L1 也停（FR-340）
- **audit + alert**：BLOCK 寫 audit（phase / threat_category / l1_input_hash / l1_output_hash）；連續 5 次 BLOCK 同 device / 1h → Telegram alert（FR-339）

### 寫入端 allow-list（S2）
- `human_explanation` / `deactivation_reason` 寫入時嚴格 allow-list：含 `<` `>` `{` `}` `\` / 控制字元 / `ignore previous` regex → 400
- **NFKC normalize 再比對**（v6 WARN-1）：防全形字元（`＜` U+FF1C / `｛`）繞過

### DB Freeze Trigger（S1，migration 010）
- 建 `device_service_ai` / `device_service_ops` 兩個 DB role
- freeze trigger：**兩個 role 預設都擋**凍結紀錄主欄位 UPDATE；OPS 合法 endpoint 須在 transaction 開頭 `SET LOCAL device_service.freeze_override='<request_id>'` 才放行（顯式 GUC token）
- `device_service_ai` 無 measurements SELECT 權限（取樣本走 OPS pool）
- 即使容器 RCE 直接 UPDATE 凍結紀錄 → DB raise exception

## Consequences

**正面**
- 語義級守衛擋住字串規則擋不住的 jailbreak
- L2 BLOCK 不計 budget → 攻擊者無法靠觸發守衛燒錢
- DB freeze trigger 是「應用層被攻破後的最後防線」（縱深防禦）
- L1/L2 介面分離 + 獨立 budget → 可獨立切換、獨立監控

**負面**
- 每次 classification +2 次 L2 call（pre + post），延遲 +1~3s、成本 +（每筆 < $0.001）
- 跨 provider 需維護兩組 API key / 額度
- freeze override GUC token 機制要求 OPS endpoint 正確 `SET LOCAL`，遺漏會誤擋合法操作

**已知風險（R-026）**
- Phase 1 dev 同 provider 時，L1 jailbreak 期間可能同時騙過 L2 → 殘留風險，靠 production 跨 provider（P-1）+ 歷史 corrections 批次 recheck（P-5）緩解
- freeze override token 若被 OPS 路徑誤用 / 洩漏 → audit row 記 request_id 可追

**後續觸發**
- Promotion Checklist P-1（強制跨 provider）/ P-5（歷史 corrections 批次 L2 recheck）
- DB role 連線池機制見 ADR-017
- salt rotation（FR-345）保護 audit hash lineage
