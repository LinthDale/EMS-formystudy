# main合併與部署紀錄 — 2026-11-13

## 已完成

| 項目 | 實際結果 |
|---|---|
| 合併／推送main | `9b61aef2b095ef02036f09d35aba6ddc58a47659`，來源`c7ac2e9`；合併樹與先前驗證版本完全一致。原main `670a99f`保留於annotated tag `pre-edge-reliability-main-20261113`。 |
| CI修復 | 原run43394371888只有unit job因wrapper缺/app/src與/app/scripts而collection失敗；`c6f652a895966461470786d5dbe6898035738c71`補兩個docker cp，未放寬測試。run43394953911六個job全部success。 |
| 建置 | receiver `sha256:474e221eaacc9acdc63f05722d844ae67eaee242545da477518c21b32a3eebdf`；Delta `sha256:db574722ead0d2f7df652b76100d81bef1256ec8762cf7f01d512a8c9cb9c680`，均標記來源commit9b61aef。後續CI修復不改application code。 |
| Delta採集器更新 | `ems-delta-edge:9b61aef`已替換原容器，保留原demo TCP／v1資料路由與持久volume；沒有v2 outbox轉換或Pi切換。佇列先線上SQLite backup、integrity_check=ok，私有備份與hash見部署preflight。容器running、restart0，DB最新時間持續前進。 |
| 公開入口恢復 | 部署前EMS首頁／session皆504，Windows轉送程序未啟動。依本次明確部署授權，用既有start-public.ps1 -NoPause恢復，PID43220，保留原靜態release。首頁200、未登入401；公開及本機登入／session／設備／量測／有界records皆200，登出204。 |
| 公開API與DB核對 | delta-sim-001來源時間與四值逐筆一致、DB唯一一列；公開正常及新image來源持續入庫有證據，非只看container running。 |

沒有重跑長測，也未占用COM或宣稱Pi／溫度表已驗收。其餘16個既有容器未重建。原工作目錄與其他未提交工作保留，main在隔離worktree管理。

## 尚未完成：可靠送達v2正式啟用

**此紀錄不是完整v2上線完成證明。** 現有主庫ssl=off、無edge_ingest.receipts／同步peer；本輪沒有在缺保護鏈時強行啟用receiver或切換來源。receiver映像已備妥，但尚未啟動；migration019–021尚未套用正式主庫，沒有修改其TLS／同步WAL／角色。

依[ADR-049](../adr/ADR-049-synchronous-wal-ack-and-pitr.md)及[WAL-PITR手冊](../../services/edge-receiver/WAL-PITR.md)，完整field啟用必須獨立主機／持久WAL＋驗證basebackup＋TLS／有限角色。已向使用者詢問獨立WAL目標；候選DGX-01在線，但現有`nick@100.64.84.58` BatchMode SSH拒絕publickey/password。下一步需使用者指定WAL主機及可用SSH入口／帳號（不用提供密碼），才繼續核容量、配置受管TLS／registry、先WAL與basebackup後切換v2。不可把同宿主容器當異失效域，也不能用QA ID／demo隔離旗標冒充正式field。

## 證據與回復

[本次部署證據](../../output/main-deployment-20261113/README.md)，包含main／CI／映像／部署／公開登入與DB核對摘要。私有queue backup留在`.local/main-deployment-20261113/`，不進Git。

如需撤回Delta image：以原base Compose加[rollback overlay](../../output/main-deployment-20261113/delta-rollback.yml)，只執行`up -d --no-deps delta-edge`；不down共享stack、不覆蓋現行outbox。main回復標籤只作版本依據，不能對有其他工作的原checkout做hard reset。公開轉送由既有腳本／配置管理；本次未改網站內容／帳號、未新增自動啟動。
