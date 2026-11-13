## 2026-11-13 最新：高必要性三項補強完成／本輪收尾

本輪限定三項高必要性補強已完成：中央receipt資料16MiB空間真ENOSPC→retryable／原ID一次恢復；slot真lost→新slot先reserve再basebackup，跨3段／checkpoint後真PITR驗gap marker；同cluster兩分支二次PITR固定核定timeline／target。38定點通過18.00秒；616相鄰短回歸／12既有專用skip／coverage91.73%，48新單測通過（套件重疊不加總）。正式部署／Pi仍待驗，無COM／共享／長測重跑。 [完整結果](../../output/no-pi-critical-closure-20261113/README.md)、[唯一還原／slot操作手冊](../../services/edge-receiver/WAL-PITR.md)、[ADR-051](../adr/ADR-051-pinned-recovery-and-slot-reseed.md)。本輪到此收尾；已指定無Pi項目完成，其餘強化不自動追加。Pi／溫度設備全鏈路及正式部署仍待驗。

## 2026-11-13 最新：三項WAL安全／滿載／損壞短測完成

DB／WAL TLS、128MiB archive ENOSPC恢復、損壞backup／WAL及有效外cluster拒絕已私有短測；55通過62.52秒，568短回歸／12專用skip／coverage90.99%，原已ACK資料PITR36通過。修field db_tls強制驗證、021版本化TLS＋固定角色WAL predicate、外置expected_system_id及tar資源預檢。無COM／共享部署／長測重跑；正式異失效域與Pi仍待驗。 [結果與證據](../../output/no-pi-wal-security-20261113/README.md)；正式啟用依[WAL/PITR手冊](../../services/edge-receiver/WAL-PITR.md)，先migration019／020／021與TLS角色／外置server key，還原核可信cluster ID後才啟PG。

## 2026-11-13 最新：邏輯損壞修復／異常MQTT批次／SIGTERM完成

[本輪證據](../../output/no-pi-integrity-20261113/README.md)：25新一致性／競態／溢位＋5惡意批次＋1真DBwait中SIGTERM／完整edge重啟，與35槽號共66通過22.08秒；500短回歸／12既有專用skip／91.36%，最新210工具／儲存通過。已修store quick_check漏掉邏輯損壞、live水位倒退可重用seq／淘汰舊筆、audit缺失ACK仍刪、pending跨快照誤報與retention counter溢位；schema3/wire2／容量最舊淘汰／sender公平／WAL guard不變，新增optional audit_time FULL可延後掃描。初始16RED與後7RED、原中間run保留；最終SIGTERM約0.1135秒exit0，11筆逐ID/hash／投影source time/device/四值一致且各1，pending0。

此為既有完整性契約bugfix，未部署共享／占COM／重跑長測，6自有容器清理；遇語意損壞保留原庫/journal，不手改seq、不建空庫，先核備份／來源再復原。不是全量bitrot掃描、完整舊庫回滾偵測、600k/Pi性能或實體掉電／SD／4G驗收。
## 2026-11-13 最新：其他無Pi切換短測完成

[本輪證據](../../output/no-pi-cutover-20261113/README.md)：新增3類5案＋35槽號共40通過15.00秒；另131工具／轉換單測通過。受限field DBrole＋mTLS＋syncWAL、真撤INSERT保持pending／恢復同receipt補投影；v1轉換首筆後／發布前／後真SIGKILL，原檔不變／不發布部分正式庫／映射保持、pending各入中央1次；合法重複clientID在原batch仍inflight時踢線，callback核ready/challenge/batch、重連換challenge／舊ACK拒、原新各1。修初版碰撞先等timeout造成的證據弱點，production無缺陷需修。只改測試／工具，原6自建容器清理，無shared／COM／長測操作；Pi／實體SD掉電／4G／正式部署仍待驗。
## 2026-11-13 最新：WAL保護已ACK資料與實體PITR

