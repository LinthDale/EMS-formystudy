# ADR-049：中央 ACK 先等獨立 WAL 刷盤，再以實體備份 PITR

日期：2026-11-13；狀態：Accepted（本輪使用者核定修復，僅私有驗證，正式部署待驗）；Owner EMS。

## Problem / Decision

ADR-048 邏輯還原實證：備份後已 committed ACK 的 B，edge 已刪 payload，舊 dump 沒有 B，generation 換代無法再生內容。目標是在主庫單點損失後，以實體 base backup＋獨立持久 WAL 恢復已確認資料；不重跑長測、不操作共享服務或 COM、不宣稱整台主機／兩份儲存同時損失零遺失。

1. field receiver 強制 `ack_durability=sync_wal`，具名 `wal_standby_name=ems_archive`；demo 預設 local 只供既有隔離測試，可明示 sync_wal。field 不允許降級 local。
2. PostgreSQL fsync=on、synchronous_commit=on、具名同步接收端 streaming/sync 且 flush_lsn 可查證，否則不送 committed ACK。主庫使用 `synchronous_standby_names='FIRST 1 (ems_archive)'`；獨立接收端使用 PG15 `pg_receivewal --synchronous`＋physical replication slot，WAL 在接收端持久 volume 刷盤後才確認。不能以 async archive、remote_write 或未加 --synchronous 代替。
3. 收件／投影仍同交易，transaction 強制 synchronous_commit=on；COMMIT 後取得固定 pg_current_wal_flush_lsn，再驗同名接收端 flush≥該 LSN 才 ACK。接收端失聯／配置錯／未知結果保持 retryable、edge 原 ID 重送。SQL migration020提供固定 search_path 的 SECURITY DEFINER boolean 檢查，僅 receiver role可執行，不授 pg_read_all_stats。
4. 實體備份以 pg_basebackup -Ft -Xstream 建立，WAL current .partial 也保存；PITR 選 operator 明示 restore point，缺 WAL 不可略過目標或空庫重建。切換須隔離舊主庫、外置 generation 換代與重連，恢復庫先重新建立同步 WAL 接收再服務 ACK。要完整保住全部已ACK資料，目標必須涵蓋最後已ACK的commit；刻意回復較早時間會捨棄後續資料，不能宣稱零缺口。
5. WAL archive 與 base backup 由維運管理，field 須獨立主機／儲存失效域、TLS verify-full、專用REPLICATION帳號及網路限制；slot可能撐滿主庫，須容量監控、備份保留鏈與定期演練。receiver role不取得備份路徑／複寫密碼。私有QA容器同一宿主機，只驗主庫容器失效與PITR，不能冒充異地主機／斷電驗收。

## Maintenance / Validation

權威入口：PRD-0021 §15.9、edge-receiver/store.py、receiver.py、migration020、部署範本與獨立 WAL 操作手冊。MQTT wire2、local schema3與最新／最舊成功1:1公平不變；無REST/UI。新增工具均只控制當輪owned ID／固定命令，證據目錄沿用 NOFOLLOW／有界讀／原子寫。驗收要求 RED→GREEN、migration兩次與最小權限、WAL停機不假ACK且恢復一次、basebackup後ACK且本地已刪B在原主庫停用後從WAL回來、目標後C保持pending並重送、缺WAL不能達標。

來源：[PG15 pg_receivewal](https://www.postgresql.org/docs/15/app-pgreceivewal.html)、[同步複寫](https://www.postgresql.org/docs/15/warm-standby.html)、[持續封存與PITR](https://www.postgresql.org/docs/15/continuous-archiving.html)。

### 2026-11-13 使用者核定單機運行

外部同步WAL部署暫停，第二主機／SSH待辦取消；本機WAL及現行服務維持，沒有修改field sync_wal契約或以local降級啟用v2。先前部署前置條件保留為未來參考，非本階段待提供資料。詳[單機政策](../releases/edge-single-host-policy-20261113.md)。
