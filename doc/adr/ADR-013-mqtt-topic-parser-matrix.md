# ADR-013：MQTT Topic Parser Matrix v3（deny-by-default）

## Status
Accepted（2026-05-29）

> 來源：PRD-0003 §8.5；DL-002（v1 matrix）、DL-003（v3 deny-by-default 7 條準入）。對應 ADR-007（topic 命名規範）。

## Context

device-service 被動訂閱 MQTT 偵測未登錄裝置。若訂閱過寬（`#`）或解析過鬆，會：

1. 把雜訊 topic 當成裝置狂建 candidate
2. 被惡意 / 畸形 payload 攻擊（超大 payload、超長 id、特殊字元注入）
3. OT 設備被植入韌體後，透過畸形 topic 攻 IT 端 parser（R-022）

需要一個白名單式（deny-by-default）的解析矩陣。

## Decision

採 **Parser Matrix v3 + deny-by-default 7 條準入規則**：

- **限定訂閱層級**（不訂 `#`）：
  - `ems/+/+/measurements`（兩層 wildcard）
  - `factory/sensor/+`（一層 wildcard）
  - 其餘通配（`factory/#`、`#`）一律禁止
- **deny-by-default 7 條準入檢查**（任一未過即丟訊息 + 對應 metric，不建 candidate）：
  1. topic 必須命中 Matrix 規則 #1–#4，否則 `unmatched_topic_total`（FR-327）
  2. `device_id` / `sensor_id` 通過 regex `^[a-zA-Z0-9_-]{1,64}$`，否則 `mqtt_invalid_id_total`（FR-322）
  3. payload size ≤ 16 KB，否則 `mqtt_oversized_payload_total`（FR-323）
  4. 解析後欄位數 ≤ 64，否則 `mqtt_oversized_fields_total`（FR-324）
  5. 全域 candidate 建立速率 ≤ 60/min，超出排隊 + `candidate_rate_limited_total`（FR-325）
  6. 同 source_topic 60s 內已建 → 跳過、僅 update `last_seen_at` + `mqtt_dedupe_skipped_total`（FR-326）
  7. 規則 #4 命中即忽略（明文化，W2）
- **legacy mapping 與 ADR-007 對應**：`factory/sensor/temp_01 -> sensor-001`、`factory/sensor/temp_02 -> sensor-temp-02`（normalize）
- `src/topic_parser.py` 覆蓋率 ≥ 95%

## Consequences

**正面**
- deny-by-default → 未知 / 畸形 topic 預設不處理，攻擊面小
- 每條 deny 規則有獨立 metric，可觀測攻擊 / 誤設定
- 限定 wildcard 層級避免訂 `#` 引發的雜訊風暴

**負面**
- 新增合法 topic 模式須改 parser + 測試（不能靠寬鬆訂閱自動吸收）
- legacy mapping 為硬編碼對應，需隨既有裝置調整

**已知風險**
- OT 端被植入後送畸形 topic（R-022）→ 7 條準入 + regex + size cap 為第一道防線

**後續觸發**
- ingest webhook 來源（Phase 2）走 INGEST key，不經此 MQTT parser
- 新 topic 模式 → 更新 parser matrix（本 ADR 可加註，規則大改走新 ADR）