使用者要求修復backup後已ACK、本地刪除卻不在舊dump的缺口。新field receiver強制sync_wal：主庫COMMIT及具名獨立WAL fsync覆蓋固定LSN後才ACK。私有PITR已用實體basebackup＋獨立WAL（含partial）、原主庫KILL後救回B，缺WAL無法達標而拒啟動，C保留pending原ID補送。[證據與結果](../../output/no-pi-wal-pitr-20261113/README.md)、[ADR-049](../adr/ADR-049-synchronous-wal-ack-and-pitr.md)、[維運唯一手冊](../../services/edge-receiver/WAL-PITR.md)。此為同宿主隔離容器驗單主庫損失，正式異失效域／TLS角色／首份basebackup仍須啟用驗收；沒有WAL的舊歷史缺口不可憑空重建。未切共享／用COM／重跑長測。

新舊傳送：依原capture_seq先最新再最舊，只有authenticated committed且本地成功resolved才換邊；失敗／retiredACK不換。容量滿另由最舊開始淘汰存新。既有空檔被當新庫是已修bug：只在路徑不存在且O_EXCL新建成功才初始化，既有zero／empty／damaged拒開保留；精確hot-journal回滾不等於清空。
# 採集測試接手：溫度 → Pi → EMS

## 2026-11-13 最新：還原／接收超量／歷史補傳新資料延遲完成

[本輪證據](../../output/no-pi-restore-load-20261113/README.md)定點38通過／18.90秒，419相鄰通過／12既有專用case跳過／coverage91.04%。真正pg_dump-Fc還原到新ems_restore，備份A完整receipt/hash/時間/投影一致，pending C原ID補回一次、新D正常，舊ACK實際回放拒絕；備份後已ACK且local刪payload的B明示dump＋local不能補，sourceDB僅留test oracle，不稱RPO0／WAL PITR。接收端在真私有DB鎖下收到200封同樣本有效重送，queue64／drop135／rate拒65，無假committed，恢復原／新各1列。

實際修FR-2107 sender FIFO：依[ADR-048](../adr/ADR-048-v2-live-backlog-fairness.md)最新／最舊成功送達1:1交替，3公平反例RED保留。1000舊＋3新以原1秒sender節奏，延遲1.044／2.091／2.098秒、舊亦進展，6確認＋997待傳完整。latest候選不等於每筆新資料固定SLA，重啟輪次不持久；wire2／schema3／ACK認證不變。工具backup-copy防symlink/FIFO/無界讀已加固；共享／COM／長測未動，Pi／4G／完整PITR與SLA仍另驗。

## 2026-11-13 最新：broker重啟／損壞庫／client憑證輪替撤權完成

使用者指定先做三項、故障修復且不跑長測。[證據](../../output/no-pi-lifecycle-20261113/README.md)：定點42通過／28.40秒／零跳過，含broker真正停／起、同edge PID持續TCP採3筆並各入庫1次；4種損壞檔拒開且hash不變、新路徑正常；同CN新憑證可用、CRL撤舊serial（error23）、活動old TLS斷開／重連拒、新cert原ID補傳。相鄰393通過／12既有專用case跳過／coverage91.02%，包含原三SIGKILL恢復。實際修ReliableOutbox：既有zero／空SQLite不可當新庫重建；只在精確READONLY_ROLLBACK用rw原生恢復journal，其餘損壞拒開、不reset。新測試控制器host檔案I/O防symlink已補；原RED／失敗run與sourcesfalse保留。

共享v1／COM／長測未操作；CRL＋重啟僅自有broker，非正式憑證系統或即時撤權SLA。若真queue損壞先保留／備份，不touch空檔或手改schema假恢復；恢復備份／新stream需核對身份與未知結尾。Pi／實體SD／4G／中央PITR仍未驗。

## 2026-11-13 最新：9個新無Pi恢復／憑證短測完成

