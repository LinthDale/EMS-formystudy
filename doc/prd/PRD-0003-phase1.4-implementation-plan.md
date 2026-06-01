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

1. **FR-329 budget HARD CAP — implemented (5e0b86d) + reservation-leak fix (2665012) + §13 tests**
   - **Done**: pre-call estimated-cost **reservation** (`budget_reserve`) under a **budget-namespace `pg_advisory_xact_lock`** (`budget:provider:period`, separate from §8.6.8 `device:` lock) → near-budget single call cannot cross; concurrent workers cannot both pass. **`budget_settle`** reconciles reservation→actual (refund; full refund on fallback). **Reservation never leaks**: `process_message` wraps reserve→classify→apply→settle in try/finally; an unexpected exception after a successful reservation refunds the full reservation. unpriced-model WARNING. §13 tests: near-budget denied, concurrent→exactly-one, settle refund, full refund, **exception-refund (no leak)**, real-provider settle. 185 tests, device_service ~99% (test container).
   - **Remaining caveats (NOT a production guarantee — real-provider enablement)**: NOT run against live Anthropic/OpenAI; cost is an estimate (not real billing); **L2 guardrail `provider='guardrail'` ledger row not yet recorded** (MockGuardrail is free); rare guardrail-post-block-after-L1 path refunds full reservation though L1 spent tokens (minor under-count); the in-`finally` refund itself is best-effort (suppressed on a secondary DB failure). (decision context: local DL-013/14/15 — NOT in git; this plan doc + commits are the tracked record, since `doc/governance/decision-log.md` is gitignored by convention.)
2. **MQTT subscriber reconnect / error branch 測試覆蓋**
   - 現況（保守表述）：`run_subscriber` 已加 defensive reconnect loop + lifespan task done-callback，但 **reconnect 路徑與 per-message error branch 尚無單元/整合測試**（commit 已註明 uncovered）。
   - Must-do：補測試 — (a) broker 斷線觸發 reconnect（可用 fake aiomqtt client 模擬 raise→重試）；(b) 單則訊息 `process_message` 拋例外不殺 loop；(c) done-callback 在 task 異常結束時記 error。

## Phase 1.4 其餘範圍（§12.4）

