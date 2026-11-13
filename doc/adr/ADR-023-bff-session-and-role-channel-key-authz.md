# ADR-023：BFF Session 與 role→channel-key 授權實作

## Status

Proposed（2026-06-11）

源自 [PRD-0005](../prd/PRD-0005-ems-frontend.md) §9（GATE-1）實作（`services/bff/`）。PRD 已鎖定 GATE-1 技術選型（FastAPI BFF + cookie session + Origin CSRF）；本 ADR 記錄四項**超出 PRD 文字的實作層安全決策**，供後續 review 簽核。

## Context

PRD-0005 §9/§12 GATE-1 定案：BFF 為瀏覽器唯一後端入口、cookie-based session、Origin-header CSRF、role→channel-key 授權。但下列實作層問題 PRD 未明定：

- role 變更時 session 的語義（僅降級失效？任何變更？）
- session 儲存的抽象程度（P1 用什麼、未來怎麼換）
- 上游（device-service / PostgREST）回 401/403 時，如何呈現給瀏覽器
- 量測讀取（PostgREST hop）是否消耗某條 key 通道

## Decision

1. **任何 role 變更（不只降級）即 revoke session**——權限只能透過重新登入取得。較 §9.1「降級失效」更嚴，消除 session 內再授權的攻擊面。（`bff/roles.py` 註記 + `SessionManager.change_role`）
2. **`SessionStore` Protocol + in-memory 實作（P1）**，Redis 以同介面替換（GATE-1）；路由不依賴實作。**in-memory 限單 uvicorn worker**（不跨進程），水平擴展前須換 Redis。
3. **上游 401/403 一律對瀏覽器回 502**："BFF 自選 key，上游 auth 失敗即 BFF 自身配置錯誤"，不轉發上游 auth 細節；5xx / 未預期狀態 → 502；契約性 4xx（400/404/409/422/429）透傳。（`bff/upstream.py`）
4. **PostgREST 量測 hop 不花任何 key 通道**（web_anon 白名單 view，§9.3）。BFF 僅持 **OPS / INGEST 兩把 key**；**AI key 永不進 BFF**（§1/§6.1）；READONLY role 無 key 通道（fail closed，絕不借用他 role 的 key）。

## Consequences

- ＋ 嚴於 §9.1；無 session 內再授權的攻擊面；key 永不對瀏覽器可見（含錯誤路徑與 log）。
- ＋ session store 介面可換 Redis 而不動路由。
- － role 切換需重新登入（UX 成本，P1 可接受）。
- － in-memory store 限單 worker；多 worker / 水平擴展前必換 Redis（ops 文件須註明）。
- 對應威脅模型：`doc/governance/threat-model.md` TB-6 / T-22~T-25（session 竊取、CSRF、跨 role 提權、上游錯誤洩漏）。
- 對應可調參數：`doc/governance/tunable-parameters.md` BFF 區（session 壽命/閒置、upstream timeout、origin allowlist；cookie 屬性與 role→≤1 key 為 spec-locked）。
