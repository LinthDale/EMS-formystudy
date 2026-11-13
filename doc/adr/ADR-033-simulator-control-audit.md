# ADR-033：統一 simulator 控制與持久操作紀錄
- 日期：2026-09-29
- 狀態：Accepted（已實作並於本機驗收）
- 對應：PRD-0022；修改 PRD-0001 FR-002/008、PRD-0002 FR-108 的模擬器控制範圍。

## Context
四種 simulator 缺少共同入口、身分與操作紀錄；PLC raw Modbus/MCP 可繞過高層控制。使用者已要求統一。

## Decision
既有 BFF OPS session + Origin 控制四個固定 ID。BFF 的 SQLite volume 先記 intent 再派送，append-only outcome/reconciliation，UUID 永久去重、每台串行與 instance/revision CAS。
EMS 自有 wrapper 暴露內部已認證 typed control endpoint；target 拒絕舊 REST/raw Modbus 寫入。上游 submodule 不修改。HTTP timeout 不重送、unknown 需 receipt 或明確新 instance 對帳。相同設定值不是執行成功證據。
BFF 單 worker，以 OS file lock 拒絕第二 active instance。模擬設定記憶體保存、操作紀錄持久；volume 不能刪除。
Delta 改 scenario 前結算發電量。Pi/真設備及 standalone RTU 不開新的控制入口。

## Alternatives
獨立 control service 增加單點、部署與重複認證，四台規模不採用。僅統一 UI 無法封鎖 raw 旁路。Docker socket、shell 重啟不提供 typed 安全邊界。

## Consequences
舊 curl :8001 POST 與 MCP simulator raw writes 停用；MCP read 保留。API 是唯一應用控制入口，主機管理員仍具有管理權，SQLite 非密碼學防竄改。設定重啟還原、未知結果保留，不宣稱 exactly-once。

## 2026-09-29 CLI Secure-cookie 相容修正
本機實際 BFF 保留 Secure cookie，原 urllib CLI 在 HTTP loopback 登入200後沒有回送 cookie，查詢/登出因此401。CLI 僅在已選定的 http://127.0.0.1 或 http://[::1] 相同有效 port，覆寫 CookieJar 的 return_ok_secure 判斷；cookie.secure 與父類 domain/path/expiry 檢查保持不變。
localhost、userinfo、其他 host/port 不適用此例外；外部仍須 HTTPS。記憶體 cookie jar、無 redirect/proxy、BFF cookie 設定與帳號皆不變。登入與讀取失敗不再誤稱有未知結果的 simulator write。
