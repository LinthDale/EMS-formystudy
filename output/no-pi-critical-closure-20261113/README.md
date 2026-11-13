# 高必要性無Pi強化：三項完成並收尾

日期：2026-11-13。使用者核定「強化的必要性高的話就做」。本輪限於三項直接影響來源保留／WAL保護鏈／還原分支的短測，完成後收尾；未重跑長測，未操作COM、共享容器或正式DB，未部署新版本。

| 完成項目 | 實際測試與結果 |
|---|---|
| 中央DB資料空間耗盡 | 將真實edge_ingest.receipts表移到當輪主庫16MiB tmpfs tablespace，實際填滿。PostgreSQL在INSERT receipt擴檔時回報No space left on device；MQTT收到實際retryable ACK，原筆仍pending、無部分量測投影。刪測試filler後原ID入庫一次／pending0，最後移回pg_default並刪除測試tablespace。 |
| 複寫slot真失效與新鏈重建 | 停獨立WAL接收，限制slot保留並真切段／checkpoint，觀察wal_status=lost、restart_lsn=NULL、pg_receivewal exit1與拒絕原因；實際資料批次只收到retryable。保留舊slot／archive，先reserve新slot再做新basebackup；備份後故意提交gap marker、跨3段並checkpoint，驗base後啟新空archive接手。固定flush fence＋以新base/WAL真PITR查回reseed-gap，再generation換代開ACK；原已ACK及原pending兩筆各一列。 |
| 同cluster多timeline二次PITR | 真正建立同system ID的timeline2／3分支、相同named target；故意latest會還原出branch-three。使用核定timeline2則只得到branch-two，之後正常promote到新timeline4；原base／WAL輸入hash不變。證明cluster ID與checksum本身不足以核定分支。 |

## 修復與防回歸

- [還原預檢](../../services/edge-receiver/edge_receiver/backup_preflight.py) 的directory CLI現在必填外置核定`--expected-timeline`及`--target-name`；拒latest/current、缺值與設定注入字元。通過backup ID／checksum後輸出recovery_settings；**不自動寫PG設定或啟動PG**。維運仍須核定業務正確分支、套用輸出並檢查實際設定。原Python verify_backup函式仍只負責備份驗證。
- 初版reseed流程先base、後建立slot，獨立複核指出可能留下WAL保護空窗；已修成**slot reserve在base之前**，並以真實base後提交＋3切段/checkpoint＋新鏈PITR堵住只看當前flush的假安全判定。這是本輪新增維運／測試流程的修正，沒有部署過自動reseed服務。
- lost-slot測試改成等待實際retryable ACK，避免sender節流／握手短路被誤當故障拒絕。閘門保留舊run-03弱PASS作反例，缺gap鏈證據不能判通過。
- 程式、Python、安全、架構複核均通過，原HIGH已關閉；[複核記錄](review-status.json)。規範為[ADR-051](../../doc/adr/ADR-051-pinned-recovery-and-slot-reseed.md)，操作集中於[WAL-PITR](../../services/edge-receiver/WAL-PITR.md)。receiver／migration021／TLS／wire2／schema3及容量公平政策不變。

## 最終驗證

| 套件 | 結果 | 證據 |
|---|---|---|
| 三項定點整合＋原35槽號邊界 | **38通過／18.00秒**，3獨立證據條件全真、21自有容器清理成功、sources_unchanged=true | [result](run-final/result.json)、[JUnit](run-final/integration.xml) |
| 必要相鄰整體短回歸 | **616通過／12既有專用case跳過／36.06秒**，coverage **91.73%**，6自有容器清理成功、sources_unchanged=true | [result](regression-final/result.json)、[JUnit](regression-final/integration.xml)、[coverage](regression-final/receiver-coverage.json) |
| 新CLI／案例與證據閘門單測 | **48通過／0.05秒**：17還原目標／CLI、31 scope／真fixture／舊弱證據／24變異／4控制注入 | [JUnit](critical-unit.xml) |

上述套件有重疊，不加總為獨立案例數。核心失敗／恢復證據：[中央資料滿](run-final/central-data-full.json)、[slot重建](run-final/slot-reseed.json)、[同ID分支PITR](run-final/timeline-pitr.json)。來源雜湊／清理／舊封存與私鑰稽核：[final verification](final-verification.json)，全靜態封存：[manifest](artifact-sha256.json)。

保留過程紀錄：target-red為新增分支保護介面的14個TDD RED；run-01漏收docker stderr造成測試控制器FAIL，run-02的PGDATA／archive同名造成FAIL，均已修；run-03雖38PASS但缺backup→pickup空窗證據，不能作最終完成；run-04是修完整保護鏈後38PASS，run-final為完整固定來源的最終38PASS。

## 結案範圍與限制

三項高必要性條件與回歸均通過，本輪收尾，不自動追加強化。其餘測試若日後有新需求再納入；Pi／真溫度設備全鏈路及正式部署仍待另驗。

本輪中央滿載只驗receipt資料tablespace，不是整個pg_wal滿；tmpfs不是掉電耐久驗收。同宿主容器不是跨主機HA。新slot／base／archive流程由維運執行，本輪沒有新增自動reseed／failover；CLI也不能自動判定操作者核定的業務分支是否正確。PG15的空archive會從slot restart_lsn接手，適用條件見[官方pg_receivewal文件](https://www.postgresql.org/docs/15/app-pgreceivewal.html)。
