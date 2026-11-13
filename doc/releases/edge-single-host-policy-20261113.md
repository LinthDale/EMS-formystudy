# 單機部署政策 — 2026-11-13

## 2026-11-13 最新決定：單機運行，外部WAL部署暫停

使用者明確指定「先停用，暫時只有規劃一台電腦」。目前以一台EMS電腦運行，取消本階段對第二台WAL主機／DGX SSH帳號的需求；不再將它列為待使用者補資料的阻擋。

外部WAL receiver／replication slot／同步peer均未啟用，核對主庫fsync=on、synchronous_commit=on、synchronous_standby_names空值、複寫連線0、slot0。PostgreSQL本機WAL與正常資料持久化保留；17個既有服務不重建、不重啟。

目前已上線的Delta TCP／v1路由與公開EMS繼續運作。需要外部同步WAL的v2 field receiver維持未啟用；本次沒有把field自動降級成local，也沒有啟用QA／demo繞過。單機故障不提供異機容災保證。若日後要啟用v2單機確認模式，須另明確修訂其durability契約；本次只是停用外部複寫部署規劃。

先前「等待獨立WAL主機／SSH入口」為歷史狀態，已由本決定取代。既有ADR-049／050／051實作與測試保留作未來啟用參考，不刪除歷史證據，不重跑長測。

[實際核對](../../output/single-host-policy-20261113/verified-before.json)。
