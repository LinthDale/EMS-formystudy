# ADR-005：DB schema 採 `api` / `public` 雙層隔離

## Status
Accepted（2026-04-22）

## Context

PostgREST 預設曝露指定 schema 下的所有 table / view。若直接讓它讀 `public`：

- 任何新建表（含內部 staging / debug 表）會被自動曝為 REST endpoint
- 寫入權限與讀取權限耦合難以分離
- 未來若需限制特定 view（如只允許聚合查詢、不曝原始資料），需大量改動

需要一種「DB 內部 vs 對外 API」的明確邊界。

## Decision

採 **雙層 schema 隔離**：

| Schema | 用途 | 權限角色 |
|--------|------|---------|
| `public` | 內部資料表（hypertable、staging、internal view） | `postgres`（owner）、Telegraf 寫入 |
| `api` | 對外 REST 曝露的 view / function | `web_anon`（read-only）、`authenticator`（PostgREST 連線） |

PostgREST 設定：
```yaml
PGRST_DB_SCHEMAS: api
PGRST_DB_ANON_ROLE: web_anon
```

`api` schema 內的 view 從 `public` 表選欄位，**不直接曝原始表**。權限規則：
- `web_anon` 對 `public.*` 無任何權限
- `web_anon` 對 `api.*` 僅有 SELECT
- `authenticator` 為 PostgREST 連線身份，可 SET ROLE 切換到 `web_anon`

實作位置：
- `infra/timescaledb/init.sql`：建立兩個 schema、view、role
- `infra/timescaledb/02-authenticator.sh`：以 env var 建 authenticator role 與密碼

## Consequences

**正面**
- 新增內部表不會意外曝光
- 權限模型清晰：「想對外開放？放 `api`。要鎖起來？放 `public`。」
- 未來加寫入 endpoint 可獨立給寫權限角色，不影響讀取
- 對應 OWASP「最小權限」原則

**負面**
- 新增對外欄位需改兩處：先建 `public` 表，再建 `api` view
- DB 物件數量增加（每個對外資料源至少一表 + 一 view）
- 開發者需理解 PostgREST role-switching 機制

**後續觸發**
- 新增對外 endpoint 一律走 `api` view，不得直接曝 `public` 表
- 寫入 API 啟用時新增 `web_writer` role 與對應 `api` schema function
- 跨 schema view 變動須同步 `api/openapi.yml`
