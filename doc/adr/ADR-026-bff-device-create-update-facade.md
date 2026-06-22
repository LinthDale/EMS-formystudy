# ADR-026：BFF 設備 create/update facade（FR-502 人工兜底；不暴露 hard DELETE）

## Status

Accepted（2026-06-18）

源自 [PRD-0005](../prd/PRD-0005-ems-frontend.md) §6（FR-502）/ §8.1（device proxy surface）。補齊 PRD-0005 §8.1 facade 原列「read + confirm/override/reject/corrections」中**未涵蓋的 create/update**。與 [ADR-023](./ADR-023-bff-session-and-role-channel-key-authz.md)（session / role→channel-key）、[ADR-025](./ADR-025-measurement-product-facade.md)（量測 facade）、[ADR-010](./ADR-010-device-state-machine.md)（設備狀態機）並存不衝突；服務於 [PRD-0003](../prd/PRD-0003-Device-Registry-Auto-Discovery.md) 自動發現的人工兜底場景。

## Context

PRD-0003 的設備靠**自動發現**（MQTT topic / Modbus topology）建立並由 AI 分類。但自動路徑會出錯或漏掉：

- AI 分類可能**錯**（錯 `device_type`、錯 domain）或**漏**（拓樸未涵蓋的設備、離線時段加裝的設備）。
- 既有的 confirm / override / reject / correction 只能**修正已存在的候選**；無法處理「設備根本沒被自動建出來」的情形。

FR-502 因此要求前端能由 OPS **手動建立 / 編輯 / 停用**設備，作為自動發現失準時的人工兜底。盤點後端：

- **device-service 本體早已支援**：`POST /devices`（`create_device`，201）、`PATCH /devices/{id}`（`update_device`）、`DELETE /devices/{id}`；`api/openapi.yml` 1.3.0 已文件化 `createDevice` / `updateDevice` operationId。
- **但 BFF facade 缺路由**：`services/bff/bff/routes/devices.py` 目前只代理 read + confirm/override/reject/corrections（見該檔頭 §8.1 surface 清單），**沒有 `POST /api/devices` 也沒有 `PATCH /api/devices/{id}`**。
- 前端 live client（`frontend/src/api/client.ts`）的 `createDevice` / `updateDevice` 已對映 `POST /api/devices` / `PATCH /api/devices/{id}`，但打過去會 404 —— **FR-502 在 web 端目前不可達**。

需決策：(1) 是否經 BFF 對外暴露 create/update；(2) 其安全模型（OPS / CSRF / frozen 裝置處理）；(3) device-service 的 `DELETE /devices/{id}`（實為 soft-retire，非物理刪除）是否一併暴露。

## Decision

1. **新增兩條 BFF facade 路由**，鏡像既有 mutating pattern（`override_device`）：

   ```
   POST  /api/devices               -> device-service POST  /devices
   PATCH /api/devices/{device_id}   -> device-service PATCH /devices/{device_id}
   ```

   body 以既有 `_json_body()` 僅驗「是合法 JSON object」即 **verbatim forward**。BFF **不重複定義** `DeviceCreate` / `DeviceUpdate` schema —— schema 校驗為 device-service 單一真相（§9.6），BFF 只做「JSON object 否則 422」的邊界守門，避免雙真相漂移。（`services/bff/bff/routes/devices.py`）

2. **OPS-gated**：兩條皆 `require_roles(Role.OPS)`，OPS 通道 key 由伺服器側 `_key_or_503()` 注入（ADR-023 role→≤1 key，缺 key fail-closed 503，永不借用他 role 通道）。手動建立 / 編輯屬特權寫入，與 confirm/override/reject 同級。

3. **CSRF / Origin**：兩條皆 mutating，沿用既有 Origin-CSRF middleware（無合法 Origin → 403），與既有 mutating 路由一致；瀏覽器 session 走 SameSite cookie（§9.4）。

4. **邊界校驗 + frozen 分工**：`PATCH` 的 `device_id` 先過 FR-322 regex（`DEVICE_ID_PATTERN`，spec-locked）才動上游。上游 4xx 由 `forward()` **回穿**，BFF 不臆測、不吞錯：device_id 重複 → 409、未知裝置 → 404、body 違規 → 422，**且 PATCH 對 confirmed/frozen 裝置 → device-service 回 `409 "frozen record — use /override"`**（凍結觸發器，ADR-016；`update_device` 不帶 freeze override）。故 **`PATCH` 的適用範圍 = 非凍結（candidate）裝置的欄位編輯（location/vendor/model/protocol/gateway_id…）；已確認裝置的分類 / device_type 變更一律走既有 `/override`**（freeze override + 改 signals + 寫 audit）。前端表單（S5）須據此把 confirmed 裝置的 device_type 編輯導向 `/override`，而非 PATCH。