[本輪證據](../../output/no-pi-resilience-20261113/README.md)：新9案（SIGKILL三個交易邊界、SQLite BUSY／READONLY、旋轉中的線上backup、v2 server錯CA／錯hostname／過期）全通過，加原35槽號共44案／11.09秒／零跳過；工具32案通過。三TLS故障後均保留原ID/hash，合法mTLS恢復中央各1列／pending0。崩潰真dirty-spill證據以child constructor結束後hash為基準，修掉初版將初始化提交算入的假PASS風險；完成marker改原子發布。run-01舊缺陷保留，最終以run-final為準。production未改／共享未切／COM未用／長測未重跑；Pi、實體掉電／SD／4G、中央PITR仍另驗。

## 2026-11-13 最新：容量滿改保留新資料、淘汰最舊

使用者核定「新資料比舊資料重要，應該要從最舊資料開始覆寫」。[ADR-045](../adr/ADR-045-newest-first-edge-retention.md)／[本輪證據](../../output/newest-first-retention-20261113/README.md)取代舊v2「滿queue／audit拒新」策略：schema3本地按capture_seq淘汰最舊queue／quarantine／audit，與新樣本同交易，失敗全回滾；wire仍2，淘汰不記committed，有界摘要及warning。336項短回歸通過／12專用case未重跑、coverage≥80%，含23容量案、兩個真MQTT容量情境與35槽號固定案例。離線12筆限3，中央只入最後3筆；舊sample DB commit後、真ACK前被淘汰，不傷replacement。新舊schema不可雙writer，升版先停舊程序備份，舊版拒schema3；v1轉換容量不足整體失敗不裁切發布。

未切共享v1／占COM／重跑長測，舊封存仍保留原容量拒新結果。Pi／ADTEK／實體SD／4G與完整對帳UI尚未驗收。此處優先於下方歷史「保留所有pending／滿停採」敘述；中央歷史／控制帳本不是本次淘汰範圍。

## 2026-11-13 最新：其他無Pi短測與固定防回歸

使用者要求繼續無Pi測試、不重跑長測，並確保剛才錯誤不再漏檢。[本輪證據](../../output/no-pi-v2-faults-20261113/README.md)：8個新真故障（DB真逾時／自有backend終止、雙投影拒收、雙live receiver、generation舊ACK、SQLiteFULL／audit cap、rogue mTLS）＋35個固定槽號案例，共43通過／9.63秒，另16防呆通過。控制器兩入口強制核對完整35案identity，漏跑／替代／湊重複／skip／假DB逾時都不能以exit0過關。來源只改測試控制器／測試／catalog，production與原封存不變；未碰COM、未部署共享v2或重跑長測。

## 2026-11-13 最新：槽號誤標已修，僅做邊界補測

使用者要求「把槽號誤標修正，針對那個邊界補測就好，不用重跑長測」。[修復紀錄](../../output/slot-boundary-fix-20261113/README.md)：bench_run按scheduler原定deadline標槽並保留signed delay，原scheduler值不改；66項定點／相鄰判定通過，原五筆只做時間回放，新槽號5107–5111連續、該筆delay=−15ms。真正跳槽／重複／終界仍會檢出。未改production／verifier／舊frozen或原帳本，未占COM／啟服務／重跑長測。原24h中斷與歷史嚴格FAIL維持。

## 2026-11-13 09:07：僅驗證異常單筆，不重跑

使用者明確要求「驗證那筆測試就好，不用重跑」。[單筆證據](../../output/slot-5109-verification-20261113/README.md)：11/12 21:55:38.631664那筆有完整read／commit／ACK，DB／API各1列；前後共5筆逐筆一致。原凍結槽號公式會將邊界前約15ms的讀取歸入前一槽，因此5108重記／5109缺記是工具標號異常，不是那筆漏採或重複入庫。只完成驗證，未改工具／原帳本，未重跑；24h中斷狀態不變，後續勿自行安排重跑。

## 2026-11-13 最新：原24h已因Windows更新重開機中斷

[本日稽核](../../output/soak-interruption-audit-20261113/README.md)：11/12 22:29:14 MoUsoCoreWorker、22:31:26 TrustedInstaller先後發起計畫重啟；最後採樣22:29:13，約7h39m共5,512筆，DB／API本日逐筆5,512／5,512相符、pending0／SQLite完整。**24h未完成／INTERRUPTED，原status的RUNNING已過時，原三PID均不在。** 原1h本日重查仍3,600／3,600通過。槽號帳本另有5108重記／5109缺記的15ms邊界異常，嚴格FAIL保留，不能把資料全到當長測PASS。

