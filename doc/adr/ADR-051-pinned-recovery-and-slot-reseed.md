# ADR-051：還原固定timeline／target，lost slot必須重建保護鏈

日期：2026-11-13；狀態：Accepted／三項已私有短測驗證（正式部署另驗）；Owner EMS。

## 問題與範圍

沿PRD-0021 FR-2106、ADR-049／050補三項高影響短測：中央receipt資料空間ENOSPC、slot真正lost、同system ID多timeline二次還原。其餘強化不納本輪，無長測／COM／共享操作。原手冊雖要求核定timeline，預檢CLI只驗system ID及checksum，不能替操作者固定還原分支。

## 決策

1. directory還原預檢CLI增加必填外置`--expected-timeline`與`--target-name`，僅接受正uint32十進位timeline及有界安全名稱；拒latest/current及缺值。輸出核定的recovery設定供維運套用；它不自行啟動PG，不證明操作者指定的分支符合業務意圖。Python既有verify_backup只驗backup的契約保留，另以recovery_settings共用產生設定。archive layout預檢不需要target。
2. slot失效時不允許盲目drop/recreate後直接開ACK。隔離ACK出口，保留原archive／lost slot證據；在可信原主庫先建立新physical slot並以reserve=true立即保留WAL，再取得並驗證新basebackup。從備份開始到新接收端追上之間全部WAL都要保留；以空archive綁新slot由PG15 READ_REPLICATION_SLOT的restart_lsn接手，具名同步flush覆蓋固定LSN且新base＋WAL真PITR驗證完整鏈後，外置generation換代／重連才開ACK。無有效base或WAL鏈則保持停止；不新增自動failover／自動slot重建。
3. 中央滿載只填當輪owned主庫的16MiB獨立tablespace tmpfs，移入真receipt表，觀察真INSERT擴檔ENOSPC與retryable／來源保留；清filler後同ID恢復一次，移回pg_default/drop測試tablespace後才做實體備份。不得填共享／宿主磁碟。這不代表整個pg_wal耗盡或掉電測試。
4. 多timeline案例實際建同一system ID的不同分支、相同named target，證明latest可達錯分支；正式工具拒絕latest，固定外置核定timeline可二次PITR並驗分支資料／排除另一分支。history缺失不可忽略，還原正例含checksum／ID驗證與指定target達成。

## 維護與驗收

權威：backup_preflight、WAL-PITR手冊與私有critical短套件；現有receiver ACK／TLS／migration021／wire2/schema3與容量公平政策不變。工具僅固定owned操作，不接受worker CID／SQL／路徑／timeline。先保留RED，三項真故障＋35槽號邊界、證據反例閘門及必要相鄰短回歸；正式部署與Pi另驗。

依據：[PG15 slot狀態](https://www.postgresql.org/docs/15/view-pg-replication-slots.html)、[PG15 recovery目標](https://www.postgresql.org/docs/15/runtime-config-wal.html)。

## 實測與複核

本輪限定三項高必要性補強已完成：中央receipt資料16MiB空間真ENOSPC→retryable／原ID一次恢復；slot真lost→新slot先reserve再basebackup，跨3段／checkpoint後真PITR驗gap marker；同cluster兩分支二次PITR固定核定timeline／target。38定點通過18.00秒；616相鄰短回歸／12既有專用skip／coverage91.73%，48新單測通過（套件重疊不加總）。正式部署／Pi仍待驗，無COM／共享／長測重跑。 [結果與原RED／弱證據](../../output/no-pi-critical-closure-20261113/README.md)。code／Python／security／architecture複核通過；初版slot/base空窗HIGH已修，原run-03 PASS因缺gap反例只作歷史弱證據，新gate拒絕。CLI只輸出核定設定，promotion會產生新timeline，非自動判讀業務正確分支。
