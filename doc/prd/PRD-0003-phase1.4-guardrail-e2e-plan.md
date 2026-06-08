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

### ✅ G2 — 真模型 live E2E（DONE，merged dev d688f6d）
**完成**：opt-in 整合測試 `tests/integration/test_device_service_guardrail_live.py`（無真 key 自動 skip），對真 OpenAI（L1 gpt-4o-mini + L2 gpt-4o-mini）過實際 Classifier pipeline 三情境**實跑通過**：(1) 乾淨電力樣本→真 L1 分類 electricity@0.95、L2 pre+post PASS→summary_source=llm；(2) 明顯 injection→deterministic 後盾 pre-block→system_fallback、攻擊目標 motor 沒漏出；(3) **語意 injection（規避靜態 marker）→真 L2 模型擋下（instruction_hijack）**→證明 model-backed L2 擋得住 regex 漏接的攻擊。**live E2E 抓到並修掉真實 bug**：`_summarize_output` 用 `|`/`;` 當分隔符（本身是 shell metachar）→ guardrail 自己的「output 含 shell metachar」規則誤判、把每筆乾淨分類都 post-block→改回傳結構化 dict（JSON 嵌入，真 metachar 仍逐字可偵測）。fake-client 單測沒抓到、真模型才現形。加 regression 單測鎖死。code-review APPROVE（0 CRIT/HIGH，MED/LOW 已修）。device_service unit 251 passed + live 3 條。成本約數美分。
<details><summary>原計畫</summary>
- key 放 `.env`（gitignored）：`LLM_PROVIDER=openai` + `LLM_API_KEY=sk-...` + `GUARDRAIL_PROVIDER=openai`（共用 `LLM_API_KEY`）。
- E2E（throwaway 容器或本機，連真 OpenAI）：
  - injection prompt → **L2 pre BLOCK** → L1 不被呼叫 → digest `summary_source='system_fallback'` → device 不 confirmed、不寫越權內容（FR-336）。
  - 模擬 L1 惡意 output（或自然樣本）→ **L2 post** 行為正確（FR-337）。
  - 乾淨樣本 → L2 pass → 正常分類。
  - no-leak：client/digest 不含 stack trace / 內部細節。
- 成本：每筆分類多 2 次 L2 call、小模型短 prompt，E2E 只跑少量樣本，預估 < $0.05。
</details>

### Follow-up（本計畫後，production enable 前必做）
- **FR-340 L2 budget metering**：見下方「## FR-340 實作計畫」（進行中）。
- **跨-provider**：`make_guardrail` 支援 `anthropic`，L1 OpenAI + L2 Anthropic 真·defense-in-depth E2E（需 Anthropic key）。

## FR-340 L2 budget metering — 實作計畫

> PRD §8.7.4 / FR-340：L2 token 用量寫入 `llm_budget_ledger` 獨立 `provider='guardrail'` row；budget gate fail-closed 同套 L2；**L2 budget 100% → 不可繼續 classify（L1 也停）→ 全走 system_fallback**。這是 real-provider guardrail 上線的最後 blocker。

### Slice 1 — usage plumbing（不動 budget，純接線）
- `GuardrailVerdict` 加 `usage: dict|None`（{input_tokens, output_tokens}）。
- `LLMGuardrail._judge` 從回應抽 usage（mirror openai_provider._extract_usage）並掛到 verdict；deterministic 後盾擋下 / MockGuardrail → usage None（免費）；fail-closed 例外路徑 usage None。
- `Classifier`：累加 pre+post 的 usage → 新 `Outcome.guardrail_usage`（含各 fallback 路徑，pre 擋下也帶已花的 pre usage）。
- unit tests（fake client 帶 usage）；預設 mock → guardrail_usage None，行為不變。

