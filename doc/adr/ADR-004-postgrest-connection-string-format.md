# ADR-004：PostgREST 連線字串改 key=value 格式

## Status
Accepted（2026-04-22）

## Context

PostgREST 透過 `PGRST_DB_URI` 連線至 TimescaleDB。Stage 1 初始採 URI 格式：

```
PGRST_DB_URI: "postgres://authenticator:1qaz@WSX@timescaledb:5432/ems"
```

啟動失敗：

```
could not translate host name "WSX@timescaledb" to address: Name or service not known
```

根因：密碼含 `@` 字元，URI parser 把第一個 `@` 視為 user-host 分隔符，導致 `WSX@timescaledb` 被當成 hostname。其他特殊字元（`:` / `/` / `?` / `#`）也會引發類似解析錯誤。

可選解法：
- A. URL-encode 密碼中的特殊字元（`@` → `%40`）
- B. 改用 PostgreSQL 標準 key=value 格式
- C. 限制密碼字元集（不允許特殊字元）

C 不可接受（弱密碼）；A 需在每個使用密碼的地方都記得 encode（易錯）；B 為 PostgreSQL 原生支援、不需 encode。

## Decision

`docker-compose.yml` 中 PostgREST 改用 **key=value 連線字串格式**：

```yaml
PGRST_DB_URI: "host=timescaledb port=5432 dbname=ems user=authenticator password=${AUTHENTICATOR_PASSWORD}"
```

延伸規範：
- 所有 PostgreSQL 系列工具（pg_dump、psql、其他 ORM）優先使用 key=value
- 僅在工具不支援 key=value 時才使用 URI（並 URL-encode）
- 密碼可任意包含 `@` / `:` / `/` 等字元，不需特殊處理

## Consequences

**正面**
- 密碼策略不受連線字串格式限制
- 設定可讀性高（每個欄位獨立）
- 與 PostgreSQL 官方 libpq 文件一致

**負面**
- 與 12-factor app 流行的 single URI env var 模式不同（多數工具兩者都支援，影響有限）
- 新進開發者可能誤以為要寫 URI 格式

**後續觸發**
- 任何新 service 連 PostgreSQL 一律 key=value
- 文件範例（README、操作手冊）統一示範 key=value 格式
