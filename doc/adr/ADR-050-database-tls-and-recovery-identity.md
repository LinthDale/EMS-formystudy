# ADR-050：field DB／同步 WAL 強制驗證 TLS，還原核對外置 cluster 身分

日期：2026-11-13；狀態：Accepted／已私有短測驗證（正式部署另驗）；Owner EMS。

## 問題與目標

ADR-049雖要求部署使用TLS，但程式field DB連線尚未強制驗CA／hostname／client cert，同步WAL predicate也未查peer是否TLS。實體備份校驗能證明檔案一致，無法單靠內部manifest判定整套有效備份是否來自操作者預期cluster。本輪修這些準入缺口，並真測WAL archive ENOSPC、損壞備份／WAL及跨cluster拒絕；不重跑長測、不動共享／COM、不假稱正式跨主機HA或實體SD驗收。

## 決策

1. field receiver新增必填`db_tls={ca_file,cert_file,key_file}`，建立CERT_REQUIRED＋check_hostname的SSLContext並明確傳入asyncpg；禁止Unix socket／DSN host覆寫／明示非verify-full sslmode，避免繞過TCP TLS。demo仍只在明示隔離namespace可用，DB TLS可選。DSN／私鑰內容不寫log。
2. migration021新增版本化sync_tls_wal_flushed，runtime直接呼叫，缺021拒絕而不回退；舊sync_wal_flushed保留強化wrapper：保留唯一具名sync peer與固定LSN覆蓋，另查pg_stat_ssl的ssl=true、非空client_dn及固定ems_wal_archive角色；沒有已驗證client證書TLS通道，不可committed ACK。只回boolean、固定pg_catalog search_path、撤PUBLIC／僅receiver可execute，不授統計全讀。正式DB/WAL須hostssl cert與hostnossl reject、專用有限角色；命名仍信任受管DB／CA，不抵抗管理員偽造peer。
3. 還原前對**已解開的PGDATA**先以外置可信`expected_system_id`比pg_controldata，再pg_verifybackup，才准啟PG recovery。expected ID必須由維運的cluster登記／已驗TLS主庫取得，不能只讀同一備份自稱的ID。錯cluster及校驗失敗一律停止，無空庫／較早promote fallback。WAL損壞仍需真啟動recovery到指定點驗證；pg_verifybackup不等於全部PITR保證。
4. WAL滿測試只填當輪owned WAL job container的128MiB tmpfs，不填宿主或共享磁碟。PID1保持容器活著，pg_receivewal子程序ENOSPC退出不抹掉tmpfs；記真No space、slot lag與來源pending，刪固定quota filler後原slot重連、原ID送達一次。tmpfs只驗空間耗盡／恢復行為，不是非揮發archive耐久驗收。
5. server TLS key位於PGDATA之外；實體備份／證據不能夾帶私有CA或server/client key。測試PKI結束清除，保留公憑證metadata與雜湊。host控制僅固定op→當輪owned資源，不接受worker任意SQL、CID或host path。

## 維護／驗收

PRD-0021 §15.12、receiver DB TLS helper／config、migration021、WAL-PITR手冊與recovery preflight工具為權威；wire2／local schema3／capacity與公平政策不變。C4 Context／Container沿原元件，只把DB與WAL連線標成驗證TLS，備份檢查為維運工具。驗收：先RED、DB與WAL正反TLS真連線、錯憑證不假ACK、真ENOSPC＋恢復、backup checksum／WAL CRC／foreign WAL／有效外庫backup拒、正常正例與必要短回歸；正式部署仍待驗。

依據：[PG15 TLS](https://www.postgresql.org/docs/15/libpq-ssl.html)、[server TLS](https://www.postgresql.org/docs/15/ssl-tcp.html)、[pg_verifybackup限制](https://www.postgresql.org/docs/15/app-pgverifybackup.html)。

還原tar預檢只接受標準未壓縮regular／directory，固定512-byte header在讀extension payload前拒絕PAX／GNU sparse／links／devices／穿越；預設8GiB檔案及展開總量／100000 entries。檢查後保持輸入不可變、非root解到受控空目錄，再核外置cluster ID及checksum；system ID不區分同cluster logical DB或同ID分支，timeline仍人工核定。

驗收：DB／WAL TLS、128MiB archive ENOSPC恢復、損壞backup／WAL及有效外cluster拒絕已私有短測；55通過62.52秒，568短回歸／12專用skip／coverage90.99%，原已ACK資料PITR36通過。修field db_tls強制驗證、021版本化TLS＋固定角色WAL predicate、外置expected_system_id及tar資源預檢。無COM／共享部署／長測重跑；正式異失效域與Pi仍待驗。 [證據](../../output/no-pi-wal-security-20261113/README.md)。