沒有啟動重跑、占COM或切共享v2；原狀態／來源／帳本保留，最終事故判定另存。昨日v2的259項與90.81%仍是已完成的獨立驗證，封存hash相符；不是本日重跑。後續連續24h必須另開run，先處理更新窗口及槽號邊界，不能接續湊時數。下方11/12 RUNNING敘述為歷史快照。

## 2026-11-12 最新：可靠送達子集已修復／未切共享

使用者要求「缺口修復」。[ADR-043](../adr/ADR-043-opt-in-committed-telemetry.md)／[實作及切換入口](../../services/edge-receiver/README.md)新增 opt-in v2 queue／session ACK／中央 receiver／migration019：**本地只在中央 DB committed ACK 後刪除，重送同 ID 只入庫一次**。原兩個 v1 反例以真 MQTT／DB／mTLS在新路徑驗證修復；259項通過、12項專用case跳過、combined coverage90.81%。真TCP採集程序SIGKILL後原ID補傳、並行重送／repair、DB寫入失敗回滾、mTLS禁止偽造ACK等均通過。[完整證據](../../output/committed-delivery-fix-20261112/README.md)。

**原24h與共享runtime保持v1，尚未切換部署，歷史FAIL不改寫。** 目標舊sender須先停止並備份，再只讀轉換仍pending至全新v2檔；不能碰活動COM3／COM4。v1已刪而中央未到的資料不能保證追回。Pi、ADTEK、完整多設備／manifest對帳、20/s／7天容量與PITR仍未驗收；本輪修復不能等同溫度全鏈路完成。舊章節以下為階段快照，可靠送達目前狀態以本節為準。

## 2026-11-12 17:20 實際接收端與 IP 丟包補測

[本輪證據](../../output/no-pi-ingest-20261112/README.md)：使用現行相同 image／Telegraf 設定的私有接收副本，確認 **同筆重送入 DB 兩列，以及接收服務停機時 broker 已確認／本地已刪、恢復後 DB 仍缺 1 筆**；兩案是 v1 可靠送達 FAIL，並未修復 receipt／去重。私有 DB 暫停 10 秒後 10／10 恢復；另一私有核心 netem 實際丟 17 個 IP 封包，200 筆積壓＋30 次 TCP 採樣共 230／230 完整。211 項回歸通過、12 個私有 TLS／時鐘案未重跑，production coverage 96.06%。

原 24h 已完成前 1,740 槽與 DB／API 逐筆相符，但仍 RUNNING。首次中途查詢因 UTC／單調時鐘邊界相差 2.781ms 多納入下一槽，FAIL 與診斷保留；用同一快照的實際下一槽時間另查通過，未改活動 verifier。舊靜態 770 檔、前輪 384 檔、活動／封存來源及 verifier hash 相符；共享 17 容器 ID 不變，自有測試容器及 netem 已清理。沒有改 production、COM 或部署。**Pi 已由使用者確認尚未到位**；後續先推進不依賴 Pi 的工作，硬體與 ADTEK 全鏈路不能標完成。

## 2026-11-12 16:51 無 Pi 補測完成

使用者要求直接執行其他無 Pi 測試，[本輪證據](../../output/no-pi-backlog-20261112/README.md)：私有積壓 10,000＋同步採樣 120 共 10,120 筆完整；弱網／抖動／限速／三次斷流 155 筆完整；線上備份 1,000 筆完整前綴通過；新 QA 設備 `delta-backlog-qa-20261112` 的 110 筆實際 EMS DB／API 逐筆相符，介面驗到歷史 stale 與新採樣 live。Linux 唯一臨時 user service 強殺後約 11.3 秒重啟、正常停止與時間延續通過，已停止自有服務／程序／容器。203 項回歸通過、12 個私有 TLS／時鐘案沿用前輪實跑；production coverage 96.06%。