5. **不暴露 `DELETE`（與 `/reject` 重複且較弱）**：FR-502 的「停用」語意 = **retire（→ 退役）**。device-service 的 `DELETE /devices/{id}` **並非物理刪除** —— 它呼叫 `device_repo.set_lifecycle(status="retired")`（soft-retire），但**不帶 freeze override**（frozen 裝置 → 409 導向 `/reject`）、回 `204` 無 body、**且不寫 audit**。既有 `POST /api/devices/{id}/reject` 是嚴格更佳的退役路徑（同為 soft-retire，但可 freeze-override、寫 `freeze_override` audit row、回更新後的 `DeviceOut`）。故 DELETE 對 web 屬**冗餘且功能較弱的重複**，**刻意不經 BFF 暴露**；停用一律走 `/reject`。

6. **文件同步**（§3）：本 facade 兩路由補進 `api/openapi.yml`（device-service 端 `createDevice`/`updateDevice` 已存在；本 ADR 補的是 **BFF 對外 facade 面**）；更新 `devices.py` 檔頭 §8.1 surface 清單；同步 `doc/operations/容器速查表.md`、`操作手冊.md`、`README.md`。

## Consequences

- ＋ FR-502 人工兜底在 web 端可達：自動發現錯分類 / 漏建時，OPS 可手動建立或修正設備，不必繞進 DB 或直連 device-service。
- ＋ 安全模型與既有 mutating 路由**完全一致**（OPS-gated + CSRF + FR-322 path regex + verbatim forward + §9.6 單一真相），無新信任邊界、無新金鑰通道。
- ＋ 前端 live client 既有 `createDevice`/`updateDevice` 對映即刻可用，毋須改 client 契約；mock client 已於 Wave 3 起頭批備齊樂觀回傳。
- － 手動 create 使「人工建立」與「自動發現」設備並存：device_id 衝突、與後續自動發現的 reconciliation 由 device-service `create_device`（201/409）負責；BFF 僅回穿 status，不解這層語意（屬 device-service / PRD-0003 狀態機範疇）。
- － facade 與 device-service create/update 契約耦合：device-service 改 `DeviceCreate`/`DeviceUpdate` schema 時前端須同步（openapi 為單一真相，§13.2 drift test 守護）。
- ＋ PATCH/override 分工明確（Decision 4）：非凍結裝置走 PATCH、已確認裝置的分類變更走 `/override`（freeze override + audit），與 ADR-016 凍結模型一致；前端不會誤用 PATCH 改 confirmed 裝置而吃 409。
- 對應威脅模型 `doc/governance/threat-model.md`：create/update 納入 BFF mutating surface，與 confirm/override/reject 同類，沿用 TB-6 / T-24（role→key）/ T-25（上游錯誤不外洩）/ T-26（auth）既有緩解，**未新增資產或邊界**；於 threat-model 標註 mutating surface 擴充。
- 對應可調參數 `doc/governance/tunable-parameters.md`：**未新增**可調參數。
- 對應 PRD：實作 PRD-0005 FR-502，補 §8.1 facade surface（原列 read + confirm/override/reject/corrections，本 ADR 補 create/update；明確排除 `DELETE`（停用走 `/reject`，見 Decision 5）；PATCH/override 分工見 Decision 4）。

> facade 對映摘要（伺服器端注入 OPS key，瀏覽器不可見金鑰）：
>
> | 對外（瀏覽器 → BFF） | 上游（BFF → device-service） | 守衛 |
> |---|---|---|
> | `POST /api/devices` | `POST /devices` | OPS + CSRF + JSON-object 邊界 |
> | `PATCH /api/devices/{id}` | `PATCH /devices/{id}` | OPS + CSRF + FR-322 + JSON-object 邊界 |
> | `POST /api/devices/{id}/reject`（既有，停用語意）| `POST /devices/{id}/reject` | OPS + CSRF |
> | ~~`DELETE /api/devices/{id}`~~ | （刻意不暴露）| — |
