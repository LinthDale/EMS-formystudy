# Committed telemetry receiver

目前field DB亦強制驗證TLS：設定`db_tls={ca_file,cert_file,key_file}`，驗CA／hostname及client憑證；部署依序migration019／020／021，WAL固定`ems_wal_archive`角色、TLS＋client身分、同步flush覆蓋後才ACK。最新 [55項短測／568項短回歸與36項PITR](../../output/no-pi-wal-security-20261113/README.md) 已私有驗證；正式部署另驗。還原與滿載處置以 [WAL-PITR](WAL-PITR.md) 為準；[外置cluster身分／備份預檢](edge_receiver/backup_preflight.py) 不接受空庫fallback。

PRD-0021／ADR-043 的可靠送達子集。Python 3.11，paho-mqtt 2.1.0／asyncpg 0.31.0；新 v2 topic 與舊 Telegraf 完全分離。receiver 不開 HTTP／Modbus port，沒有控制命令。實作及故障驗收見 [本輪紀錄](../../output/committed-delivery-fix-20261112/README.md)。

| 修改項目 | 權威入口 |
|---|---|
| MQTT canonical schema、ID/hash、ACK 驗證 | [reliable_wire.py](../delta/delta_device/reliable_wire.py) |
| 原子入庫／去重／缺列修復 | [store.py](edge_receiver/store.py)、[migration019](../../infra/timescaledb/migrations/019_edge_committed_receipts.sql) |
| 權威設備／stream／revision／profile／生效時間 | [設定範本](deploy/receiver.example.json)、receiver.validate_config |
| mTLS principal 與 topic 權限 | [broker 範本](deploy/mosquitto-v2.conf.example)、[ACL](deploy/edge-v2.acl.example) |
| 邊緣 queue／sender／離線轉換 | services/delta/delta_device/reliable_*.py、migrate_delivery.py |
| 部署與驗證 | [opt-in Compose](../../compose.edge-receiver.yml)、[私有驗證工具](tools/verify_private.py) |

DB DSN 只由設定指定的 env 取得；使用具 LOGIN 的專用角色，授予 migration 建立的 `ems_edge_receiver` 群組，不用 postgres／OPS 憑證。收據 schema 不授予 PUBLIC/web_anon。服務需核實 fsync、synchronous_commit；未知 commit 不回 committed。未完成正式 owner／主機、憑證輪替／撤銷與備份復原驗收前，不宣稱 production ready。

部署前先產生 DB 外的 generation UUID 檔案並持久保存，缺失拒啟動。設定／憑證路徑須由 container UID10001 可讀；私鑰唯該帳號可讀，generation／config 掛唯讀。**PITR／恢復舊 DB 前隔離 ACK 路由，更新外置 generation 並強制所有 gateway 重連**，不可沿用 DB 備份內的 generation；私有PITR已驗，正式異失效域仍待驗收。

原本匿名 broker 不可直接充當 v2 field 接收端，也不能在相同 broker/topic plane 留匿名 listener 旁路。gateway 憑證 CN 必須等於 gateway_id，只能寫自己的 samples/session request；只有 receiver 能寫 ACK/session response。設定綁定 device、stream、revision、profile 及半開採樣生效時間。替換範本的 QA ID／UUID／日期及 endpoint，需同步 edge 與權威 registry。field 強制 mTLS；demo v2 只接受明示的 network-none namespace 且僅 lo，不能拿 demo flag 接共享匿名端點。

從 repo root `docker build -f services/edge-receiver/Dockerfile .` 建置。先在核定 DB 執行 migration019／020／021（不改舊 API view），依WAL-PITR建立basebackup／同步WAL保護，再提供 `EDGE_RECEIVER_DSN`、`EDGE_RECEIVER_CONFIG`、`EDGE_RECEIVER_GENERATION`、`EDGE_RECEIVER_CERTS`，以 `docker compose -f compose.edge-receiver.yml --profile edge-v2 up -d --build` 啟動新增服務。此操作文件不是本輪共享部署紀錄；原 24h 凍結 v1 不切換。

只切換已停止的目標 sender：備份 v1 queue，使用新的 v2 設定及全新 outbox 路徑，執行：

```sh
PYTHONPATH=services/delta python3 -m delta_device.migrate_delivery \
  --source /absolute/stopped-v1/outbox.db --config /absolute/v2-config.json --source-stopped
PYTHONPATH=services/delta python3 -m delta_device edge --config /absolute/v2-config.json
```

轉換只讀原 queue、逐列核對 ILP／snapshot、保留原時間與 clock 高水位，完整暫存成功才原子發布新 queue；已存在目的檔拒絕覆寫，映射保存在新 metadata。`--source-stopped` 是操作者確認，不會替你停止程序；不可對本輪活動 COM 台架使用。v1 已刪除／中央未收到的歷史資料不能由此復原。回滾時停 v2 sender 並保存 queue，禁止交給 v1 以 PUBACK 清空；可修正 receiver 後沿原 ID 重送。

