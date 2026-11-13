# 最新量測優先：容量循環保留修訂與驗證

2026-11-13（Asia/Taipei）。使用者明確要求「新資料比舊資料重要，應該要從最舊資料開始覆寫」。依[ADR-045](../../doc/adr/ADR-045-newest-first-edge-retention.md)／[PRD-0021 §15.5](../../doc/prd/PRD-0021-multi-device-edge-reliability.md)實作；本輪變更本地量測queue，未切共享v1、操作COM或重跑長測。

## 完成的行為

- queue／quarantine、audit筆數或SQLite主檔bytes滿時，依capture_seq由最舊開始淘汰，保留新進量測。正常容量內不主動刪除；不依ACK先後或牆鐘倒退判斷新舊。bytes不足以1／2／4…最舊前綴重試，可能多刪部分前綴，未承諾每次最少刪除筆數。
- 舊資料淘汰、新樣本UUID/hash／seq／window及有界摘要在同一SQLite交易；新寫入若失敗，舊資料、序號、窗口及摘要全部回滾，不先刪舊資料再另存新資料。
- 容量淘汰不記committed。`retention_status()`分開累積未確認送達副本、已確認audit及quarantine淘汰，保留最近序號span及末筆ID/hash，寫`capacity_eviction` warning。未確認不等於中央必定缺失；span也不是全段都遺失的清單。摘要有界，完整逐筆淘汰ledger、上傳中央與缺口UI仍未實作。
- 舊樣本已送出、等待ACK期間也可淘汰；同一合法session的真ACK晚到，原ID已不存在則返回False、記`ack_for_retired_sample`，不刪replacement、不重建舊資料、不假記成功。中央已有的舊量測不被本地回收刪除。
- 本地schema升3，MQTT wire仍2、中央migration仍019。完整schema2同交易補必要metadata並升版，舊版拒開schema3。兩個非唯一加速索引另用交易，僅SQLITE_FULL時完整回滾該索引交易並記`retention_indexes_deferred`，仍可沿掃描查詢運作，下次重啟重試；無索引效能未驗。若必要metadata也無法寫入，升版回滾保留舊檔。
- v1離線轉換仍須完整容納來源pending；bytes不足造成任何輪替，整體拒絕且不發布部分目的檔。無引用window同交易回收，避免另一張表無界累積。

## 驗證入口與證據

最終baseline-final：**336項通過、12項既有專用case未重跑，27.17秒，production combined line coverage91.04%**。23項容量案例已包含在336項內，不另外疊加。八類故障＋35槽號的獨立短套件另列如下。

最終faults-final-02：**43項通過、0失敗／0跳過，9.11秒**；35槽號完整案名與真DB逾時證據閘門通過。兩個最終run各自5容器均回收、來源unchanged，未對共享服務故障注入。

| 範圍 | 證據與判定 |
|---|---|
| 最終相鄰短回歸 | [baseline-final log](baseline-final/integration.log)、[JUnit](baseline-final/integration.xml)、[coverage](baseline-final/receiver-coverage.json)、[整輪／清理](baseline-final/result.json)，包括23容量案例、35固定槽號、16驗收閘門與真MQTT／DB。最終筆數／coverage另見[status](status.json) |
| 八類短故障＋35槽號 | [faults-final-02 log](faults-final-02/integration.log)、[機器驗收](faults-final-02/suite-assessment.json)、[整輪／清理](faults-final-02/result.json)，43案；兩容量案已由拒新改為最舊淘汰／最新保留，其他DB／ACK／mTLS證據門檻保持 |
| 真同session ACK淘汰競態 | [結果](baseline-final/capacity-late-ack.json)：舊樣本中央commit後、真ACK送出前存replacement淘汰舊本地列；ACK不刪新列，兩樣本中央各1列、新樣本之後正常送達，pending0 |
| 離線12筆限3 | [結果](baseline-final/capacity-offline-recovery.json)：最舊9筆本地淘汰，恢復連線後只傳最後3筆；逐個原ID查中央為0×9＋1×3、pending0，沒有重複入庫 |
| SQLite真主檔容量 | [結果](faults-final-02/sqlite-full.json)：64KiB quota連續存20筆12KiB snapshot，保留最新suffix，原ID/hash不變、重開integrity=ok且不超quota；無法回收足夠空間的真FULL另有單測驗全回滾 |
| audit已ACK後滿 | [結果](faults-final-02/audit-capacity.json)：audit cap1時回收舊已確認索引，新seq2成功接納，不把audit回收誤記中央缺失 |
| 真舊schema2滿載升版 | [fixture來源](legacy-fixture-provenance.json)、[真舊檔](legacy-schema2-full.db)、[RED](upgrade-red.log)、[23項GREEN](retention-final.log)。fixture由封存舊碼生成，61,440 bytes／2筆12KiB／無新index；先重現新增index滿載失敗，再驗延後index可升版、既有兩筆不先刪、後續新筆可輪替 |
| 舊版拒schema3 | [獨立舊碼驗證](upgrade-compatibility.json)：以before原碼真建schema2，完整樣本升3，舊原碼重開確實ValueError，原ID/hash保留 |

