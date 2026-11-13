# 無Pi剩餘三項：中央備份還原、接收超量恢復、新資料送達延遲

2026-11-13（Asia/Taipei）。使用者要求測完剩餘三項、不重跑長測、有問題修復且清楚列結果。全部使用自有network-none MQTT／TimescaleDB副本、合成量測與固定QA身份；共享v1、COM及原24h未操作。本輪production修復為[ADR-048](../../doc/adr/ADR-048-v2-live-backlog-fairness.md)最新／最舊公平傳送，wire2／本地schema3與中央receipt／認證不變。

## 完成項目與實際結果

| 使用者指定項目 | 實際測試 | 結果 |
|---|---|---|
| **中央資料庫備份還原** | 真`pg_dump -Fc`完整備份私有ems，`createdb ems_restore`後Timescale pre_restore／pg_restore／post_restore；原庫保留作獨立oracle，復原只使用dump＋local | 備份A的sample／hash／commit時間／retention／四欄投影完全一致；還原點先為A/B/C＝1/0/0。外置generation換代，真MQTT舊ACK回放不能刪pending；C原ID／hash／投影補回1次、新D1次。**B在備份後已ACK且local payload已刪，無法由這份dump＋local補回，明列不可補，不宣稱零遺失。** [證據](run-final/database-restore.json)、[實際dump](run-final/central-backup.dump)、[host操作收據](run-final/lifecycle-control.json) |
| **接收端超量與恢復** | 私有投影表真ACCESS EXCLUSIVE鎖，先驗receiver確實阻塞於投影SQL，再以真MQTT送200封同一合法sample／envelope重複訊息 | broker全數收200，receiver佇列最高**64／64**、丟棄**135**次輸入；無DB commit時不發假committed且原pending保留。解除後rate拒**65**次，receiver存活，重送原筆與新筆各中央1列／pending0。[證據](run-final/receiver-overload.json)。這不是200獨立樣本吞吐驗收 |
| **大量舊資料補傳時的新資料延遲** | 真SQLite存1000筆三天前歷史，sender依production edge的每次step後wait1秒節奏運行，另進3筆新資料；不是加速drain | enqueue至中央commit約**1.044／2.091／2.098秒**，完成排名1／2／2；最舊歷史也前進，總帳**6已確認＋997待傳＝1003**，未丟掉或偷偷清空history。[證據](run-final/live-backlog-delay.json)。只3個私有本機短觀察，不是p95/p99／現場SLA |

**最終定點38項通過、0失敗／0跳過，18.90秒**（新3情境＋原35槽號）：[log](run-final/integration.log)、[JUnit](run-final/integration.xml)、[三份真故障／恢復閘門](run-final/suite-assessment.json)、[整輪與5容器清理](run-final/result.json)。

**相鄰短回歸419項通過、12個既有專用clock/TLS案例跳過，33.49秒，production combined line coverage91.04%**：[log](regression-final/integration.log)、[JUnit](regression-final/integration.xml)、[coverage](regression-final/receiver-coverage.json)、[整輪](regression-final/result.json)。包含新公平3案與新工具23案，38與419有重疊，不相加當獨立新案例。兩個最終run sources_unchanged=true、每輪5自建容器logs／清理通過。

延遲案的6確認／997待傳是**本地outbox／audit總帳**；停止sender時，待傳中可能含中央已commit、但本地尚未處理ACK的樣本，不拿此6當中央總入庫筆數。三筆新資料的延遲以中央commit返回觀察，沒有把本地enqueue或PUBACK當送達。

## 發現並修復

