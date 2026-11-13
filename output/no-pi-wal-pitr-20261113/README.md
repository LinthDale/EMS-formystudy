# 已確認資料的 WAL 保護與實體 PITR（2026-11-13）

本輪已完成程式修復與私有實測，沒有重跑長測、占用COM或更動共享部署。正式異失效域／TLS複寫與Pi仍待現場啟用驗收。

| 完成項目 | 實際結果 |
|---|---|
| 修中央ACK只保主庫本地commit的缺口 | field強制sync_wal；fsync/on、唯一具名sync peer、COMMIT後固定LSN必須已由獨立接收端刷盤覆蓋才ACK；field禁止local降級 |
| WAL接收端停止 | 真停自有pg_receivewal；只回retryable/database、A仍pending；恢復後同ID去重 |
| 主庫COMMIT後、ACK前WAL再中斷 | A在中央已存在1列，但postcommit gate失敗只回retryable，local仍pending；重新同步後原ID送達1次 |
| 實體備份 | 真pg_basebackup -Ft -Xstream，base.tar／pg_wal.tar／backup_manifest；兩個恢復副本都pg_verifybackup通過 |
| 備份後已ACK、local payload已刪B | B在備份結束後才入庫並獲ACK；原主庫SIGKILL後，只用basebackup＋獨立WAL（含.partial）PITR到B之後named restorepoint；B完整receipt、hash、canonical、committed_at、retention及四欄投影完全相同 |
| 缺WAL反例 | 相同basebackup配空archive，無法到指定restorepoint，PostgreSQL明確FATAL、未promote；不新建空庫假恢復 |
| 目標之後C與舊ACK | C的中央commit/ACK遺失發生在restorepoint之後，PITR後C不存在且local pending；換DB外generation、真舊ACK回放拒絕，再以原ID/hash補回 |
| 恢復庫重新保護 | 新timeline2先重新啟同步pg_receivewal，才開receiver ACK；A/B/C/新D各1列，pending=0 |
| migration020 | 兩次套用無錯；PUBLIC不可呼叫durability函式，receiver可呼叫但沒有pg_read_all_stats；固定pg_catalog search_path的SECURITY DEFINER只回boolean |
| 工具安全修復 | 動態create的commands.json改持FD原子rename，修複核發現的symlink覆寫入口；base/WAL檔名白名單、NOFOLLOW/NONBLOCK／regular／大小與64檔上限，prepare/恢復皆非root |

測試結果：

- **最終定點：36通過／13.89秒、零跳過**，`run-postcommit/`；1個真整合情境內含上述階段＋35個固定槽號回歸。`suite-assessment.json`要求完整catalog與12項具體證據，不僅看exit0。
- **相鄰短回歸：433通過／12個既有專用case跳過、33.91秒、coverage91.14%**，`regression-01/`。主程式store/receiver自該輪後未再變；後續只補工具防護和定點邊界。
- **最新工具／公平／空庫防呆：116通過／0.63秒、零跳過**，`tools-postcommit.xml`，包含最終新增的WAL symlink/FIFO/oversize/unknown-name拒絕與同一command recorder反例。
- 初始9個新單測：4失敗／5通過（`red.xml`）→9通過（`green-unit.xml`），證明修復前沒有field WAL保護。
- `run-01`原失敗保留：還原程序UID與archive權限不符；已改為同host UID非root，修好清理。`run-02`36通過8.79秒；`run-final`安全補強後36通過8.50秒；後續再補COMMIT後斷WAL邊界，以`run-postcommit`為最終PITR結論。
- 最終12個自建資源的log與移除都成功，sources_unchanged=true；原主庫實際KILL，恢復沒讀原PGDATA/pg_wal。共享容器核對見`final-verification.json`；既有長測結果與封存未修改。

**新舊交替規則**：傳送依capture_seq，先最新、再最舊，1:1成功交替。例已有1～10，順序10→1→9→2；若又來11，下一個latest機會選11。只有當前authenticated committed且本地原筆resolved成功才換邊；timeout／retry／淘汰後遲到ACK不換。普通重連不重置，程序重啟從latest，無跨重啟絕對公平或每筆固定秒數SLA。容量滿時則另按最舊開始淘汰存新，淘汰不假記送達。

**空白被當新庫的原因**：SQLite本來允許零位元檔初始化；舊constructor只看「沒有table就CREATE」，漏分「路徑從未存在」與「原檔被截空」。這是程式缺陷，上一輪已修，不是設計要清空舊資料。現在只有O_EXCL真正新建成功的路徑能初始化；既有zero／empty SQLite／damaged一律拒開且保留原檔，只有SQLite精確READONLY_ROLLBACK才做原生hot-journal恢復，絕不刪表、reset seq或清journal。本輪相鄰與專項仍通過。

範圍與限制：本輪是同一宿主、分離容器／儲存目錄的主庫單點損失實測，不能當成整個宿主／雙份儲存同毀或正式RPO/RTO驗收。真正field須獨立持久archive、專用TLS複寫角色、首份可驗basebackup與完整WAL保留鏈先到位。本次只提供修復碼與可部署範本／操作順序，沒有切共享v1。刻意還原到某筆已ACK之前，本就會丟棄該點之後內容；要保全部ACK須還原到最後已ACK commit之後。過去那輪只有dump、沒留下WAL的歷史B無法倒推再生；本輪已實際證明新保護機制可以救回同類B。

維護入口：[ADR049](../../doc/adr/ADR-049-synchronous-wal-ack-and-pitr.md)、[正式啟用／還原手冊](../../services/edge-receiver/WAL-PITR.md)、[整合測試](../../tests/integration/test_edge_wal_pitr.py)、[SQL020](../../infra/timescaledb/migrations/020_edge_synchronous_wal.sql)。獨立architect／Python／code／security複核通過，symlink問題已修並驗。

原理依據：PG15 [pg_receivewal](https://www.postgresql.org/docs/15/app-pgreceivewal.html)說明--synchronous才會即時刷盤／回報；[PITR文件](https://www.postgresql.org/docs/15/continuous-archiving.html)說明實體備份與連續WAL鏈。沒有使用每筆pg_switch_wal或假設非同步archive已經耐久。
