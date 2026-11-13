# 無Pi續測：崩潰、鎖定／唯讀、線上備份與v2伺服器憑證

2026-11-13（Asia/Taipei）。使用者要求繼續其他不需要Pi的測試、不重跑長測、發現問題就修復並清楚列出結果。本輪測試現行wire2／本地schema3及ADR-045最舊淘汰政策；**production程式未修改，未切共享部署、占用COM或啟動長測**。

## 完成項目與結果

**新增9案全部通過，加35個原槽號固定回歸，共44項通過、0失敗／0跳過，11.09秒**。驗收工具另**32項通過**（原16＋本輪新增16，非32項全新功能）。[最終log](run-final/integration.log)、[JUnit](run-final/integration.xml)、[九份證據閘門](run-final/suite-assessment.json)、[整輪及清理](run-final/result.json)、[工具單測](controller-final.log)。下列9案不重複計數重跑次數。

| 新增測試 | 完成結果 | 原始證據 |
|---|---|---|
| 刪舊後、寫新前SIGKILL | 真子程序exit=-9；有rollback journal及**constructor之後**的主檔變更；重開還原原ID/hash、seq1、淘汰0，下一筆seq2 | [crash-after_retire](run-final/crash-after_retire.json) |
| 寫新／摘要完成、commit前SIGKILL | 真dirty-page主檔與41,472 bytes journal；重開整筆回滾，新樣本／新窗口／淘汰數不殘留，原筆完整 | [crash-before_commit](run-final/crash-before_commit.json) |
| commit後SIGKILL | 重開與enqueue返回的完整新sample逐字相等（含UUID/hash），seq2／淘汰1保留；下一筆seq3 | [crash-after_commit](run-final/crash-after_commit.json) |
| SQLite writer lock | 真BEGIN IMMEDIATE鎖住約5.005秒，得到SQLITE_BUSY；舊筆與淘汰0保持，解鎖後新筆seq2正常循環 | [sqlite-busy](run-final/sqlite-busy.json) |
| SQLite檔案唯讀 | 在非root私有worker將自有檔案設0400，真SQLITE_READONLY；失敗不淘汰、不前進序號，恢復0600後正常接納 | [sqlite-readonly](run-final/sqlite-readonly.json) |
| 線上備份期間繼續淘汰 | SQLite backup每頁複製的progress callback內，另一thread實際提交seq13–20；備份最後一致保留16–20、淘汰15、integrity=ok | [online-backup](run-final/online-backup.json) |
| v2不受信server CA | 真TLSverify_code19，再觀察production ReliableSender實際connect_fail；原ID/hash保留，改合法mTLS後中央1列／pending0 | [tls-server-untrusted-ca](run-final/tls-server-untrusted-ca.json) |
| v2 server主機名稱不符 | 真TLSverify_code64；原資料保留，合法連線恢復後同原ID中央只1列／pending0 | [tls-server-wrong-host](run-final/tls-server-wrong-host.json) |
| v2 server憑證過期 | 真TLSverify_code10；原資料保留，合法連線恢復後同原ID中央只1列／pending0 | [tls-server-expired](run-final/tls-server-expired.json) |

前三案是Linux自有程序SIGKILL與SQLite rollback-journal recovery，**不是實體掉電／SD驗收**。備份案驗一致性，不是把舊stream備份任意還原成可上線writer的PITR驗收。TLS恢復走真receiver與PostgreSQL committed ACK，不以PUBACK當入庫證明。

## 發現並修復的問題

1. **崩潰測試可能假通過（HIGH，已修）：**初版hash在parent啟動child前取得，而child constructor提交PRAGMA可能先改主檔；因此`main_file_changed=true`不能獨立證明被kill的交易真的落盤。改在child constructor完成後、enqueue前重新取baseline；marker保留兩個實際SHA256及baseline_stage，閘門核對合法64hex／值不同與journal，不只信boolean。commit後另核對完整原sample，不允許重建ID/hash蒙混。
2. **完成訊號讀取競態（已消除）：**原ready.json直接write_text可能讓parent先讀到空／半截JSON；改寫tmp完成後os.replace原子發布。SQLite讀取／backup連線改closing明確釋放。

[反例重現](crash-proof-counterexamples.json)以run-01凍結舊controller證明「只有constructor變更」「錯baseline階段」「commit後identity改變」原本都可假PASS，新版三案均拒。新增判定函式[覆蓋96.875%](new-assessment-coverage.json)，32單測含skip／缺案／重複、非SIGKILL、無dirty page、錯回復序號、假鎖、非並行備份、錯TLS原因／未真連線及缺proof等。

本輪沒有觀察到需要修改production採集／sender／receiver的失敗；不能因此宣稱所有故障都已排除。修復的是驗收工具的證據嚴格度與測試可靠性。production總體覆蓋91.04%是[前輪336項結果](../newest-first-retention-20261113/README.md)，本輪未重跑該整套；resilience log的45%是本輪定點路徑對全部production檔案的分母，controller unit的39%也含未執行的provisioning/main，兩者都不是全系統退步或完整覆蓋聲明。

## 執行歷程與隔離

[storage-first](storage-first.log)6案通過；[controller-red](controller-red.log)13案因缺新suite／assessment失敗後，[controller-green](controller-green.log)29案通過。[run-01](run-01/result.json)初版44案exit0保留，**其前三crash案不作dirty-spill已驗到的最終依據**。收緊證據及加3反例後，[storage-final](storage-final.log)6案、[controller-final](controller-final.log)32案、run-final44案通過。[獨立Python／code複核](reviews.md)均Approve，原HIGH及修正保留。

重現：`python3 services/edge-receiver/tools/verify_private.py --suite resilience --output <全新目錄>`。固定只選新6 storage＋3 TLS及原35槽號，無長測。工具自建network-none anchor、demo broker、獨立mTLS broker、DB、worker五容器；TLS 8886／8887／8888只在該私有namespace的loopback，無hostport、Docker socket或serial掛入worker。真SIGKILL只用本test建立的Popen handle；唯讀／鎖／backup只作用暫存DB。每輪5容器回收，臨時PKI清除，僅保存公憑證metadata與命令／log。

來源：[storage測試](../../services/delta/tests/test_reliable_resilience.py)、[v2 TLS整合](../../tests/integration/test_edge_resilience.py)、[控制器](../../services/edge-receiver/tools/verify_private.py)、[工具反例](../../services/edge-receiver/tests/test_private_suite.py)。[保護檢查](protection-check.json)、[結果](status.json)、[來源SHA256](source-sha256.json)、[文件連結](link-check.json)、[封存SHA256](artifact-sha256.json)另存；舊封存及原長測資料不改寫。
