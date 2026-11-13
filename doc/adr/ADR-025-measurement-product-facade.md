# ADR-025：Per-device 量測 PRODUCT facade（產品語意，取代 PostgREST operator 直通）

## Status

Proposed（2026-06-16）

源自 [PRD-0005](../prd/PRD-0005-ems-frontend.md) §8.2 / §9.3（review P2）BFF 實作（`services/bff/`）。精煉 PRD-0005 §8.2 量測路由原則、**取代** §8.2 中「量測經 BFF 但仍以 domain 為 key、透傳 PostgREST 參數」的殘留作法。與 [ADR-023](./ADR-023-bff-session-and-role-channel-key-authz.md)（session / role→channel-key）、[ADR-022](./ADR-022-narrow-measurement-table.md)（窄表量測儲存）並存不衝突。

## Context

PRD-0005 §9.3 已鎖定「前端一律經 BFF、瀏覽器不直連 PostgREST」。P1 骨架先落地的量測路由為 `GET /api/measurements/{domain}`：BFF 仍把 **PostgREST operator 值**（`device_id=eq.<id>`、`time=gte.<ts>`、`order=time.desc`）原封不動從瀏覽器查詢字串透傳到 PostgREST view。問題：

- **抽象洩漏**：瀏覽器必須知道 PostgREST 的 operator 文法（`eq.` / `gte.` / `<col>.desc`）與底層欄位名（`time`），等於把儲存層細節推到最不可信的一端。前端與後端儲存緊耦合，未來換儲存（如 ADR-022 窄表 `signal_measurements` unified view）即破壞前端契約。
- **domain 是錯的 key**：前端真正持有的識別子是 `device_id`，不是 domain。要前端先知道「某設備屬 electricity 還是 factory」才會挑對 view，這個 domain 知識本應由後端依設備註冊資料決定。
- **輸入面過寬**：透傳式參數讓校驗停在「字元集 + 上限」層級（見既有 `routes/measurements.py`），無法以產品語意（時間是否合法 ISO8601、排序是否 asc/desc）收斂。

需要一個「以 device 為中心、只暴露產品語意、伺服器端翻譯成儲存查詢」的 facade，前端代理（frontend agent）將同步對此契約開發。

## Decision

1. **新增 per-device 量測 facade**：

   ```
   GET /api/devices/{device_id}/measurements
       ?since=<ISO8601>&limit=<1..1000, default 100>&order=<asc|desc, default desc>
   ```

   瀏覽器只說產品語意（`since` / `limit` / `order`）；**永不**構造 PostgREST operator。BFF 伺服器端把 `since→time=gte.<ts>`、`device_id→device_id=eq.<id>`、`order→time.<asc|desc>`、`limit→limit` 翻譯後才打 PostgREST。（`bff/routes/device_measurements.py`）

2. **device→domain 解析以 `gateway_id` 為唯一權威信號**：BFF 先以 OPS 通道讀 device-service `GET /devices/{id}` 取得設備記錄，再用 `gateway_id` 對應量測 view —— `ems-gateway → /electricity_measurements`、`kc-gateway`/`kc-ingest → /factory_measurements`。此映射**刻意鏡像** device-service 既有的 `measurements_repo.table_for_gateway`，確保 BFF 與後端對 electricity/factory 切分一致。不可解析的 gateway → **404**（絕不臆測 domain）。（`bff/domain.py`）

   - 不採 `device_type` 作 domain 信號：`device_type` 為自由 TEXT（ADR-021 閉集僅應用層夾箝），且一個 domain 內含多種 type（factory 含 temperature/pressure/motor/valve…）。`gateway_id` 才是資料管線的真實歸屬。

3. **facade 為 OPS-gated**：device→domain 解析必須讀 device 記錄，而 device-service `/devices/{id}` 僅開在 OPS 通道（§8.1：status/gateway 屬特權欄位）。依 ADR-023 role→≤1 key 不可借用，READONLY/INGEST 無 OPS 通道，故對此 facade 回 **403**。量測讀取 hop 本身仍 **不花任何 key**（web_anon view，§9.3 / ADR-023 §4）。

4. **保留 legacy `GET /api/measurements/{domain}` 但標記 deprecated/internal**：前端（FR-520/521）改用 per-device facade；舊路由於 deprecation window 內維持可用（內網 / legacy caller），程式註記「不得擴充」。不在本 ADR 立即移除，避免破壞既有消費者。

5. **輸入校驗以產品語意收斂**（boundary validation，deny-by-default）：`since` 須通過嚴格 ISO8601（`datetime.fromisoformat`）；`limit` 限 `1..measurements_max_limit`（預設上限 1000），未給套用 `measurements_default_limit`（預設 100）；`order` 限 `asc|desc` allowlist；未列名查詢參數一律 422；`device_id` 先過 FR-322 regex 才動上游。

## Consequences

- ＋ 瀏覽器零 PostgREST 文法知識；儲存層可換（如 ADR-022 unified view）而不破壞前端契約 —— 抽象邊界回到後端。
- ＋ domain 由後端依 `gateway_id` 決定，前端只需 `device_id`；與 device-service 共用同一映射，無雙真相。
- ＋ 校驗以產品語意收斂（ISO8601 / 排序 allowlist / limit 邊界），輸入面比透傳式更窄。
- ＋ 維持 ADR-023 全部保證（role→≤1 key、量測 hop 不花 key、key 永不對瀏覽器可見含錯誤路徑）。
- － facade 多一次 device-service 往返（解析 domain）才查量測；可接受（量測卡片非高頻、device 記錄可未來加快取）。
- － facade OPS-gated：READONLY/INGEST 無法用 per-device facade（其 domain 解析需 OPS 讀）；若未來需放寬給 READONLY，須提供「不需特權讀即可解析 domain」的途徑（如公開的 device→domain 對照 view），屬後續 ADR。
- － 兩條量測路由並存於 deprecation window；移除 legacy 路由須待前端完全遷移後另議。
- 對應威脅模型：強化 `doc/governance/threat-model.md` T-08（PostgREST 唯一瀏覽器面 = BFF，operator 不再外露）；沿用 TB-6 / T-24（role→key）/ T-25（上游錯誤不洩漏）既有緩解，未新增資產或邊界。
- 對應可調參數：`doc/governance/tunable-parameters.md` BFF 區既有 `measurements_default_limit`（100）/ `measurements_max_limit`（1000）即本 facade 的 limit 預設與上限；本 ADR **未新增**可調參數（沿用既有兩項）。
- 對應 PRD：精煉 PRD-0005 §8.2 量測契約原則、取代 §8.2 「domain-key + operator 透傳」之量測路由註記；不變動 device-service 後端契約（本 facade 純屬 BFF 對外 facade 面）。

> 翻譯映射摘要（伺服器端，瀏覽器不可見）：
>
> | 產品參數（瀏覽器） | PostgREST 參數（BFF→PostgREST） |
> |---|---|
> | （路徑）`device_id` | `device_id=eq.<device_id>` |
> | `since=<ISO8601>` | `time=gte.<ISO8601>`（未給則不加時間過濾）|
> | `order=asc\|desc` | `order=time.asc\|time.desc` |
> | `limit=<1..1000>` | `limit=<同值>`（未給套 default 100）|
