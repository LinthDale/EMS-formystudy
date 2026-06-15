# ADR-024：BFF 認證：OIDC-first + argon2id 本地 fallback

## Status
Proposed（2026-06-15）

精煉 [ADR-023](./ADR-023-bff-session-and-role-channel-key-authz.md)；源自 [PRD-0005](../prd/PRD-0005-ems-frontend.md) §9。ADR-023 已定 session / CSRF / role→channel-key；本 ADR 補上「認證來源」這一層的決策。

## Context
PRD-0005 §9 鎖定 BFF 為瀏覽器唯一入口與 cookie session，但「使用者憑證從何而來、如何儲存」在 P1 僅以 skeleton 實作：`BFF_AUTH_USERS` 以 **SHA-256（無 salt、快速雜湊）** 存密碼。威脅模型新增 T-26：env 外洩即可離線爆破，且 SHA-256 非為密碼設計。Owner 拍板（2026-06-15）：「不要自管密碼，改接企業 IdP / OIDC。長期 OIDC 優先；argon2id 作為本地 fallback。」目前尚無可整合的 IdP，故需要一個能「現在關閉雜湊弱點、未來無痛接 OIDC」的設計。

## Decision
1. **認證改為可插拔 provider**：login route 經 `AuthProvider` 介面取得 role，session/CSRF/role→key 下游完全不變。由 `BFF_AUTH_MODE`（`local` 預設 / `oidc`）於啟動時選定，未知值 fail-fast。（`bff/auth_providers.py`）
2. **OIDC / 企業 IdP = 戰略主線（長期），Phase-1 延後**：提供 `OidcProvider` 介面與明確 `NotImplementedError`；選 `oidc` 模式時 login 回 **503**（fail closed，絕不降級成不安全路徑）。完整 Authorization-Code + PKCE（discovery / redirect / token 交換 / id-token 驗證 / claim→role 映射）延至 Phase-1，因目前無 IdP 可整合。
3. **本地 argon2id = fallback（現在實作）**：以 `argon2-cffi` 取代 SHA-256。`BFF_AUTH_USERS` 記錄格式 `username:<argon2id PHC>:role`，PHC 內嵌 salt 與成本參數（m/t/p）；記錄以 **`;`** 分隔（PHC params 含逗號，故不可用逗號分隔）。只接受 argon2id（拒 argon2i/argon2d 與舊 sha256-hex）。驗證對未知使用者跑 dummy verify（抗枚舉）；空表 fail-closed；解析失敗 fail-fast。提供 `python -m bff.hashpw` 供 ops 產雜湊。
4. **不擴大攻擊面**：密碼雜湊僅存 .env（不入 committed TOML，沿用 ADR-023 secret 邊界）；不記錄任何密碼 / PHC / cookie。

## Consequences
- ＋ 關閉 T-26：argon2id memory-hard、per-hash salt，離線爆破成本大增；R-015 標記 Closed（緩解）。
- ＋ 認證來源可換（local↔oidc）而不動 session/route；OIDC 落地時只改 `auth_providers.py`。
- ＋ 維持 ADR-023 全部保證（session/CSRF/role→≤1 key、key 永不對瀏覽器可見）。
- － 多了一個 runtime 相依 `argon2-cffi`（需求清單已登錄）；argon2 驗證較 SHA-256 慢（刻意，為安全成本）。
- － OIDC 尚未實作：`oidc` 模式目前不可用（503）；多租戶 / 企業登入須待 Phase-1。
- 對應：threat-model T-26、risk-register R-015、tunable-parameters（`BFF_AUTH_MODE` / `BFF_AUTH_USERS`）。

## Phase-1 延後項目（OIDC）
discovery 端點與 client 設定、Authorization-Code + PKCE 重導與回呼、token 交換與 id-token（簽章 / iss / aud / exp / nonce）驗證、claim→Role 映射策略、IdP session 與 BFF session 生命週期對齊、登出（含 IdP 端）。落地後 `OidcProvider.authenticate`（或新增 redirect 端點）取代現行 `NotImplementedError`。
