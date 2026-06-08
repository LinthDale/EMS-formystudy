# PRD-0003 Phase 1.4 — 真實 L2 Guardrail (same-provider) E2E 計畫

> 記錄文件（[[feedback_plans_need_record_doc]]）。對應 PRD §8.7、FR-336/337/338/339/340、ADR-016、Promotion P-1。
> 使用者定調（2026-06）：**先做同-provider 真模型 E2E，跨-provider（L1 OpenAI + L2 Anthropic）留 follow-up**。

## 背景 / 問題

目前 L2 guardrail 只有 `MockGuardrail`（hardcoded regex/字串比對，免費、無模型），且在 `main.py` / `mcp_server.py` 直接硬編注入。後果：

- 真正擋攻擊那層只認得寫死的字串（`"ignore previous"`、`DROP TABLE`…），擋不了同義改寫 / 混淆 / 語意層攻擊（§8.7.2 要求的「output 與資料形狀不符」這種需理解的判斷做不到）。
- 沒有 `GUARDRAIL_PROVIDER/MODEL/API_KEY/BASE_URL` 設定（FR-338 未接線）。
- L2 不消耗 budget → `llm_budget_ledger` 的 `provider='guardrail'` row 從未寫入（FR-340 未做）。

→ 「真實 provider + L2 guardrail」**不能宣稱 production-ready**。本計畫把它補成真模型雙層守衛並用 E2E 驗證。

## 切片

### ✅ G1 — 真實 LLMGuardrail provider（DONE，merged dev 4c2d25d，**不需 key**）
**完成**：llm_guardrail.py + make_guardrail + guardrail_* config + main/mcp 注入 + [guardrail] TOML + tunable 註冊表 + 15 unit tests。code-review 兩輪（0 CRITICAL）：HIGH-1 delimiter injection 修法改用 **JSON envelope 結構隔離**（json.dumps content 當字串值，引號/換行轉義，攻擊者無法偽造收尾 delimiter break out；模型仍讀得到轉義後文字）——含 regression 測試；另修 MED-1/2/3（check_output fail-closed 測試、inner exception DEBUG log、api-key fallback WARNING）、LOW-1/2/3（reasoning 截斷、factory strip、config field_validator）。device_service unit 250 passed。reviewer 確認 safe to merge（殘留語意層影響風險為任何 model-backed guardrail 固有、非 delimiter 層可解）。
<details><summary>原計畫</summary>
- **新檔 `llm/llm_guardrail.py`**：`LLMGuardrail`，雙階段防護——(1) 先跑 `MockGuardrail` deterministic 規則當免 token 後盾（known injection/command 直接擋）；(2) 通過才呼叫**獨立的 guardrail 模型**判語意層攻擊（§8.7.2 hardcoded security prompt，user/input 不可改）。**fail-closed**：任何 model/parse/network error → BLOCK（→ system_fallback），守衛掛掉絕不放行未檢查的分類。
- **`llm/factory.py` 加 `make_guardrail(provider, ...)`**：`mock` → MockGuardrail；`openai`/`local` → LLMGuardrail（OpenAI-compatible client，可注入測試 client）。`anthropic` 守衛 = 跨-provider follow-up。
- **`config.py`**：加 `guardrail_provider="mock"`（預設不變行為）、`guardrail_model`、`guardrail_api_key`（空→沿用 `llm_api_key`）、`guardrail_base_url`、`guardrail_default_model_openai="gpt-4o-mini"`、`guardrail_max_output_tokens=256`。`SECRET_FIELDS += guardrail_api_key`；FR-342 base_url 驗證同樣套 `guardrail_base_url`。
- **`main.py` / `mcp_server.py`**：改用 `make_guardrail` 注入；若 `guardrail_provider != mock` 啟動印 WARNING：「L2 budget metering 尚未實作（FR-340），真實 guardrail 的 L2 成本目前 UNCAPPED」。
- **unit tests** `tests/unit/test_device_service_llm_guardrail.py`：注入 fake OpenAI client，驗 deterministic 後盾先擋（不呼叫模型）/ 模型回 block→BLOCK / 模型回 pass→PASS / 壞 JSON→fail-closed BLOCK / network error→fail-closed BLOCK / output phase summary 正確。**不打真 API**。
- 驗收：classifier 行為不變（預設 mock）；新模組高覆蓋；code-review 0 CRIT/HIGH 後 merge dev。
</details>

### G2 — 真模型 live E2E（**需 GPT key**，NEXT）
- key 放 `.env`（gitignored）：`LLM_PROVIDER=openai` + `LLM_API_KEY=sk-...` + `GUARDRAIL_PROVIDER=openai`（共用 `LLM_API_KEY`）。
- E2E（throwaway 容器或本機，連真 OpenAI）：
  - injection prompt → **L2 pre BLOCK** → L1 不被呼叫 → digest `summary_source='system_fallback'` → device 不 confirmed、不寫越權內容（FR-336）。
  - 模擬 L1 惡意 output（或自然樣本）→ **L2 post** 行為正確（FR-337）。
  - 乾淨樣本 → L2 pass → 正常分類。
  - no-leak：client/digest 不含 stack trace / 內部細節。
- 成本：每筆分類多 2 次 L2 call、小模型短 prompt，E2E 只跑少量樣本，預估 < $0.05。

### Follow-up（本計畫後，production enable 前必做）
- **FR-340 L2 budget metering**：`Outcome` 加 `guardrail_usage`、classifier 收集 pre+post token、`classify_under_budget` 對 `provider='guardrail'` reserve/settle + budget 100% fail-closed（L1 也停、全 fallback）。
- **跨-provider**：`make_guardrail` 支援 `anthropic`，L1 OpenAI + L2 Anthropic 真·defense-in-depth E2E（需 Anthropic key）。

## 流程（不變）
每片 TDD + **合併前 code-review agent**（[[feedback_review_before_merge]]）；記錄落本檔（[[feedback_plans_need_record_doc]]）；測試在 throwaway 容器（[[reference_ems_test_runtime]]）；可調參數集中（[[feedback_tunable_params_registry]]）。

## 安全要點
- guardrail security prompt **hardcoded**、user/input 不可影響（[[feedback_two_layer_ai_guardrail]]）。
- fail-closed 一律往 BLOCK（never auto-confirm 未檢查結果）。
- reasoning 入 audit 仍走 `_MAX_REASON_LEN` 截斷（防未來 LLM guardrail echo 攻擊內容）。
- guardrail_api_key 為 secret，只進 .env、SECRET_FIELDS redact、不進 TOML。
