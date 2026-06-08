# ADR-015：AI Bounded Autonomy + Correction Loop

## Status
Accepted（2026-05-29）

> 來源：PRD-0003 §8.6；DL-004 引入 Bounded Autonomy（取代早期「AI 只描述世界」過嚴詮釋）、DL-005 凍結集合擴充 + JSON 注入。

## Context

早期 review 一度將 AI 通道限制為「只能描述世界、不能改 registry」。但這與 G2/G3（AI 自動分類 + 信心 > 0.9 自動 confirmed）矛盾——自動推進 candidate->confirmed 本就是 AI 的本職。

真正要防的不是「AI 改 registry」，而是「AI 覆寫人類已介入過的決策」與「分類路徑被注入污染」。需要一個有邊界的自治模型 + 人類修正回饋的閉環。

## Decision

採 **Bounded Autonomy + Correction Loop**：

### 自治邊界（§8.6.1 權限矩陣）
- AI **可**：寫 `ai_*` 欄位、寫 review digest、自動推進 `candidate -> confirmed`（信心 > 0.9 + 無 correction 衝突 + L2 PASS + 持有 advisory lock）
- AI **不可**：`confirmed -> candidate/maintenance/retired`、override device_type/signals、提交 ai-feedback、budget extend（全歸 OPS）

### 凍結規則（§8.6.2）
- 凡 `classified_by IN ('human', 'manual_override', 'migration_backfill')` 的紀錄（含既有 sim-001 / plc-001 / sensor-001）：AI **不得** mutate `device_type` / `device_signals` / `status`；**仍可**更新 `last_seen_at`
- 偵測 signal shape drift（新欄位 / 缺失 / value range 偏移 > 30%）→ 寫 `metadata.drift_detected_at` + alert，**不**自動轉狀態（FR-335）
- **DB 層強制**：不僅應用層自律，migration 010 建 freeze trigger，`device_service_ai` role 對凍結紀錄 UPDATE 主欄位即 raise exception（見 ADR-016，即使容器 RCE 也擋）

### Correction Loop（§8.6.3）
- 人類發現 AI 誤判 → `POST /ai-feedback`（OPS only）寫 `device_corrections`（永久保留），含 `verdict` / `corrected_*` / `human_explanation`（30–500 字）/ `rerun_classification` / `demote_to_candidate`
- 未來相似 candidate 分類前：retrieval 所有「相關」corrections（同 gateway_id / 同 device_type 家族 / 同 topic prefix，**無筆數上限**）→ sanitize → 注入 prompt
- **注入格式採 JSON 結構**（DL-005，取代 v4 XML 標籤）：corrections 以 JSON object array 給 LLM，降低標籤逃逸風險
- **衝突偵測**（FR-332）：LLM 回的 device_type 若與最近 correction 的 `corrected_device_type` 不同 → `metadata.correction_conflict=true` + **強制留 candidate**（不論信心多高）
- **Prompt size 緊急斷路器**（W-2）：注入超 32 KB → LRU 截斷 + metric
- **單筆 correction 毒化緩解**（W-B）：`device_corrections.is_active` + OPS `/corrections/{cid}/deactivate`；deactivate 後不再注入

## Consequences

**正面**
- AI 自治與人類權威各有明確邊界，不再二選一
- 人類修正可累積為 AI 的長期記憶（correction loop），相似裝置越分越準
- 衝突偵測確保「人類教過的事」AI 不會用高信心強行覆蓋
- 凍結規則 + DB trigger 保護既有 production 裝置不被 Phase 1 AI 動到

**負面**
- correction retrieval + 注入增加每次 classification 的複雜度與 prompt 長度
- 無上限注入需 prompt size 斷路器兜底
- corrections 永久保留 → 需 promotion checklist 審計（P-2）防注入殘留

**已知風險**
- 惡意 / 誤導 correction 污染未來分類 → is_active 開關 + 大量 deactivate alert（FR-344）+ L2 guardrail（ADR-016）多層緩解
- 同 provider 期間寫入的污染 corrections 影響 production → Promotion Checklist P-2/P-5 強制審計 + 批次 L2 recheck

**後續觸發**
- correction 注入內容須先過 L2 guardrail pre-check（ADR-016）
- ai-feedback rate limit（FR-343）、salt rotation（FR-345）
