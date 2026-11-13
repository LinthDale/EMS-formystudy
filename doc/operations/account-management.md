# EMS 帳號管理（PostgreSQL）

2026-09-30 · PRD-0023 / ADR-035。正式專案：`/home/dalelin/synaiq/EMS`。

## 1. 帳號紀錄在哪裡

本機登入帳號存於現有 PostgreSQL／TimescaleDB 的 `ems` database：

| 物件 | 內容 |
|---|---|
| `bff_auth.accounts` | UUID、帳號、Argon2id 密碼雜湊、角色、啟用狀態、版本、時間 |
| `bff_auth.account_audit` | 每次成功異動的 request_id、DB 操作者、原因、前後狀態；不含密碼或 hash |
| `bff_auth.imports` | 一次性舊帳號匯入 marker |
| `bff_auth.account_summary` | 不含密碼雜湊的管理查詢 view |

`.env` 不再保存 `BFF_AUTH_USERS`。只保存 `BFF_AUTH_DB_DSN`（BFF reader）和 `BFF_AUTH_ADMIN_DSN`（主機管理工具）等服務憑證。
資料持久化於既有 `timescale_data` named volume；重建 BFF 不會刪除帳號。不要刪除資料庫 volume。
目前 `demo` 已遷移，角色 `ops`，原密碼雜湊逐字比對一致，未重設密碼。

## 2. 從哪裡操作

在 WSL 終端進入專案：

```bash
cd ~/synaiq/EMS
docker compose run --rm account-admin list
```

`account-admin` 是臨時 CLI 容器，沒有公開 port。它使用主機上的管理 DB 憑證，不需再輸入 `demo` 密碼。
這代表可操作 Docker 且可讀取管理 DSN 的主機維運人員才能管理帳號；目前未提供網頁新增帳號。
此指令與控制模擬器的 `sim` 不同：`sim` 仍使用 EMS 使用者登入 BFF。

## 3. 新增帳號

例如新增維運帳號 `dalelin`：

```bash
docker compose run --rm account-admin create dalelin --role ops --reason "新增維運人員"
```

終端會要求輸入兩次新密碼，不回顯；長度 12–256 字元。不要使用 `-T`，也不要把密碼寫在命令或 .env。
帳號 1–64 字元，可用英數字、底線、點、減號，區分大小寫。

| role | 用途 |
|---|---|
| `ops` | 維運，包括 simulator 控制與需要 OPS 的管理查詢 |
| `ingest` | 使用既有 ingest 權限通道，不具 OPS 模擬器控制權 |
| `readonly` | 僅可存取原本允許 readonly 的查詢介面；不代表所有監控功能都開放 |

第一個帳號必須是 `ops`。新增後可立即從 EMS 登入，或：

```bash
python3 scripts/simulator_control.py --username dalelin list
```

## 4. 停用、啟用、改角色、改密碼

```bash
docker compose run --rm account-admin disable dalelin --reason "暫停存取"
docker compose run --rm account-admin enable dalelin --reason "恢復工作"
docker compose run --rm account-admin set-role dalelin --role readonly --reason "改為查詢用途"
docker compose run --rm account-admin reset-password dalelin --reason "使用者要求重設密碼"
```

每次異動都增加 `auth_version`，所有舊 local sessions 在下一次請求失效；即使再啟用、改回原角色或相同密碼，也不恢復舊 session。
禁止停用／降權最後一個啟用中的 OPS；多個管理請求同時操作也受保護。
未提供硬刪除或改名，以保留帳號與稽核關聯。無效或被拒絕的變更不會寫入成功異動紀錄。
`POST /api/auth/role` 仍只處理現有 session 撤銷，不是帳號角色管理入口。

## 5. 查詢紀錄與不確定結果

```bash
docker compose run --rm account-admin history --username dalelin --limit 50
docker compose run --rm account-admin history --limit 100
```

寫入前 CLI 會顯示 `request_id=...`。若連線中斷或顯示 Operation not confirmed，先查該 UUID：

```bash
docker compose run --rm account-admin history --request-id 00000000-0000-4000-8000-000000000001
```