本輪只新增測試工具及文件；新 QA 身分與 110 筆模擬量測保留供追溯。沒有修改 production、共享容器、COM 或原長測來源；24h 仍進行中。第 9 關中央 receipt／去重與 Pi／4G／ADTEK 全鏈路仍待實作／驗收，不再重跑人工 USB 秒數補驗。

## 2026-11-12 16:06 最新接手補充

使用者已確認 **Pi 尚未到位，先接續不需要 Pi 的測試**。本輪 [無 Pi 接手結果](../../output/no-pi-takeover-20261112-1600/README.md)：191 項回歸通過（96.06% coverage），12 項時鐘／TLS 另於私有環境全部通過；活動 24h 長測的已完成前 863 槽與 DB／API 逐筆一致；本機 Monitor 實際台架資料在 1440／390px 檢查通過，100 筆畫面紀錄可追溯至採樣帳本及 DB。原靜態證據 770 檔及活動來源／verifier hash 均相符，17 個共享容器 ID 維持。此次未修改 production 或活動長測來源。

5 秒／24 小時仍 RUNNING，預計 11/13 14:49:53 採樣結束後才做全窗對帳；863 槽只是中途完成區間，不是長測 PASS。中央 receipt／去重仍待實作、第 9 關 v1 FAIL 保持。新證據另存獨立目錄，舊逐關 README／latest-status／manifest 保持原快照；目前動態進度仍查原 soak status。以下 15:53 交接快照保留。

更新：2026-11-12 15:53（Asia/Taipei）。這是交接快照與待辦，不是新功能完成或部署證明。Owner：EMS 專案接手工程師／agent。

## 1. 使用者最新決定（先讀）

- 本輪先拿掉日照計，只測 **U701-A-10 溫度貼片＋CS1-TP1-8-A 溫度表**。
- 最終必須由 **Pi 採集、解析、暫存並傳送至 EMS**。不要再把「電腦直接採集到 EMS」當成本次交付。
- 目標：`U701-A-10 → CS1-TP1-8-A → RS485 雙絞線 → USB–RS485 → Pi（解析／SQLite）→ 有線網路或 4G → EMS 接收後台 → DB → EMS 溫度介面`。
- 真溫度表已是從站，此鏈路只需一顆 USB–RS485 插在 Pi；PC 是設定／檢視端。只有 PC 模擬 RTU 從站時才需要另一顆轉換器。
- 原 Pi 3B+ 已由使用者回報摔壞，替換 Pi 到位與否尚未確認；溫度貼片／表頭目前是型號已選定，不能宣稱已收貨或接線完成。硬體未到可準備程式與隔離模擬測試，不能替代 Pi 端到端驗收。
- 不再安排人工精確秒數的 USB 拔插補驗（使用者已取消）；不要要求重做已完成的台架項目。

## 2. 下一位 agent 從這裡開始

1. 先讀根 [AGENTS](../../AGENTS.md)、[規範](../../project_rules.md)、[PRD Guideline](../PRD-架構設計-Guideline.md)、[任務地圖](../README.md)。在權威 `/home/dalelin/synaiq/EMS` 查看 git 狀態，保留所有既有變更。
2. **先看活動長測，不占用 COM3／COM4。** 讀 [動態 status](../../output/delta-no-pi-validation-20261112/soak-sequence-01/status.json) 與 [長測說明](../../output/delta-no-pi-validation-20261112/soak-sequence-01/README.md)。確認更新時間和程序仍活著；RUNNING 字串本身不證明程序正常。
3. 讀下表的未完成項目；第一個可獨立推進的工作是取得 **CS1-TP1-8-A 原廠接線圖及 Modbus 暫存器表**，確認實際版次。不能用 Delta register map 或猜地址來讀 ADTEK。
4. 盤點替換 Pi、溫度表與貼片是否到位；只詢問尚缺資訊，不重新詢問已確定的 Pi 上傳目標。通訊／硬體未確認前不給猜測接線或市電施工指示。
5. 涉及新增設備 profile、payload／入庫／UI 時，依 PRD-first 補足本次溫度整合 PRD／ADR、三圖、風險及測試契約，再 TDD。現有 PRD-0020 只涵蓋 Delta，不能視為已核准 ADTEK 全鏈路。

