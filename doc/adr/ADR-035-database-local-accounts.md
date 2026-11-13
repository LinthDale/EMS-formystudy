# ADR-035：本機帳號以 PostgreSQL 為唯一來源

## Status
Accepted — 2026-09-30，使用者明確要求「帳號現在記錄在.env中不行，需要有DB紀錄」。取代 ADR-024 中 local env user table 的決策，OIDC 方向保留。

## Context
.env user table 不適合帳號生命週期與稽核；靜態登入角色不能即時撤銷既有 session。EMS 已有 PostgreSQL/TimescaleDB。

## Decision
採 PRD-0023，private bff_auth schema、專用 reader/admin DB roles、SECURITY DEFINER 限定異動與 audit 同 transaction。帳號管理以 Compose CLI 提供，密碼 getpass/Argon2id。
local 認證唯一來源 DB；一次性明確匯入現有 hashes，成功後移除 BFF_AUTH_USERS。session 綁 UUID/auth_version/provider，逐請求查核，DB 故障 fail closed。OIDC 不依賴本機帳號表。
使用現有 raw SQL migration 018；asyncpg 沿用專案既有 dependency；不新增 migration framework。

## Consequences
停用/改角色/改密碼會撤銷所有舊 local sessions。DB outage 影響登入及受保護操作；連線有 timeout。管理憑證不進 BFF。稽核的 actor 為真實 DB session_user，DB owner 仍是可信復原邊界。
不新增公開帳號 API 或網頁；不將密碼寫入 .env；現有 demo 原密碼保留。
