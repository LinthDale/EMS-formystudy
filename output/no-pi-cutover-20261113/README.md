# 新增無Pi切換／受限權限／MQTT碰撞短測（2026-11-13）

本輪新增3類情境、5個整合案例。最終以`run-inflight`為準：**40項通過／15.00秒、零跳過**（新5案＋35個固定槽號回歸）。另`tools-inflight.xml` **131項通過／0.28秒、零跳過**，含20項新入口／防假通過閘門與既有控制器／轉換單測。沒有重跑長測、占用COM或更動共享服務。

| 新增測試 | 執行方式 | 結果 |
|---|---|---|
| 正式mTLS＋受限DB帳號＋同步WAL的完整送達／缺列修復 | 新建只繼承ems_edge_receiver的LOGIN，查證superuser／replication／createdb／createrole均false；4個實際DELETE／改receipt內容／建表／pg_shadow讀取皆被拒；真MQTT送達後刻意丟ACK、刪私有投影並撤INSERT，再恢復權限 | 真InsufficientPrivilegeError只回retryable，本地原筆保留；恢復後原ID補投影1次，原receipt committed_at不變，pending0 |
| v1→v2轉換SIGKILL：第一筆已寫、整批尚未完成 | 子程序真轉換，寫完首筆停在marker（核PID與stage）後SIGKILL；重新轉換至新正式路徑 | 中斷時正式目的檔不存在；v1原檔逐bytes不變；只轉換仍pending兩筆，不復活已ACK的一筆；實送中央各1列 |
| v1→v2轉換SIGKILL：完整轉好、發布前 | 在os.link呼叫之前停住並SIGKILL | 沒有發布部分目的庫；重試完整轉兩筆，mapping／原時間與值保留，中央各1列、pending0 |
| v1→v2轉換SIGKILL：發布後 | os.link真成功後、目錄fsync呼叫前SIGKILL；正式目的庫已存在 | 目的庫完整／integrity_check=ok，含完整migration receipt與2筆ID mapping；再次轉換拒覆寫，既有目的庫送達各1列、pending0。僅驗程序中斷，不冒充斷電／儲存持久化驗收 |
| 重複mTLS MQTT client ID碰撞 | 原sender有真已commit但ACK遺失的inflight batch；另一合法client用同ID連入。斷線callback持sender.lock先拍ready/challenge/batch再呼production reset，確認尚未timeout | broker確實踢原連線；原筆保留，新採樣仍可入本地；原sender自動重連、新challenge不同，receiver真重播舊ACK被觀察且拒絕；原／新中央各1列，pending0 |

本輪發現並修的是**測試證據強度**：首輪碰撞前先等ACK逾時，session已被timeout重設，不能單獨證明碰撞使活躍批次失效。改成ACK仍等待時碰撞，並核對斷線callback當下的真狀態；`inflight_at_collision`和`observed_disconnect`成為驗收必要證據，新增「其實沒inflight／timeout已先重設／不同session」三個反例。產品程式未發現需修缺陷，本輪沒有修改sender／store／receiver／migration SQL。

證據版本：

- `gate-red.xml`：新增入口／驗收尚未實作時17項RED，保留原反例。
- `run-01`：40通過／16.01秒，初版碰撞測試有上述強度限制，不能用來聲稱精確inflight碰撞邊界。
- `run-final`：背景inflight版本40通過／15.18秒。
- **`run-inflight`：實際callback狀態核對版40通過／15.00秒**，五份場景JSON與suite-assessment完整通過，35案catalog完整，sources_unchanged=true。
- `tools-final.xml`128通過為較早工具版；**`tools-inflight.xml`131通過／0.28秒**含最新20個閘門案，缺案／替代案／skip／高權限／local ACK／假crash／部分發布／重複／碰撞未發生或已timeout／舊ACK被接受／缺證據都不能過。
- code、Python與security獨立複核通過，原測試強度意見已修；詳review-results.json。
- 六個自建資源（anchor、兩broker、DB、WAL receiver、worker）log／移除全成功。共享17容器與舊封存雜湊核對見final-verification.json。

本輪coverage是只跑5個新場景的定點覆蓋，不作全程式coverage承諾；沒有為了數字重跑上一輪整套回歸或長測。子程序SIGKILL不代表實體SD掉電；DB role測試的傳輸是mTLS，但私有PostgreSQL沿原network-none QA trust配置，不是正式DB TLS或跨主機HA驗收。Pi／ADTEK／實體SD／4G與正式部署依舊另驗。

維護入口：[新整合案例](../../tests/integration/test_edge_cutover.py)、[控制器](../../services/edge-receiver/tools/verify_private.py)、[新驗收反例](../../services/edge-receiver/tests/test_cutover_suite.py)、[PRD-0021](../../doc/prd/PRD-0021-multi-device-edge-reliability.md)、[ADR-043](../../doc/adr/ADR-043-opt-in-committed-telemetry.md)／[ADR-049](../../doc/adr/ADR-049-synchronous-wal-ack-and-pitr.md)。
