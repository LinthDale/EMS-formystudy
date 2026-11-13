# 無Pi前三項續測：broker重啟、SQLite損壞、憑證輪替撤權

2026-11-13（Asia/Taipei）。使用者指定先做前三項，不重跑長測、發現問題修復並清楚列結果。本輪只用自有network-none副本、暫存SQLite及私有PKI。原24h仍INTERRUPTED，未占COM、修改共享服務或切換v2部署。

## 完成項目與結果

| 使用者指定項目 | 實際測法 | 結果／證據 |
|---|---|---|
| **v2 broker真正重啟** | 執行production edge與真Modbus TCP simulator子程序；host只停止當輪自有broker，採集持續；原container ID重新啟動且StartedAt改變 | 同一edge PID在broker離線期間取得並SQLite提交**3筆新讀值**，當時中央0列；重新連線後各原ID中央1列、pending0，未以重建edge假裝重連。[結果](run-final/broker-restart.json)、[edge log](run-final/broker-restart-edge.log)、[broker log](run-final/broker.log) |
| **SQLite損壞／截斷** | 對含已commit樣本的副本破壞header、截成一半、截成零長度、替換成有效但空schema的SQLite；另驗真正新路徑可初始化 | 4種既有受損檔都拒開、bytes／SHA256不變、不建空queue、不重置序號。[header](run-final/corruption-header.json)、[截斷](run-final/corruption-truncated.json)、[零長度](run-final/corruption-zero-length.json)、[空SQLite](run-final/corruption-empty-sqlite.json)；新路徑仍正常seq1 |
| **閘道器client憑證輪替與撤權** | 同gateway/CN `qa-edge` 的新key/cert正常傳送；CA簽CRL撤舊serial，獨立openssl verify得到error23，重啟自有TLS broker強制既有連線重新驗證 | 舊／新憑證撤權前皆成功；活動中的舊TLS連線確實斷開，舊憑證重連被拒且原pending保留；新憑證仍能傳送該原ID、中央1列／pending0。[結果](run-final/certificate-rotation-revocation.json)、[host操作收據](run-final/lifecycle-control.json)、[憑證公metadata](run-final/certificate-metadata.json) |

**最終定點42項全部通過、0失敗／0跳過，28.40秒**：[log](run-final/integration.log)、[JUnit](run-final/integration.xml)、[六份證據閘門](run-final/suite-assessment.json)、[整輪及清理](run-final/result.json)。42＝broker1＋憑證1＋損壞4＋新路徑1＋原35槽號；不是42種全新故障。相鄰短回歸結果另見[status](status.json)與[regression-final](regression-final/integration.log)，未重跑長測。

**相鄰短回歸393項通過、12項既有專用clock/TLS案例跳過，33.00秒，production combined line coverage91.02%**；含原3個SIGKILL、容量／升版／轉換、35槽號及工具檢查。工具本身合67項（原private_suite32、receiver5、新lifecycle_suite30），新lifecycle30項已包含在393項內；定點42與393有重疊，不相加當獨立案例。12項跳過的完整原因保存在[JUnit](regression-final/integration.xml)，本輪真mTLS輪替／撤權實跑不等於該12項都重跑。

## 發現與修復

1. **實際production缺口：既有空檔被靜默重建。** 初版遇已存在的零長度或空schema SQLite會重建metadata／queue，掩蓋資料遺失並從seq1重新開始。[TDD RED](corruption-red.log)2失敗／3通過保留。修[reliable_store](../../services/delta/delta_device/reliable_store.py)：以O_EXCL區分真正新建與既有檔；既有檔先只讀檢查schema版本／表，零長度／空庫／損壞拒開、不建schema。[31案GREEN](storage-green.log)確認容量／schema2→3／離線轉換相容。
2. **修復途中回歸：只讀預檢擋住hot journal復原。** 前輪兩個commit前SIGKILL案真正重現`SQLITE_READONLY_ROLLBACK`，[RED](hot-journal-red.log)2失敗／1通過保留。只對此精確錯誤改以`mode=rw`交SQLite原生rollback，再驗schema；rw不建立缺失檔案、不生成新schema。其他錯誤不走fallback，避免為恢復而清空損壞庫。修後[78項工具／儲存檢查](security-and-storage.log)通過，包含原三個SIGKILL與4損壞案。
3. **新測試控制器的host檔案邊界已加固。** 複核指出worker可預建固定response.tmp或log／result symlink，使host按路徑讀寫外檔。現在host寫入全部使用隨機exclusive FD寫完原子rename；生命週期log持匿名FD讀取，request／JUnit／proof讀取皆NOFOLLOW、NONBLOCK、一般檔案及大小限制。新單測驗證外部檔不變、symlink／超大／目錄拒絕、固定op／UUID／當輪owned CID，worker不能指定host命令或目標。[工具與儲存GREEN](security-and-storage.log)。

broker初版前置條件要求持續採集時queue必須降至0，會因採集與傳送速率接近而誤FAIL；改驗已commit至少一筆，再以停止broker時的seq高水位界定真正離線新採樣，未放寬原ID／DB核對。測試不是要求重跑長測。

## 歷程與獨立複核

- [run-01](run-01/result.json)：41通過／1失敗，broker前置誤FAIL；憑證與損壞證據保留，沒有改寫成PASS。
- [run-02](run-02/result.json)：42測試通過／28.88秒，但source執行中因控制器安全修正而改變，整輪`passed=false`／`sources_unchanged=false`，**不作最終驗收**。
- run-final：42／28.40秒，完整35案identity與六份故障證據通過、source不變、5自有容器logs／清理通過。最終相鄰regression-final另存，不疊加重跑次數當新增測試數。
- [Python／code／security複核](reviews.md)最終均Approve；中途HIGH、失敗run及修正前備份保留。原有長測、容量／resilience等封存不改寫。

## 操作與界線

重現：`python3 services/edge-receiver/tools/verify_private.py --suite lifecycle --output <全新目錄>`。新[test_edge_lifecycle](../../tests/integration/test_edge_lifecycle.py)、[test_reliable_corruption](../../services/delta/tests/test_reliable_corruption.py)、[test_lifecycle_suite](../../services/edge-receiver/tests/test_lifecycle_suite.py)是維護入口。worker不掛Docker socket／serial／hostport；host只接受broker_stop／broker_start／revoke_old_client，映射到本run已有owned IDs，無任意CID／檔案路徑／命令輸入。PKI、CA key及CRL全為本次私有臨時資料，結束清除。

這是**受信測試程式的私有PKI／命令與檔案邊界驗證**；worker可讀測試PKI，不宣稱完整惡意worker隔離或正式最小憑證部署。撤權以CRL＋broker重啟強制斷線完成，不宣稱只更新CRL檔就會即時終止所有已建立TLS session；server憑證輪替、正式CA／CRL分發／撤權SLA仍另驗。損壞案測啟動保護，不保證能修復已壞SD或追回資料；實體掉電／Pi／4G／中央PITR也不在本輪。

[status](status.json)、[保護檢查](protection-check.json)、[來源SHA256](source-sha256.json)、[連結檢查](link-check.json)、[封存清單](artifact-sha256.json)另存，清單不雜湊自身。