1. **production：FIFO使新資料排在整批歷史後。** [3案RED](fairness-red.log)重現50舊＋1新／連續新資料／ACK失敗下無公平服務。修[store.pending](../../services/delta/delta_device/reliable_store.py)增加明示newest選取，預設仍最舊；[sender](../../services/delta/delta_device/reliable_sender.py)初始最新，只有authenticated committed且本地原筆成功resolved後，最新／最舊1:1交替。timeout／retryable／已淘汰原ID的遲到ACK不消耗成功輪次。[54案GREEN](fairness-green.log)與真千筆積壓延遲確認；容量淘汰政策、UUID/hash、節流／退避不變。
2. **測試host備份讀取邊界。** 安全複核指出docker cp可保留容器symlink，普通host `read_bytes()`可能跟隨外檔／FIFO或無界讀；改只copy到host private隨機新子目錄，使用NOFOLLOW／NONBLOCK FD、一般檔案與16MiB上限、limit+1受限binary讀，再核SHA256才原子發布。symlink／FIFO／超限3反例另用Path.read_bytes spy，避免unsafe讀完才hash不符也僥倖當PASS。[24案修正GREEN](fix-green.log)；最終23個restore/load工具案含2個完整值一致反例，已收419回歸。
3. **測試計數範圍。** 初版lost-ACK案例把sender.next_send強制歸零，撞真batch limiter，未走到預定commit；移除強制並等待真captured committed後才還原。第二輪將恢復流量4封混入200封burst而記204，嚴格gate正確拒絕整輪；現於解鎖前freeze burst精確200，恢復另記total204，不放寬gate。

不把「備份後已ACK且payload已刪」視為本輪可修復的程式遺失：這是刻意選擇較舊備份的復原點限制。原DB僅留作測試oracle，未用它回填B；若實務仍有其他可用副本可另救援。要降低這類缺口須另驗中央WAL／更密備份與異機耐久策略，本輪沒有實作或宣稱WAL PITR、RPO0或RTO達標。generation回放案同時換session，證明該組合被拒，不隔離單一guard。

## 失敗歷程與複核

- [run-01](run-01/result.json)：1失敗／37通過，lost-ACK測試的人工加速碰真限流；未到還原，不作還原成功證據。其他短測結果保留。
- [run-02](run-02/result.json)：pytest38通過／18.97秒，但burst204與固定200契約不符，suite-assessment正確false；不作最終驗收。
- run-final：38／18.90秒，三份嚴格證據全true；還原A與補傳C逐欄一致、dump實體hash相符，source原庫未變。regression-final：419／12skip／91.04%。不疊加重跑次數。
- [Python／code／architect／security複核](reviews.md)最終Approve，原HIGH與MEDIUM及修正不刪除。原長測、容量、resilience／lifecycle封存保持。

## 重現與維護界線

`python3 services/edge-receiver/tools/verify_private.py --suite restore-load --output <全新目錄>`。新[整合測試](../../tests/integration/test_edge_restore_load.py)、[公平單測](../../services/delta/tests/test_reliable_fairness.py)、[工具反例](../../services/edge-receiver/tests/test_restore_load_suite.py)及[控制器](../../services/edge-receiver/tools/verify_private.py)為入口。完整邏輯備份採[Timescale官方備份還原步驟](https://www.tigerdata.com/docs/deploy/self-hosted/backup-and-restore/logical-backup)，版本／映像SHA及固定命令保存在各run；沒有使用pg_restore並行恢復。

host只接受固定db_backup／db_restore映射當輪owned database，source=ems、target=新ems_restore，無worker指定DSN／SQL／path／CID、不drop原庫；worker無Docker socket／serial／hostport。5自有容器沿network-none loopback，PKI臨時清除。備份只含合成私有DB，不是共享正式資料。受信測試worker仍可讀私有PKI，不宣稱完全惡意worker隔離。

1:1輪次在記憶體，重啟從最新開始，反覆重啟不保證跨boot嚴格公平。最新候選不等於每筆新樣本都有固定秒數；持續新資料時中間樣本會進最舊通道。吞吐不足仍可能延遲／依ADR-045容量淘汰。沒有20/s／7天回補、全負載percentile、Pi／SD／4G／中央備援／完整缺口UI驗收。原24h仍INTERRUPTED，未切共享部署或重跑長測。

[狀態](status.json)、[保護檢查](protection-check.json)、[來源SHA256](source-sha256.json)、[文件連結](link-check.json)、[本輪封存SHA256](artifact-sha256.json)另存，清單不雜湊自身。