### Slice 2 — budget gate + ledger（fail-closed）
- config 加 `guardrail_monthly_budget_usd` + `guardrail_reserve_input_tokens`（可調，入 TOML/registry）。
- `classify_under_budget`：對 `provider='guardrail'` reserve 最壞情況（pre+post 共 2 call）→ 傳 `guardrail_ok` 給 classifier；classify 後依 `Outcome.guardrail_usage` settle（cache hit → 不重複計、全額退；leak-safe finally 退 reserve）。pricing 以 guardrail_model 查表。
- `Classifier.classify` 加 `guardrail_ok`：False → `fb("guardrail_budget_exhausted")` **在 pre/L1 之前**（FR-340：L1 也停）。
- 整合測試（DB）：guardrail ledger row 寫入、budget 100% → 全 fallback、fallback/cache → 退款；L1 與 guardrail 兩 row 獨立。
- docs：tunable-parameters + TOML + 操作手冊（guardrail budget 與 alert 說明）。
- 註：guardrail budget 100% 的 Telegram alert 投遞與既有 L1 80% alert 一樣走 Grafana-over-ledger，屬 observability 批次（與現有未接線狀態一致），本片只保證 **fail-closed 行為 + ledger 記錄**。

### 流程
每片 TDD + 合併前 code-review；fail-closed 一律往 fallback；不破壞既有 L1 budget 路徑（純加 guardrail 平行軌）。

## G2 live E2E — 執行證據 / promotion gate

live 測試是 **opt-in**（無真 key 自動 skip），故不在一般 CI 跑。要作為 promotion gate（宣稱「最新程式仍過真模型測試」）時，在 repo root 跑下列指令並保留輸出：

```bash
set -a && . ./.env && set +a   # 需 .env: LLM_PROVIDER=openai / GUARDRAIL_PROVIDER=openai / LLM_API_KEY=sk-...
docker run --rm -e LLM_PROVIDER -e LLM_API_KEY -e LLM_MODEL -e GUARDRAIL_PROVIDER \
  -e GUARDRAIL_MODEL -e GUARDRAIL_API_KEY -v "$PWD":/app -w /app ems-device-service:latest \
  bash -c "pip install -q pytest pytest-asyncio psycopg2-binary && \
    python -m pytest tests/integration/test_device_service_guardrail_live.py -v"
```

最新通過證據（2026-06-08，commit 上承 d688f6d + 本輪 review 修正）：
- `test_clean_sample_passes_both_real_models` PASSED — 真 L1 分類 `electricity`、`new_status=confirmed`（confidence > threshold）、L2 pre+post PASS、no-leak。
- `test_obvious_injection_blocked_to_fallback` PASSED — 後盾 pre-block → system_fallback、攻擊目標 `motor` 未漏出。
- `test_semantic_injection_caught_by_real_model` PASSED — 規避 regex 的語意攻擊由真 L2 模型擋下（`instruction_hijack`）。
- 連同 16 條 guardrail 單測，共 **19 passed**（真 OpenAI，gpt-4o-mini×2，成本約數美分）。

> 註：promotion 到 production 前仍需 **FR-340 L2 budget metering**（見 Follow-up）。目前 real guardrail 的 L2 成本 uncapped，故僅宣稱「G2 live E2E 完成」，**不**宣稱 guardrail production-ready。

## 流程（不變）
每片 TDD + **合併前 code-review agent**（[[feedback_review_before_merge]]）；記錄落本檔（[[feedback_plans_need_record_doc]]）；測試在 throwaway 容器（[[reference_ems_test_runtime]]）；可調參數集中（[[feedback_tunable_params_registry]]）。

## 安全要點
- guardrail security prompt **hardcoded**、user/input 不可影響（[[feedback_two_layer_ai_guardrail]]）。
- fail-closed 一律往 BLOCK（never auto-confirm 未檢查結果）。
- reasoning 入 audit 仍走 `_MAX_REASON_LEN` 截斷（防未來 LLM guardrail echo 攻擊內容）。
- guardrail_api_key 為 secret，只進 .env、SECRET_FIELDS redact、不進 TOML。
