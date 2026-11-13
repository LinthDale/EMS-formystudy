# 無Pi：邏輯損壞、異常批次與SIGTERM短測（2026-11-13）

本輪新增3類、31個案例：25個SQLite一致性／競態／溢位案例、5種真MQTT無效批次、1個真DB等待時SIGTERM及完整edge重啟。**最終66項通過／22.08秒、零跳過**（新31＋35固定槽號回歸）；產品儲存程式有修復，尚未部署共享。沒有重跑長測或使用COM。

| 完成項目 | 原先發現的問題／測法 | 修復與結果 |
|---|---|---|
| SQLite結構正常但資料邏輯錯亂 | quick_check=ok，sequence／clock回退、audit缺失／hash／state／seq不符、orphan audit原本都可開庫 | 開庫同交易查queue/audit關係、狀態、重複序號及現存audit高水位，拒開且檔案SHA256不變，不清空或自動補造 |
| 送出前與ACK刪除前的身分核對 | persisted payload可與SQL ID／seq／hash／configured device或window不符；live audit缺失時原ACK處理仍可刪source | pending驗canonical wire/hash、設定身分、SQL列、audit/window；ACK在同一BEGIN IMMEDIATE再次驗，再更新audit／刪payload。不一致整筆回滾、來源保留；已容量淘汰的遲到ACK仍False |
| 執行中高水位回退 | 只加開庫檢查仍會漏：舊seq1已ACK或滿cap後，把活躍metadata.sequence改0，下一筆可重用seq1；中央會因stream/seq衝突拒新筆 | enqueue在淘汰之前、同一寫入交易先比對現存audit的MAX(seq)／MAX(source time)，回退拒絕，來源、摘要與序號不改 |
| 合法容量輪替的並行讀取 | queue讀完至audit/window讀取間，另一writer正常淘汰可造成假損壞判定 | pending加短BEGIN共用一致快照；真writer到retire邊界後reader仍讀完整舊筆，釋放後新筆保留 |
| 容量摘要int64溢位 | 合法最大counter再加1會提交超界摘要，使下一次開庫失敗 | 累加後、刪舊資料前再驗retention，超界整個替換回滾，不丟source、不提交不可重開的狀態 |
| 真MQTT異常批次 | bad hash混批、同ID重複、JSON重複key、非法UTF-8、過深JSON，共5案皆經實際receiver parser | 無ACK、兩原筆本地保留、中央0/0；receiver繼續服務，合法原ID恢復中央1/1、pending0 |
| DB仍等待時正常SIGTERM | 真私有projection表鎖，pg_stat_activity確認receiver在Lock wait；對真TCP採集edge子程序SIGTERM | 約0.1135秒正常exit0，退出後DB lock仍在、本地3筆原payload保留。再啟完整edge程序續採送達，最後11筆ledger／receipt／projection逐ID、hash、來源微秒時間、device、四欄值一致且各1列，pending0 |

程式修復在[reliable_store.py](../../services/delta/delta_device/reliable_store.py)。本地schema3／wire2、容量最舊淘汰、最新／最舊成功1:1及中央同步WAL契約不變。僅新增可延後的`audit_time(sampled_at_us)`加速索引；與既有audit_sequence/audit_window同一optional transaction，SQLITE_FULL則回滾該索引交易並warning／掃描查詢保持正確。兩個MAX用獨立scalar subquery，正常可走兩個covering indexes；`watermark-query-plan.json`驗證計畫及刪索引後正確fallback，不是600k/Pi效能驗收。

測試結果與證據版本：

- `consistency-red.xml`：原版18案中16失敗／2通過，含缺audit時ACK可刪source；先留反例再修。
- `consistency-green.xml`：第一階段＋舊相鄰55通過。
- `live-boundaries-red.xml`：複核指出live回退、重複seq、counter溢位和read snapshot邊界後再留7失敗／18通過。
- `consistency-final.xml`：25新案＋原損壞／恢復／容量／轉換共62通過／6.94秒。
- `run-01`：66通過／22.89秒；SIGTERM當時僅核projection筆數／唯一性，原版保留。
- **`run-final`：66通過／22.08秒**，補投影ID集合、微秒來源時間／device／四值逐筆比canonical；13份具體證據檢查全true，6自建資源log／清理皆成功、sources_unchanged=true。
- **`regression-final`：500通過、12項既有專用case跳過／34.12秒，production coverage91.36%**。這是短回歸，不是長測。主程式store之後未改；最新projection證據補強另由run-final和tools-final驗，沒有把舊500項算成已跑新projection案。
- **`tools-final.xml`：210通過／7.28秒、零跳過**，包括最新20個完整驗收／假PASS反例、25新一致性及原相鄰儲存／工具案。漏案、改名、skip、改動損壞檔、假拒絕、部分寫入、假ACK、未經parser、重複恢復、非真DB等待／SIGKILL冒充SIGTERM、投影ID或值錯、缺證據都不能過。
- code／Python／security獨立複核通過；具體HIGH與MEDIUM及修正見review-results.json。
- 原共享17容器與12份舊封存全部核SHA256，檔數／來源核對見final-verification.json；本輪全靜態證據另有artifact-sha256.json。

範圍：開庫是一次SQL關係掃描，沒有全量Python載入payload；送出／ACK只驗選中筆。高水位依**現存audit**比對，不是持續全庫bitrot掃描，也不能辨識整份一致的舊備份回滾或管理員完整重算偽造。容量已淘汰而不再留存的歷史不會被這些檢查憑空追回。拒開後須保留原檔／journal、按已驗證備份及來源核對復原，不能手改seq或重建空庫假恢復。實體SD掉電、600k庫在Pi的啟動耗時、Pi／ADTEK／4G與正式部署均仍另驗；本輪SIGTERM是程序正常退出，不冒充斷電驗收。

入口：[新一致性測試](../../services/delta/tests/test_reliable_consistency.py)、[真MQTT／SIGTERM測試](../../tests/integration/test_edge_integrity.py)、[新驗收閘門](../../services/edge-receiver/tests/test_integrity_suite.py)、[PRD-0021](../../doc/prd/PRD-0021-multi-device-edge-reliability.md)、[ADR-043](../../doc/adr/ADR-043-opt-in-committed-telemetry.md)／[ADR-045](../../doc/adr/ADR-045-newest-first-edge-retention.md)。