第一階段 sender 單筆／單 inflight、最多 2 batch/s（實際 edge loop 約每秒一次）；不承諾 20/s／7 小時清空 7 天 backlog。queue 與 quarantine 共用 cap，SQLite max_page_count 管整檔 bytes；完整本地 rich snapshot 最多16KiB，中央只存四欄 canonical sample，不宣稱三相詳細投影已完成。2026-11-13依[ADR-045](../../doc/adr/ADR-045-newest-first-edge-retention.md)改採**最新資料優先**：queue／audit／byte滿時按capture_seq由舊至新淘汰，包含未送／quarantine，與新資料同交易；不以audit累積永久卡住採集。7天為容量內目標，超額不保證完整補傳。中央 receipts 仍不自動 purge，必須監控磁碟；完整 sealed manifest／每日對帳／heartbeat UI 仍待實作。

私有驗證：先準備快取 ems-delta-test／ems-bff／alpine／Mosquitto／Timescale images，再離線建立 `Dockerfile.test`，執行 `python3 services/edge-receiver/tools/verify_private.py --output <全新目錄>`。工具只建立自有 network-none anchor、兩個獨立 broker、DB、worker，不掛 Docker socket 給 worker、不 publish host port、不碰 COM。臨時 PKI 結束清除，只封存公憑證 metadata、命令、來源 SHA256、JUnit、coverage、原始帳本及清理結果。

2026-11-13新增 `--suite faults` 短測入口：[8個真故障＋35個槽號回歸](../../output/no-pi-v2-faults-20261113/README.md)，43項通過，另16個驗收閘門反例。baseline與faults都必須核對[完整35案catalog](tools/boundary-cases.json)，缺案／同群組替代／重複／跳過一律拒，即使exit0也不能過；faults另需真DB TimeoutError、retryable/database、回滾0/0與恢復1/1。catalog變更要同步測試契約及複核。只選定點套件，沒有長測；本輪未改production。

## 最新資料優先（2026-11-13，ADR-045）

其他無Pi定點續測入口：`python3 services/edge-receiver/tools/verify_private.py --suite resilience --output <全新目錄>`。[新9案＋35槽號共44通過](../../output/no-pi-resilience-20261113/README.md)，工具32案通過；真SIGKILL三交易邊界、SQLite鎖／唯讀、線上backup與v2錯CA／錯hostname／expired server拒絕及原ID恢復。TLS 8886／8887／8888僅自有network-none loopback，無hostport／新常駐服務。控制器要求post-constructor基準的真hash差異＋journal、真故障原因與原ID證據，不能只有exit0／初始化改檔假PASS。只改測試／工具，production與共享部署未改；非Pi／實體掉電／PITR驗收。

[本輪證據](../../output/newest-first-retention-20261113/README.md)：336項短回歸通過、12項既有專用clock/TLS未重跑，production line coverage≥80%；包含23項容量案例、同session真ACK與淘汰競態、離線12筆限3只補最新3筆。原先容量滿拒新測試與證據封存保留；新版faults中的兩容量案已改驗最舊淘汰／最新持久化。

本地schema升至3，MQTT wire仍2、central migration仍019。停止舊程序並備份queue後啟動新版，完整schema2自動在同交易補必要摘要並升版；兩個非唯一加速索引另用交易，只有SQLITE_FULL時回滾索引、記retention_indexes_deferred並沿掃描查詢運作，下次重啟可重試，不宣稱無索引效能。若連必要metadata也無空間，升版安全失敗並保留舊檔。舊v2拒開schema3。勿同時啟動新舊writer；回滾保存schema3並修復新版，不手改user_version降級。v1離線轉換遇byte不足仍整體失敗，不發布被裁切的目的檔。

`ReliableOutbox.retention_status()`提供有界累積摘要：audit淘汰、未確認送達副本淘汰、已確認audit回收、quarantine淘汰及最近一批序號span／最後sample ID/hash。`capacity_eviction`寫本地warning；缺口UI與對中央上傳此摘要尚未實作。span可能包含已確認項，不代表每筆中央都缺失；計數不冒充committed。超出完整本地索引範圍後不能宣稱逐筆歷史對帳完整。回收無引用window，避免其獨立無界增長。

若新寫入最終失敗（真正磁碟無空間、I/O、不可回收占用），本次淘汰／seq／window／摘要全回滾並記sample_rejected；不得先清空舊資料。已在傳輸的舊樣本可能先被淘汰，遲到ACK僅匹配原UUID/hash，記`ack_for_retired_sample`且不刪新資料；中央已有舊筆也不會被本地回收刪除。共享v1、COM及原長測未操作；此政策只處理量測queue，不套用控制稽核。

## broker／損壞庫／client憑證生命週期短測（2026-11-13）

`python3 services/edge-receiver/tools/verify_private.py --suite lifecycle --output <全新目錄>`：[42定點通過／393相鄰通過、12專用case跳過、coverage91.02%](../../output/no-pi-lifecycle-20261113/README.md)。同edge PID在broker離線期間仍TCP採3筆、恢復中央每ID1列；4種損壞／空檔拒開不改bytes；同CN client新cert可傳、CA簽CRL撤oldserial後強制restart自有TLSbroker，活動old session斷開、old重連拒、新cert可補原ID。此為私有測試CA，非正式輪替／撤權SLA。

