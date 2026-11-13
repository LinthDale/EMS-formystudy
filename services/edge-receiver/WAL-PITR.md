# 同步 WAL 與已確認資料還原

依 [ADR-049](../../doc/adr/ADR-049-synchronous-wal-ack-and-pitr.md)／[ADR-050](../../doc/adr/ADR-050-database-tls-and-recovery-identity.md)。維運Owner EMS；只驗自有 network-none 測試環境，以下正式步驟尚未執行。共享v1不因此取得此能力。最新證據：[TLS／滿載／損壞](../../output/no-pi-wal-security-20261113/README.md)。

## 正式啟用順序

1. 停止v2接收確認，維運確認主庫 fsync=on、synchronous_commit=on、wal_level=replica 與可用 replication slot/WAL sender。以TLS verify-full、專用 REPLICATION LOGIN角色、pg_hba來源與client cert限制，不能沿用本輪私有QA的postgres/trust。
2. 在獨立失效域主機建立持久archive。查主庫cluster system identifier並登錄，archive按system ID隔離，segment檔名保留timeline前綴；不可混用不同cluster。建立physical slot `ems_archive_slot`，部署 [service範本](deploy/wal-archive.service.example) 與 [TLS設定範本](deploy/pg_service.conf.example)，替換CLUSTER_SYSTEM_ID與正式主機/憑證路徑。目錄0700，key/passfile0600，WAL沒有密碼但含營運資料，備份同樣限制存取。
3. `pg_receivewal --synchronous`必須即時fsync及回報flush，不能以預設模式或remote_write代替。主庫設定 `synchronous_standby_names='FIRST 1 (ems_archive)'` 並reload，核對唯一同名streaming/sync peer；archive process與slot身份由受信維運保證，SQL只驗server所見資訊，不能證明對方磁碟誠實。
4. **首次ACK之前**，先做並驗證一份可還原的 `pg_basebackup -Ft -Xstream --checkpoint=fast --manifest-checksums=SHA256`；WAL保存鏈涵蓋basebackup開始至最後已ACK的commit。持續取得新basebackup／監控archive與slot保留空間，不能只留下WAL而沒有base。basebackup角色／TLS來源限權另由DB維運配置，receiver不拿複寫／備份密鑰。
5. 以migration owner依序執行019、020、021（可重跑）；receiver runtime僅ems_edge_receiver角色＋原必要權限，不授pg_read_all_stats。field設定必填`db_tls.ca_file/cert_file/key_file`，CA驗證、hostname與client憑證都要成功；設定`ack_durability=sync_wal`與同名`wal_standby_name`後才啟動。runtime直接呼叫`edge_ingest.sync_tls_wal_flushed`，缺021拒絕，沒有舊函式降級。peer須為`ems_wal_archive`、TLS且client_dn非空；migration預建NOLOGIN角色，由維運核定後開LOGIN／配置憑證。任何缺peer／flush不足／配置改async／未知COMMIT結果都不回committed ACK；edge保留原ID再重送。

DB/WAL參考 [HBA範本](deploy/pg_hba.edge-tls.conf.example) 與 [server TLS範本](deploy/postgresql-tls.conf.example)，以正式來源CIDR、角色和CA取代示例。hostssl cert規則必須在舊trust/password廣泛規則之前，搭配hostnossl reject及拒絕非核定來源；CN須與登入角色一致或使用受管pg_ident映射。server key置於PGDATA之外，備份中不能包含私鑰。測試的postgres／loopback trust不能移植成正式設定。

## 還原順序

1. 停止receiver ACK出口、隔離舊主庫與自動重啟，保留完整故障證據。選定basebackup與相同system ID的完整WAL鏈；不要自動新建空DB。
2. 先在不可變的備份副本執行下列layout預檢，再以非root解開到全新、受控且無symlink的PGDATA。預檢只接受標準未壓縮tar的regular file／directory，拒絕PAX、GNU sparse、link、device、穿越與超界；不支援通用tablespace封裝。預設每個archive檔案／展開總量上限8GiB、100000 entries，可按已核定備份大小調整。外置可信cluster ID須來自維運登記或已驗TLS主庫，不能讀同一bundle自稱值。解開後必須先比pg_controldata、再pg_verifybackup，兩項過關才可啟PG；不能只驗checksum便接受整套有效外庫備份。

   ```sh
   PYTHONPATH=services/edge-receiver python -m edge_receiver.backup_preflight --check-archive /restore/base.tar
   PYTHONPATH=services/edge-receiver python -m edge_receiver.backup_preflight --directory /restore/pgdata --expected-system-id "$APPROVED_CLUSTER_SYSTEM_ID" --expected-timeline "$APPROVED_TIMELINE" --target-name "$APPROVED_RESTORE_POINT"
   ```

   另對pg_wal.tar預檢；工具依賴同版本PG的pg_controldata／pg_verifybackup。完成後設定recovery.signal、restore_command及經核定timeline／明示目標。restore_command先找完整segment，再用對應`.partial`；找不到非零返回。system ID辨識實體cluster，不區分同cluster的logical database或同ID複製分支，因此timeline／目標仍須由維運核定。到不了目標必須失敗，不能較早promote。