## 3. 既有 Delta 台架進度（不能混成溫度／Pi 通過）

詳細權威證據：[逐關紀錄](../../output/delta-no-pi-validation-20261112/README.md)、[狀態快照](../../output/delta-no-pi-validation-20261112/latest-status.json)、[原計畫](delta-no-pi-validation-plan.md)。逐關紀錄保留歷程，最新節與原始 run 結果優先於早期敘述。

| 項目 | 已確認狀態／限制 |
|---|---|
| 台架 | Windows COM3 Delta 模擬從站 → 約 60 cm 雙絞線 → COM4 採集 → SQLite／MQTT／EMS；不是 Pi 或 ADTEK |
| 基準／頻率／情境 | 基準 120/120；1／5／10／15／30 秒及 day/night/alarm 共 170 筆逐筆核對通過 |
| 停止從站 | 3 次故障恢復通過；20 筆 DB/API 相符，24 個缺測槽已分類，不能將故障期算正常採集全通過 |
| USB | COM3 修正後 PASS；COM4 已觀察 2.516 秒恢復、55/55 對帳，但離線 27.235 秒未滿工具門檻，原 FAIL／時長偏差保留，補驗已取消 |
| 封包／遲到 | 原遲到回覆 20/20 誤收的 FAIL 保留；ADR-041 unknown 鎖定 20/20、有界隔離恢復 20/20 通過；lab 1 秒不是現場設備保證 |
| 上傳中斷 | 300.016 秒離線，60 個離線槽提交；80 筆 DB/API 逐筆相符、pending0 |
| 程序／容量 | 自有 child 強制終止 10 輪；小 queue、SQLITE_FULL、損壞副本檢查通過；非 Pi／SD／主機斷電 |
| 中央 DB 確認（第9關） | **v1 FAIL，3 個反例已重現**：DB 未 commit 本地已刪，重送／重複投遞會重複 commit。中央 committed receipt、去重、缺筆對帳仍待實作 |
| UI | 本機 Monitor 攔截 API 的 5/5 契約測試通過；不是實際溫度入庫／公開站／端到端補傳驗收 |
| 1 秒／1 小時 | **PASS**：完整 3,600 秒，3,600/3,600，DB/API 各 3,600 逐筆相符、pending0 |
| 5 秒／24 小時 | **已中斷／未通過**：11/12 14:49:53–22:29:13約7h39m、5,512筆DB/API相符；Windows更新重開機終止，未達17,280與24h，原RUNNING過時。槽號另有邊界異常，見11/13稽核 |
| 時鐘／TLS | 私有環境 12/12 通過（時鐘2案11階段、TLS10案）；不代表正式 ACL 身分綁定、RTC／NTP精度或中央 DB ACK |
| 回歸 | 最近留存結果 191 passed／12 skipped、production coverage 96.06%；12 個隔離整合案另實跑通過。非本次文件工作重新測得 |

## 4. 活動長測保護與接續

15:53:31 唯讀確認 Windows PID 4564（controller）、18924（bench）、5524（simulator）仍存在。15:53:28 最新事件到 slot763，依序 read_ok／committed／broker_ack。這只證明當時持續進行，沒有提前算 24h PASS。