23個容量案例位於[test_reliable_retention.py](../../services/delta/tests/test_reliable_retention.py)，涵蓋queue／audit滿、quarantine、時間／ACK排序、重啟、最舊suffix、真FULL可回收／不可回收、invalid新資料、寫新transaction失敗、並行enqueue、windows有界、schema2升版與missing摘要拒開；另有migration及MQTT相鄰案例。12個既有專用clock/TLS測試本輪未重跑，跳過原因保留在JUnit；faults中的真mTLS正反測試有實跑，不能把不同套件混稱全部TLS都跑過或都未跑。

## RED、修正與複核歷程

[初版RED](red.log)14失敗，確認舊策略拒新／缺摘要；[green-01](green-01.log)15項、[green-02](green-02.log)47項相鄰短測保留。Code reviewer另重現本地ns可超int64而wire us仍合法，會淘汰後無法重啟；已在交易前統一奈秒範圍，補5非法邊界與最大合法值重開。架構複核再以真舊滿載檔抓到index升版空間不足；[upgrade-red](upgrade-red.log)保留，改可延後索引後23案通過。

[baseline-01](baseline-01/result.json)335通過／12跳過、91.07%；[faults-01](faults-01/result.json)與[faults-final](faults-final/result.json)各43通過。這些是修正途中不同凍結版本，最終以baseline-final／faults-final-02為準，不疊加重跑次數當新測試數。[獨立複核](reviews.md)涵蓋Python／code、架構及安全；先前HIGH與處理方式不從報告刪除。

## 維護與界線

程式：[ReliableOutbox](../../services/delta/delta_device/reliable_store.py)、[sender](../../services/delta/delta_device/reliable_sender.py)、[離線轉換](../../services/delta/delta_device/migrate_delivery.py)。部署／升版／備份及回滾見[receiver README](../../services/edge-receiver/README.md)。正常ACK與容量淘汰是兩條明示路徑；測試控制器的完整35案identity與真DB逾時證據閘門保持。ADR、PRD、三圖、API文件、風險／威脅、參數與操作入口同步，不新增對外REST／topic／權限或套件。

升版前停目標舊程序並備份；不並行新舊writer、不手改user_version降級。7天完整性只在核定容量與保留窗口內成立；滿容量後舊資料可失去補傳機會。這是SQLite主檔quota短測，非填滿主機磁碟／SD或實體掉電驗收；I/O／硬體故障時仍可能無法存新資料。中央receipt保留／PITR、控制帳本、Pi／ADTEK／4G、多設備scheduler、完整manifest／中央缺口UI與效能SLA仍另驗。原24h仍INTERRUPTED。

[保護檢查](protection-check.json)核對所有舊封存與frozen／verifier、共享容器及自有清理；[來源雜湊](source-sha256.json)、[文件連結](link-check.json)、[本輪封存清單](artifact-sha256.json)另存，清單不雜湊自身。