3. 要保全部已ACK資料，必須恢復到最後已ACK commit之後，通常replay完整可用WAL；刻意指定更早時間點等於主動捨棄後續資料。QA以已確認B後的named restorepoint示範，C是點之後commit但ACK遺失，仍由本地pending補送。
4. 確認restore目標已到且可讀寫，核對receipt canonical/hash/committed_at/retention與量測投影；重新建立新timeline同步WAL接收與basebackup保護鏈。在同步保護就緒前，不開field ACK。
5. 更新**DB以外**的generation UUID、強制edge重連建立新challenge，拒絕舊generation ACK；再開receiver。pending以原sample ID/hash補送去重，不能用舊ACK刪掉尚未恢復的資料。

## 容量與失敗處理

維運持續監控pg_stat_replication狀態/flush lag、pg_replication_slots.restart_lsn及WAL bytes、主庫與archive可用空間、basebackup驗證與保留鏈、新備份成功時間。slot可能把主庫撐滿；不能為了恢復流量把同步條件關掉卻繼續聲稱保護ACK。先隔離接收、修儲存／鏈再恢復。備份生命週期不可刪掉仍被basebackup到目標引用的WAL；本次沒有新增自動archive淘汰。

archive滿時保留slot及既有WAL，釋放／擴充核定儲存後，以原slot重啟同步接收；不可drop/recreate slot或關閉TLS／同步來清警報。slot保留bytes不等於網路flush落後量；恢復時捕捉固定主庫flush LSN，確認peer flush已覆蓋該fence，再檢查pending原ID送達一次。私有128MiB tmpfs案例驗ENOSPC及恢復，並非非揮發磁碟掉電耐久驗收。

本輪資料：`output/no-pi-wal-pitr-20261113/`封存的是自建trust測試庫實體備份／WAL與公憑證metadata，不含私有CA/client keys。舊邏輯dump那輪沒有留WAL的歷史缺口無法事後憑空重建；本修復驗證的是新保護機制確實把同類B救回。

官方：[PG15 receivewal](https://www.postgresql.org/docs/15/app-pgreceivewal.html)、[PITR](https://www.postgresql.org/docs/15/continuous-archiving.html)。

## 必要強化已驗：中央資料滿、lost slot與同ID分支（2026-11-13）

依[ADR-051](../../doc/adr/ADR-051-pinned-recovery-and-slot-reseed.md)，[三項短測證據](../../output/no-pi-critical-closure-20261113/README.md)38通過／18.00秒，616短回歸／12專用skip／coverage91.73%。

- 中央receipt資料tablespace滿時應只回retryable、保留來源；釋放／擴充資料空間後重送原ID去重。此案是16MiB有界tablespace真INSERT擴檔失敗，沒有驗整個主庫pg_wal滿或掉電。
- 先查pg_replication_slots.wal_status、restart_lsn及接收端錯誤。lost且restart_lsn NULL時，只重啟接收程序不能修好，也不能盲目drop/recreate原slot。先隔離ACK、保留舊archive與lost證據，再於可信原主庫**備份前**create新的physical slot(reserve=true)，保留整段WAL；核定容量保留策略不能讓新slot在接手前失效。取得及verify新basebackup後，新空archive綁預建slot，PG15從該slot restart_lsn接手。固定flush fence及新base/WAL實際還原演練驗完整鏈，外置generation換代／fresh session後再開ACK；無自動reseed/failover功能。
- directory CLI現在必填外置核定--expected-timeline／--target-name，拒latest/current；成功JSON輸出recovery_settings，**工具不自動寫入或啟動PG**。維運須把輸出設定套用到受控還原設定並核對實際生效值；同system ID及相同named target仍可能有不同分支。已用同ID timeline2/3證明latest選到branch-three，核定pin2選回branch-two；promote後產生新timeline4正常，2是來源分支，不是要求promotion後仍等於2。