- ✅ **Human-review endpoint（DONE，batch 1）**：`GET /devices/{id}/human-review` 回 §8.4 digest（讀 `device_review_digests`，不現呼 LLM；system_fallback 亦回 200）。OPS channel；新 `repositories/digest_repo.py`（`get_with_device` 單次 LEFT JOIN 原子取 device-exists+digest，避開讀競態；`get` 為 MCP 預留的 digest-only 取用）；`models.DigestOut` response_model；404 分裝置不存在 / 無 digest。6 integration tests，touched 檔 100% cov（容器量測）。
- **`/ai-feedback` + correction loop（分 3 slice）**：
  - ✅ **2a（DONE）**：`correction_validator.py`（§7.3a 寫入檢查：NFKC→length 30-500→control char→**Cf format char 拒絕**[sec-review H-1/M-1：ZWSP/RTL-override 等不被 NFKC 收斂、可拆解 injection phrase，故一律拒絕]→structural `<>{}\\\``→secret 黑名單→injection phrase 白名單）+ `key_id.py`（`hash_key_id` HMAC-SHA256(salt, api_key)，不存原始 key，FR-345；fail-closed on empty salt/key/version）+ config `audit_hash_salt`(secret,.env)/`audit_salt_version`(TOML)。29→31 validator unit tests + config drift test 改由 SECRET_FIELDS 推導。security-review 通過後合併。
  - ✅ **2b（DONE — corrections 寫入/列出/失效 + 校驗 + 速率限制；FR-330 兩個 action flag 延 2c）**：`correction_repo.py` + OPS `POST /devices/{id}/ai-feedback`、`GET /devices/{id}/corrections`（`active_only` 可選）、`POST /devices/{id}/corrections/{cid}/deactivate`（FR-330 核心 / FR-341）。寫入前套 §7.3a validator（**內容違規回 400**，對齊 FR-330 驗收，非 422）；HMAC `created_by_key_id`（不存原始 key）+ `salt_version`；`prompt_version_at_correction` 由**伺服端 stamp**（`prompt.PROMPT_VERSION`，非 client 傳入）；deactivate body 欄位 `reason`（對齊 PRD §624）。`audit_hash_salt` 缺失：啟動期 WARNING（不硬擋開機，sec-review M-2）+ 寫入點 fail-closed 503（no DB row）。FR-343 per-key-id 30/h、per-device 10/h DB-count 速率限制回 429 + audit log。**FR-330 `rerun_classification` / `demote_to_candidate`：加入 model 但 true 一律回 501（不靜默吞），實際行為與 classify/解凍路徑一起留 2c**（demote 會解凍 human 記錄、需 freeze override，本質屬 2c）。11 corrections integration tests；routes/devices.py + correction_repo.py + models.py 100% cov（容器量測，非 CI/prod 保證）。code-review 後合併。
  - ✅ **2c-retrieval（DONE — FR-331/332 + §8.6.5a + migration 012）**：`correction_context.py`（`build_context`、`device_type_family`[家族=自身，單點可擴充]、`topic_prefix`[前兩段、兩段皆需非空]、`cap_to_prompt_size`[32KB §8.6.5a，**二分搜尋**最大可容前綴，O(log n) render，遵 FR-331 無筆數上限]）+ `correction_repo` `retrieve_relevant`（device/gateway[JOIN devices]/type-family/topic-prefix 聯集，is_active only）/`latest_corrected_device_type`（device→gateway fallback，FR-332 來源）/`mark_applied`（applied_count+last_applied_at，與 apply_outcome 同 tx）。**migration 012**：device_service_ai 得 `device_corrections` SELECT + 欄位限定 UPDATE(applied_count,last_applied_at)（不含 INSERT/DELETE/內容欄位；DB column-priv 強制；user 授權套用 dev DB）。discovery.process_message 接線：retrieve→cap→注入 sanitized→classify(latest_correction_device_type)→summary_source=='llm' 才 mark_applied。code-review WARNING→修 O(n²)（改二分）/mark_applied 同 tx/topic_prefix 硬化/int 強轉後合併。21 corrections/retrieval/context + migration012(3) tests，correction_context+correction_repo 100% cov、discovery 95%。
  - ⏳ **2c-flags**：補 FR-330 `rerun_classification`（即時過 budget gate 重跑分類）/ `demote_to_candidate`（freeze-override 解凍→candidate→可被 AI 重新分類）兩個 flag 的實際行為（目前 501）。（FR-344 大量 deactivate alert 仍歸入下方 audit/observability 批次。）
- **`device_audit_log` 表 + FR-339 告警**：override token（reject/override/delete）、L2 guardrail BLOCK、AI status 推進的 audit 持久化（取代目前的結構化 log line）；連續 BLOCK / 大量 deactivate alert。
- **MCP server**：device-service 自帶 127.0.0.1:8766，AI 通道僅 `list_low_confidence_candidates` / `get_device_digest` / `classify_with_context`（ADR-012）。
- **Grafana panel**：鎖定 4 個（pending count / status distribution / error & latency / cost）。
- **真實跨 provider L2 guardrail E2E**（§8.7.3，production 強制跨 provider，Promotion P-1）。
- **§15.C 文件同步**：`api/openapi.yml`、`doc/operations/容器速查表.md`（容器數 12→13，加 ems-device-service）、操作手冊 — 見 [[feedback_ems_doc_sync]]。

## 流程（不變）
每批 TDD + **合併前 code review agent**（[[feedback_review_before_merge]]）；計畫/決策落 repo 記錄（[[feedback_plans_need_record_doc]]）；測試在 throwaway 容器跑（[[reference_ems_test_runtime]]）。

## 覆蓋率 / 測試的保守表述（沿用）
所報數字為 throwaway `python:3.11-slim` 容器內、device_service 模組之 pytest-cov 量測，**非 CI/production 全面保證**；整合測試在 DB/mosquitto 不可達時會 skip；`tests/Makefile` 的 coverage target 仍只量 simulator（待補 device-service target）。