ReliableOutbox以排他建立區分new／existing；既有零長度／空schema不得自動建新庫，精確SQLITE_READONLY_ROLLBACK才以rw讓SQLite恢復hot journal，再照常檢schema。不要先touch空queue檔、不手改版本或刪journal假恢復；真損壞先保留bytes與備份，restore／另開stream需核對未知結尾。wire2／本地schema3不變。測試host控制僅固定op映射當輪owned IDs，worker沒有Docker socket；回覆／logs／result用exclusive random FD→rename，讀產物NOFOLLOW／regular／bounded。worker仍可讀測試PKI，不宣稱完全惡意worker隔離；共享v1／COM／原長測未改。

## 還原／超量／新資料延遲短測（2026-11-13）

`python3 services/edge-receiver/tools/verify_private.py --suite restore-load --output <全新目錄>`：[38定點、419相鄰／12專用skip、coverage91.04%](../../output/no-pi-restore-load-20261113/README.md)。host只對本run database執行固定pg_dump ems→新ems_restore（Timescale pre/post_restore），不drop來源；backup copy用private新目錄、NOFOLLOW／NONBLOCK／regular／16MiB雙限binary讀、SHA256核對後原子發布。來源原庫只作testoracle，復原僅dump＋local；backup前A原封、pendingC原ID補、舊ACK回放拒，backup後已ACK且localpayload已刪B明列不可補，不稱WAL PITR／RPO0。

receiver真DB鎖＋200封同樣本有效重送，queue最高64、drop135、rate拒65，無假committed且恢復原／新各1列。依[ADR-048](../../doc/adr/ADR-048-v2-live-backlog-fairness.md)，sender最新／最舊成功1:1交替：初始最新，authenticated committed且本地resolved才換邊；錯誤／retiredACK不換，pending()預設仍最舊。1秒productionloop下1000舊＋3新，commit延遲1.044／2.091／2.098秒、oldest有進度、總1003不丟。輪次記憶體重啟不持久，最新候選非每一筆SLA；單筆inflight／.5秒節流／edge原1秒節奏保持，非20/s性能提升或完整7天驗收。共享v1／COM／長測未動。

## 2026-11-13 同步 WAL 與 PITR（ADR-049）

field receiver現在強制sync_wal：主庫COMMIT＋具名獨立WAL刷盤覆蓋固定LSN後才committed ACK；無peer／未同步／錯設定則retryable保留來源。deploy/receiver.example.json、migration020與[正式啟用／還原手冊](WAL-PITR.md)為權威；新增PG15 pg_receivewal/systemd/TLS範本，正式異失效域與首份basebackup就緒後才啟動，尚未部署共享。

私有入口新增`--suite wal-pitr`；所有private suites加入自有同步WAL容器與020兩次套用，既有field測試不降級。PITR suite另建立basebackup／缺WAL反例／恢復PG與新timeline WAL，無hostport或COM。工具prepare以host UID非root執行，backup/WAL只NOFOLLOW／regular／檔名白名單／有界讀，命令紀錄亦原子寫以防worker預置連結。

## 2026-11-13 無Pi切換／受限角色續測

新增`--suite cutover`，只跑[5新場景](../../tests/integration/test_edge_cutover.py)與35固定槽號回歸。field mTLS＋有限DB角色＋同步WAL完整路徑、撤INSERT恢復缺列、三轉換SIGKILL、inflight重複clientID踢線／新session舊ACK拒。[40定點通過、131工具通過](../../output/no-pi-cutover-20261113/README.md)。不改production；cutover gate要求真callback斷線狀態、真InsufficientPrivilegeError及完整source/mapping/中央一次證據，初版先timeout測試限制已修。

## 2026-11-13 integrity短測與本地儲存bugfix

`--suite integrity`選[25個新儲存案](../delta/tests/test_reliable_consistency.py)、[5種異常MQTT批次與SIGTERM完整程序重啟](../../tests/integration/test_edge_integrity.py)及35槽號，共66定點通過；500短回歸／12既有skip／91.36%，最新210工具／儲存案通過。[結果](../../output/no-pi-integrity-20261113/README.md)。store新增開庫關係／高水位檢查、enqueue退休前水位guard、selected payload/audit/window驗證、ACK同交易再驗、pending一致read snapshot與retention溢位回滾；第三個optional audit_time索引FULL可延後，schema3/wire2與其他契約不變。共享與COM／長測均未動；600k/Pi性能另驗。

### 高必要性短測收尾（2026-11-13）

[三項38通過／616相鄰通過](../../output/no-pi-critical-closure-20261113/README.md)：中央receipt資料滿、lost slot重建完整保護鏈、同cluster多timeline二次PITR。還原CLI必填核定timeline／target並輸出設定，不能把latest當核定分支；slot先reserve再備份／新archive接手，真鏈PITR過關才重新開ACK。操作以[WAL-PITR](WAL-PITR.md)為準。使用者核定高必要性項目到此收尾，其餘不自動擴充；尚未正式部署或完成Pi實機驗收。