將範例 UUID 換成該次印出的實際 ID。需要重試時，在原指令附加同一 `--request-id`，原因、目標與操作保持一致；不要換新 ID 盲目重送。
同一 ID 回傳第一次操作結果；改密碼重試不會再次要求輸入或再次重設。新的密碼變更必須使用新的 ID。
稽核 actor 是可信 DB `session_user`，目前一般顯示 `bff_auth_admin`；共享管理憑證無法辨識是哪位自然人。reason 填寫業務原因，不要填密碼或金鑰。
管理角色只能透過固定函數修改，不能直接 UPDATE/DELETE/TRUNCATE 帳號或稽核。DB owner 屬受控復原邊界。

## 6. 首次部署到新環境

目前本機已完成以下步驟，不必重做。

1. 啟動資料庫，以 DB owner 套用 migration（可重跑）：

```bash
docker compose exec -T timescaledb psql -X -v ON_ERROR_STOP=1 -U postgres -d ems < infra/timescaledb/migrations/018_bff_accounts.sql
```

2. 在受控終端進入 `docker compose exec timescaledb psql -U postgres -d ems`，讓專用角色可登入並以互動方式設定各自隨機密碼：

```sql
ALTER ROLE bff_auth_reader LOGIN;
ALTER ROLE bff_auth_admin LOGIN;
\password bff_auth_reader
\password bff_auth_admin
\q
```

3. 在受權限保護的 .env 設定以下服務 DSN，密碼須以 URL percent-encoding 編碼。不可使用 postgres 帳號當 BFF runtime：

```dotenv
BFF_AUTH_DB_DSN='postgresql://bff_auth_reader:<encoded-password>@timescaledb:5432/ems'
BFF_AUTH_ADMIN_DSN='postgresql://bff_auth_admin:<different-encoded-password>@timescaledb:5432/ems'
```

4. 建置 BFF image、建立第一個 OPS，啟動 BFF：

```bash
docker compose build bff
docker compose run --rm account-admin create initial_ops --role ops --reason "首次部署建立管理者"
docker compose up -d --no-deps bff
```

缺少 DSN、schema 或 DB 連線時 BFF local auth 不會回退讀取 env 帳號，也不會自動生成 demo。
全新部署需要先跑 migration；單純 docker compose up 不會替既有資料庫自動升級。

## 7. 舊 env 一次性遷移

`import-env` 明確由 stdin 讀取舊格式 `username:<argon2id PHC>:role`，多帳號以分號分隔。此命令不會讀取 runtime 的 BFF_AUTH_USERS。
先把現有值放在主機上權限 600 的暫存檔（勿列印、勿提交 Git），再：

```bash
docker compose run --rm -T account-admin import-env --reason "遷移既有帳號" < /secure/path/legacy-records.txt
```

匯入整批同一 transaction；必須包含 OPS。重複帳號或非法 hash 會整批回滾。完成 marker 使重跑只能回報 already_imported，不能覆寫既有帳號或重新啟用。
遷移順序：migration → 專用 DB credentials → 匯入 → 比對 DB hash/role 與原值 → 移除舊 .env 帳號及暫存檔 → 重建 BFF → 驗證登入。
請勿為了重跑而刪除 marker 或帳號表。本機 2026-09-30 的 demo 已完成逐字 hash 比對；以保留原密碼方式遷移。

## 8. 維運、備份、故障

BFF reader 最多 5 個連線；DB connect/acquire/statement timeout 5 秒。DB 故障時登入／既有 local session 請求回 503，不使用快取權限。
Argon2 2 個工作上限，排隊最多 5 秒；hash 成本與 Base64 編碼在匯入時檢查。管理交易只允許 READ COMMITTED。
BFF 重建會清除現有記憶體 session，請重新登入。OIDC session 沿用 IdP 流程，不需本機 DB account。

備份含密碼雜湊，須保護檔案權限及儲存位置；勿提交 Git：

```bash
umask 077
docker compose exec -T timescaledb pg_dump -U postgres -d ems -Fc -n bff_auth > /secure/path/ems-accounts.dump
```

備份還原先在隔離 DB 驗證，保留 UUID、版本、完整稽核及 import marker。另保管 DB role credentials；pg_dump 不包含 cluster role 密碼。
回滾保留 DB，修復 DB-compatible BFF image；不回退 env 帳號，不刪除 audit。若最後 OPS 忘記密碼，仍可用主機管理 CLI reset-password。
實際驗證：[account-management-verification.md](account-management-verification.md)。