- 動態狀態：`output/delta-no-pi-validation-20261112/soak-sequence-01/status.json`，約每30秒更新。
- Windows 工作目錄：`C:/Users/User/AppData/Local/Temp/ems-no-pi-20261112/soak-sequence-01`。SQLite 在 Windows 本機，不在 WSL 分享路徑寫入。
- COM3 序號 BG04PB77A（從站）、COM4 BG04PB7RA（採集），19200／8N1／unit1。這些是本次 Delta 台架值，**不可套作 ADTEK 設定**；重插後亦須重新確認 COM。
- 不拔 USB、不啟動第二個串口讀寫者、不重啟共享 EMS、不變更活動凍結來源／verifier。不需要為建立交接重跑測試。
- 若接手時已結束：查該階段 `soak-result.json`、`summary.json`、`db-comparison.json`、controller 狀態及退出碼；依既定接受條件核對時長、分母、逐筆數值、缺口、重複與 pending，再更新主紀錄及 latest-status。只有數量相等不夠。
- 若 status 停更：先唯讀查程序／日誌，不因時間已過就標通過或重新啟動。PID 會重用，需交叉核對啟動時間／命令列。
- 如使用者確實要求停止，依長測說明使用該 run 的 STOP.txt，由 controller 收回自己的程序，保留 STOPPED／FAILED；不得停共享容器或清除原始證據。本次未停止長測。
- 活動整個 soak-sequence-01 排除於靜態 artifact manifest；不要往舊證據目錄任意加檔或重算 hash 來掩蓋來源變更。

## 5. 溫度 → Pi → EMS 未完成清單（依順序）

| 順序／交付 | 目前缺口 | 完成證據 |
|---|---|---|
| T0 硬體與通訊資料 | 替換 Pi／貼片／表頭是否到位；CS1 手冊版次、端子與供電、Pt100 線制、站號、baud／parity／stop bits；讀取功能碼、地址基準、長度、型別、有號／小數倍率、斷線／超量程碼、回覆時限均待確認 | 原廠文件／型號照片及設定紀錄；保存文件來源與 hash，不猜暫存器 |
| T1 溫度整合規格 | 未建立本次核准的 ADTEK profile／端到端契約 | 按 Guideline 的 PRD／ADR；明確 signal、°C、量測時間、品質、採樣預設、身分及 receiver 路由；更新入口與風險 |
| T2 解析與模擬 | **沒有 U701／CS1 專用解析器或 RTU simulator**；Delta 的 read_temperature 是逆變器內部溫度，不是貼片 driver | 依原廠 golden vectors：正常、負溫、小數、缺值、錯CRC／短包／錯站、例外碼、逾時／遲到；先 RED 後 GREEN |
| T3 Pi 採集服務 | 未在可用 Pi 安裝／啟用溫度採集器 | Pi 型號／OS／時間同步、serial by-id／dialout、唯一主站、systemd、獨立 SQLite、啟動／恢復 log；Pi讀值與表頭一致 |
| T4 EMS 接收／入庫／查詢／UI | 未打通 ADTEK 溫度身分與端到端鏈路；既有電表四欄上傳不能塞溫度假值 | 實際 temperature／°C、原始時間、來源與品質在 DB／API／圖表一致；既有 sensor 模擬資料不算真貼片資料 |
| T5 有線網路完整流程 | 溫度表 → Pi → EMS 尚未實跑 | 表頭／Pi原始回覆與解析／SQLite／接收端／DB／API／UI可逐筆追溯；隔離測試身分，不覆蓋既有 sensor-001 |
| T6 斷線／斷網與可靠送達 | Pi端未測；v2 committed receipt／去重子集已私有驗證，未切共享；完整manifest對帳未實作，v1缺口仍存在 | 不補0／不沿用舊值冒充新採樣；Pi原身分補傳、DB commit後確認與重送冪等仍須現場驗，完整缺筆對帳另驗 |
| T7 4G／現場 | SIM7600G-H 網路、APN／SIM、供電與天線、TLS入口／ACL及溫度設備實體線路未驗收 | **Pi實際經4G**連EMS、斷網恢復與長測證據；不能以PC TLS私有測試代替 |

開始先用有線網路減少變因，之後切4G；兩階段傳送者都必須是Pi。1／5／10／15／30秒是使用者要求的可選採樣間隔；感測器反應、表頭更新與採集間隔分別記錄，1秒輪詢不代表1秒物理反應或每次都有新量測。

## 6. 程式與規格入口（可參考，不等於可直接套用）

