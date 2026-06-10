# ADR-021：device_type 閉集政策 — DB 自由 TEXT、應用層夾箝

## Status
Proposed（2026-06-10）

> 對應 [PRD-0006](../prd/PRD-0006-Generic-Measurement-Pipeline-Dynamic-Visualization.md) FR-608/FR-609。相關：PRD-0003 §7.1（device_type 欄位）、§8.5 Parser Matrix 規則 #3、FR-333 output_validator、[ADR-022](ADR-022-narrow-measurement-table.md)。

## Context

PRD-0006 引入 battery / solar_inverter / ev_charger / grid_meter 等新領域，且升格（FR-606/607）會把 AI 產出的 device_type / signals 決定性寫入 registry。需要決定 device_type 的合法值集合由誰強制：DB CHECK、enum type、還是應用層。

現況：`devices.device_type` 為**自由 TEXT**（無 CHECK / enum）；合法集合僅存在於 prompt 的閉集宣告（electricity / temperature / pressure / motor / valve / hvac / unknown）；`output_validator` 只驗安全字元、**不** enforce 此 enum——真實 LLM 可吐出任意型別字串而 registry 照存。

## Decision

**1. DB 維持自由 TEXT**：`devices.device_type` 不加 CHECK、不建 enum type。

**2. 閉集在應用層強制（兩道，皆決定性）**：
- **prompt 閉集宣告**：`prompt.py` 的 `DEVICE_TYPES` 為唯一合法集合宣告，prompt 明令 LLM 只能從中選擇；變更集合須升 `PROMPT_VERSION`（cache key 連動，FR-316）。
- **output_validator / 升格夾箝**（PRD-0006 FR-608）：LLM 回應與升格路徑對 device_type 夾箝——不在閉集 → 一律寫 `'unknown'`（**不 raise、不炸交易**），原值記入 metadata 供人工檢視。

**3. 本批擴充**：`DEVICE_TYPES += battery, solar_inverter, ev_charger, grid_meter`；Parser Matrix 規則 #3 之 domain→預設 type 改資料驅動（solar→solar_inverter、storage→battery；未列 domain 仍 unknown），對照表入 config（與 PRD-0006 FR-610 同一治理：device-service.toml + tunable-parameters 登錄）。

### 否決方案
- ❌ **DB CHECK / enum type**：每加一型別都要 migration（與 freeze / 最小權限治理摩擦）；CHECK 違反會 abort 整筆 confirm / 升格交易，把「AI 輸出品質問題」升級成「寫入故障」——fail mode 錯誤。
- ❌ **完全自由（無閉集）**：AI 可發明任意型別，下游（dashboard 變數鏈、路由 config、PRD-0005 UI）失去可枚舉性；與 AI Bounded Autonomy 哲學牴觸。

## Consequences

**正面**
- 新型別上線 = 改 `DEVICE_TYPES` + 升 PROMPT_VERSION + 對照表 config，**零 schema 變更**。
- 不合法值降級為 `'unknown'`（安全預設，進人工佇列語意不變）；DB 不成為 AI 輸出的硬故障面。

**負面 / 風險**
- `'unknown'` 為唯一逃生值；dashboards / 路由對 unknown 須有預設行為。
- 應用層可被繞過（直接 SQL 寫怪值）——僅 OPS role 可達，且 registry CRUD 全走 audit；接受。

**後續觸發**
- 落地時同步：`prompt.py`、`output_validator.py`、topic_parser 對照 config、tunable-parameters.md；閉集每次變更於本 ADR 附錄登記。
