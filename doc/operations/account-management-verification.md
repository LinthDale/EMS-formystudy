# DB 帳號管理驗證紀錄

2026-09-30；PRD-0023 / ADR-035。正式工作目錄 /home/dalelin/synaiq/EMS。
本紀錄只保存非敏感結果，不含密碼、hash、DSN 或完整容器環境。

## 測試與審查

- TDD RED：新 auth tests 因 accounts 模組缺失失敗；真 DB tests 因 migration 018 缺失失敗；CLI tests 因 account_cli 模組缺失失敗，之後才實作。
- BFF：253 passed，包含獨立假 repository 的 ASGI 測試與隔離 PostgreSQL 上的真實 CLI／reader登入。
- 新模組 coverage：accounts.py 86%、account_cli.py 89%，合計 88%。
- DB migration／權限／匯入／並行：8 passed。每測試獨立重建 disposable auth_acceptance schema，migration 跑兩次。
- Simulator CLI：20 unit + 1 real HTTP cookie integration，共21 passed。
- 原有四類 simulator 與資料 pipeline：35 passed（113.11秒）。臨時 BFF 重啟後可查61筆獨立驗收audit；未刪除audit。
- OpenAPI 2.1.0：無重複 YAML keys、所有內部 references 可解析，device-service contract 無漂移。
- git diff --check、BFF Python syntax、Compose config 檢查通過。
- 架構、安全、code reviewer、Python reviewer 完成複核，無未解決 block。

## 特別覆蓋的邊界

- 停用／啟用、角色改回、相同密碼重設，都無法恢復舊 session。
- 登入使用同一hash/id/role/version快照，重設競態不會給舊密碼新版session。
- DB unavailable：login與既有session均503；沒有env fallback。
- 未知／停用／密碼錯誤相同401；OIDC流程保留。
- 最後OPS並行保護；管理函數拒絕Repeatable Read等非READ COMMITTED隔離級。
- NULL／非法Base64／過量成本PHC拒絕；匯入全部同transaction、失敗無marker。
- UUID重送不再次異動；audit無hash，admin無直接UPDATE/DELETE/TRUNCATE或讀hash權限。
- Argon2工作只於真正完成後釋放slot，HTTP重複取消不能超過2個並行。
- 測試LOGIN roles使用UUID命名並在teardown刪除，不改cluster既有角色憑證。

## 本機實際遷移與部署

1. 確認正式 DB 原先沒有 bff_auth.accounts，套用 migration 018。
2. 設定獨立reader/admin service credentials；BFF reader沒有UPDATE權限。
3. 舊 BFF env 中1筆帳號原樣匯入：demo / ops / enabled=true / auth_version=1。
4. 逐筆比對新DB password_hash與原來源完全相同。沒有取得或重設demo明文密碼。
5. .env移除BFF_AUTH_USERS，改放兩個service DSN，檔案權限600。
6. 只重建BFF，保留既有DB及simulator服務。live BFF有reader DSN，不含AUTH_USERS或admin DSN。
7. 真實 account-admin list/history成功；demo有1筆import audit，actor=bff_auth_admin。
8. BFF /healthz =200，未登入 /api/auth/session =401；本機4178前端=200。

原demo密碼的登入可用性由原hash完整保留及同程式路徑的隔離真DB登入測試佐證；沒有假稱已用使用者的未知明文密碼登入正式帳號。
服務重建使舊記憶體session失效，使用者需重新登入。

## 重跑方式

BFF unit suite可不設AUTH_TEST_DSN執行，真DB測試會跳過；真DB驗收需另建一次性PostgreSQL container及名稱為auth_acceptance的database。
tests/integration/test_database_accounts.py會DROP該測試schema，禁止指向正式DB。先執行該檔建立schema，再將同DSN提供給BFF suite；僅以受保護env-file傳遞。
實際執行Docker images：ems-bff-test、ems-auth-integration；測試容器不公開port。驗收完成後刪除一次性DB及其connection暫存檔。