| 範圍 | 入口／注意事項 |
|---|---|
| Delta既有採集 | [edge.py](../../services/delta/delta_device/edge.py)、[poller.py](../../services/delta/delta_device/poller.py)、[protocol.py](../../services/delta/delta_device/protocol.py)；目前綁定Delta FC04/map，不能換device_id當ADTEK |
| SQLite／上傳 | [delivery.py](../../services/delta/delta_device/delivery.py)、[publisher.py](../../services/delta/delta_device/publisher.py)；encode_line僅voltage/current/power_kw/energy_kwh，PUBACK即刪本地列，並無中央receipt |
| Pi部署參考 | [systemd範本](../../services/delta/deploy/delta-edge.service)、[操作說明](delta-edge.md)、[field範本](../../services/delta/config/field-rtu.example.json)；Delta field時限null拒啟動，不可抄lab值解鎖 |
| 既有溫度接收參考 | [kc-ingest](../../services/kc-ingest/telegraf.conf)、[BFF量測路由](../../services/bff/bff/routes/device_measurements.py)、[frontend來源](../../frontend/src/)；有sensor demo不表示ADTEK身分／payload已接好。確認既有factory溫度路徑能否合法沿用後才決策，不必預設一定新增DB表 |
| 設計／待辦 | [PRD-0020](../prd/PRD-0020-delta-edge-telemetry.md)、[PRD-0021](../prd/PRD-0021-multi-device-edge-reliability.md)、[PRD-0006](../prd/PRD-0006-Generic-Measurement-Pipeline-Dynamic-Visualization.md)、[ADR-030](../adr/ADR-030-edge-durable-receipts.md)、[ADR-041](../adr/ADR-041-rtu-uncertainty-and-bounded-recovery.md)；Draft不是已部署 |

多設備 bus owner／scheduler、7天容量與補送負載、正式gateway/device ACL身分綁定、Pi／SD斷電、RTC／NTP精度、Delta M70A-262／RPI-M30A實機profile與回覆時限、長線EMI仍待驗。這些列為後續，不因本輪先測單溫度而標完成。

## 7. 硬體來源與確定／未確定邊界

- [U701-A-10商品](https://energyshop.starshining.com.tw/product/detail/2288545)：[原廠選型表](https://www.adtek.com.tw/uploads/root/A.Manual_TC-2023/D-SensorTransmitter/D-OrderInformation/DX-XX-U-701-order-250505.png)已核對A＝Pt100、10＝10m；實物線制／端子仍需對照手冊。
- [CS1-TP1-8-A商品](https://energyshop.starshining.com.tw/product/detail/2288339)：Pt100溫度讀取並輸出RS485 Modbus RTU。需要其完整原廠手冊，不以商城系列敘述推論每個訂購碼均通用輸入。原廠[CS1-T規格書](https://www.adtek.com.tw/uploads/root/A.Manual_TC-2023/A1/A1-TC-DataSheet/A12-07-CS1-T-DataSheet-TC-V13-260121.pdf)為查找入口，**本輪未成功下載留存或取得register map**。
- 日照計LP-PYRA03-AC及其4–20mA轉換器已依使用者最新指示移出本輪，不繼續採購建議／實作。
- 原Pi曾成功SSH：emsadmin@ems-edge-001.local、192.168.0.164、Pi3B+ Rev1.4、Debian13、64GB卡、throttled=0；均是**摔壞前歷史資料**，替換機不能假設沿用IP／SSH host key／設定。不要儲存密碼於交接檔。
- 4G只提供IP網路；不能把公開EMS網頁URL當成已可使用的MQTT/TLS接收入口。實際EMS接收端位置、路由與憑證需現場部署時確認。

## 8. 版本與本次交接改動

核對權威checkout：branch `feat/prd-0024-booth-qr-binding`，HEAD `79427c6`。目前大量程式／測試／文件修改及未追蹤證據尚未提交；HEAD不能代表這些測試所用來源，請依各run凍結來源與hash追溯。Windows備份目錄不作開發。

本次只新增交接與導航連結，未改程式／設定／API契約／DB／容器、未部署、未停止長測、未commit/push。後續agent先核對本檔時間、活動status及git狀態，再接T0／T1；不能將此交接當成溫度功能已實作。
