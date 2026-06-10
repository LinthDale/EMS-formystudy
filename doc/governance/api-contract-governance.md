# API 契約治理（API Contract Governance）

> **狀態：POLICY（規則已立，2026-06-09），尚未 ENFORCEMENT。** 規則性條款（§1 真相、§2 semver、§4 前端由 spec 生成）即時適用於人工流程；但**機械化強制尚未到位**——`api/CHANGELOG.md` 未建立、CI gate（lint/diff/contract/drift test，§5）未實作。兩者於 **PRD-0005 實作批次**落地後，本文件才從 policy 升為 enforced。在此之前，違反仍須靠 review 把關。

> 範圍：EMS 對外 / 跨服務 REST API 契約的版控紀律。**`api/openapi.yml` 為 REST API 的單一真相（source of truth）**。
> 起因：PRD-0005 自建前端要由 OpenAPI 生成 TS client，若 spec 無紀律，前端 client / 測試 / 文件全部漂移。
> 不涵蓋：DB schema 遷移治理（另見 [ADR-020](../adr/ADR-020-db-migration-governance.md)）；MCP 協定（非 REST，不在 openapi.yml）。

---

## 1. Source of Truth

- **`api/openapi.yml`（OpenAPI 3.1）是 REST API 的唯一規範來源。** 任何 REST 行為以此為準；實作（FastAPI 路由 / Pydantic model）與本檔不一致時，視為 bug，須對齊（PRD-0003 經驗：曾發生 schema drift，照實作重寫並程式化逐欄驗證）。
- 早期文件提及的 `doc/API.yaml` 為**舊路徑、已不使用**（已於 Guideline §3.3/§11.2 更正）。

## 2. 版本號（semver）

`info.version` 採 **語意化版本 MAJOR.MINOR.PATCH**（現值 `1.2.0`）：

| 級別 | 觸發 | 例 |
|------|------|----|
| **MAJOR** | **breaking change** | 移除 / 改名端點或欄位、改必填、改型別、改既有語義、收緊既有回應 |
| **MINOR** | **non-breaking 新增** | 新端點、新選填欄位、新列舉值（additive）|
| **PATCH** | 不影響契約 | 文案 / 描述 / 範例 / 修錯字 |

- 每次 API 變更**必須**同步 bump `info.version`。
- 重大端點群可在 path/tag 標註對應 PRD（如 Device Service → PRD-0003）。

## 3. Breaking vs Non-Breaking 規則

- **Non-breaking（允許在 MINOR）**：新增端點；新增**選填**欄位；新增列舉值；放寬輸入限制。
  - ⚠️ **enum 新增的消費端前提**：新增 enum 值僅在**消費端有 unknown/default handling 時**才是 non-breaking。TypeScript 前端若對該 enum 做 **exhaustive switch（無 default 分支）**，新增值會造成實務破壞（型別不涵蓋 / runtime 落空）。**規定**：所有由 spec 生成 client 的消費端，對 open-ended enum **必須**有 unknown/default 分支；否則該 enum 新增**視為 migration-needed**（升級為需協調的變更，發版時通知前端）。
- **Breaking（必須 MAJOR + 遷移計畫）**：移除 / 改名端點或欄位；選填改必填；改型別 / 格式；收緊既有回應；改既有語義。
- Breaking change 須在 PR 描述列出受影響消費端（前端 TS client、其他服務）與遷移步驟。

## 4. 前端 client：必須由 OpenAPI 生成

- **PRD-0005 前端的 TS client 一律由 `api/openapi.yml` 生成**（如 openapi-typescript / openapi-generator），**禁止手刻** request/response 型別。
- 生成物入版控或於 CI 重生並比對；spec 一改，client 隨之，杜絕「文件說一套、前端打另一套」。

## 5. CI gates（API 變更必過）

| Gate | 工具（候選）| 作用 |
|------|------|------|
| **lint** | `spectral` / `redocly lint` | spec 結構 / 風格合規 |
| **diff** | `oasdiff` / `openapi-diff` | 偵測 breaking change → 若 breaking 但 MAJOR 未 bump → **CI fail** |
| **contract test** | 由 spec 生 client，對實際服務（或 mock）驗 request/response | 防消費端與 spec 漂移 |
| **runtime drift test**（**P1 必做**）| 比對 committed `api/openapi.yml` vs device-service 執行期 `create_app().openapi()`（FastAPI 由 route/Pydantic 自動產生）| **防實作與 spec 漂移**——否則「openapi.yml 是真相」仍退回人工維護。PRD-0003 曾手動逐欄比對（commit d0f71e6）；本項把它**自動化為 CI test** |
| **version check** | 自訂 | 端點 / schema 有改但 `info.version` 未 bump → fail |

> CI 接線屬實作工項（與 PRD-0005 P1 同批，列為 P1 task）；本治理文件定義**規則**，落地時補 CI job。**在 drift test 自動化前，`api/openapi.yml` 為「source of truth」僅靠人工 + review 維持，非機械保證**（見頂部 POLICY 狀態）。

## 6. CHANGELOG

- 新增 **`api/CHANGELOG.md`**（目前不存在），每次 API 變更記一條：版本、日期、級別（MAJOR/MINOR/PATCH）、變更摘要、對應 PRD/PR。
- 為 breaking change 的唯一可追溯紀錄（decision-log 為本地 gitignored，不可依賴）。

## 7. 與既有流程的關係

- Guideline §11.2「EMS 同步義務」第 1 項即 `api/openapi.yml`——本治理為其展開的紀律。
- 與 [tunable-parameters](tunable-parameters.md)（參數治理）、[ADR-020](../adr/ADR-020-db-migration-governance.md)（DB 遷移治理）並列為 `doc/governance/` 三條治理線；各管不同 artifact，不重疊。

---

> 狀態：v1（2026-06-09 立）。規則即時生效（版控 / semver / 前端生成）；CI gate 與 `api/CHANGELOG.md` 於 PRD-0005 實作批次落地。
