# 無 Pi 逐關驗證紀錄（進行中）

2026-11-12，Asia/Taipei。對應 [驗證計畫](../../doc/operations/delta-no-pi-validation-plan.md)、PRD-0020 FR-2003/2005、ADR-031。這是 Windows 雙 USB-RS485 實體台架，不是 Pi、4G 或 Delta 真機驗收。

## 設備與隔離範圍

- COM3：FTDI BG04PB77A，從站；COM4：FTDI BG04PB7RA，採集器。當次兩埠均可獨占開啟。
- FTDI 驅動2.12.36.20（2024-10-28）；19200/8N1/unit1/base1、timeout3秒。
- Python3.12.14、pymodbus3.6.9、pyserial3.5、paho-mqtt2.1.0。
- 正式edge.run／Poller／Outbox／Publisher；測試子類只增加旁路帳本、有界終止及指定故障。
- 獨立demo設備delta-rtu-sim-001，每run自己的SQLite與MQTT client_id；共用EMS容器維持運作。
- 使用者當次回覆：雙絞線約60公分（估計，非量尺實測）；未取得新接線照片、CPU/RAM未連續量測。run啟動時manifest的not_measured保留不覆寫，由此補充來源。

## 結果

| 關卡／run | 狀態 | 證據與限制 |
|---|---|---|
| 0 盤點 | PASS（電腦端） | 序號、COM與獨占開啟確認；沿用既有接線 |
| smoke-01 | FAIL／另行補送核對通過 | 1秒3槽提交3筆，停止時pending1；重開原SQLite補送後DB/API3/3。不覆寫原失敗結果，不是同一sender自動恢復 |
| smoke-02 | PASS | 5秒3槽、pending0、DB/API3/3，poll p99約0.328秒 |
| 1 baseline-01 | PASS | 120/120、DB/API120/120、獨立golden120/120、pending0；poll p99=0.344秒，max=0.359秒 |
| 2 頻率／情境 | PASS | 1/5/10/15/30秒各30筆；night/alarm各10筆。共170筆全部逐筆通過golden、DB/API核對，pending0；與關卡1合計290筆 |
| 3 停止從站 | PASS（故障恢復） | 停30秒×3次，每次重啟後10.281秒取得新查詢有效值，符合15秒門檻；44槽取得20筆，DB/API20/20、pending0；24個缺測槽完整分類，非正常採集率通過 |
| 4 USB拔插 | COM3 PASS；COM4功能確認／時長偏差保留，補驗取消 | COM3恢復上界9.672秒、52/52對帳；COM4-01誤拔另一端，COM4-02單端正確且2.516秒恢復、55/55對帳，但離線27.235秒未達預設28秒下限，原FAIL保留，使用者取消秒數補驗，依現有證據結束USB項目 |
| 5 封包異常 | 原FAIL保留；ADR-041有界契約通過 | frames-01遲到20/20誤收保留；修正後完整sample實體unknown鎖定20/20、有界隔離恢復20/20。真機上界未核定，不宣稱無界遲到可辨識 |
| 6 上傳中斷 | PASS | 300.016秒離線、60槽全提交；同一sender重連，80筆DB/API逐筆相符、pending0，恢復後96.312秒內完成DB核對（觀察上界） |
| 7 程序崩潰 | PASS | 正式10輪：30筆已提交完整冷開恢復／DB/API逐筆一致，10筆未提交未混入、pending0；僅強制終止自有child，非主機斷電 |
| 8 容量 | PASS（隔離故障注入） | 小queue拒新保舊、真SQLITE_FULL保舊且解除後可新增、損壞私有副本拒啟動且bytes不覆寫；不代表OS磁碟耗盡或Pi斷電 |
| 9 DB committed ACK | FAIL（v1反例3/3）；v2待實作 | [隔離實證](ack-isolated-01/README.md)：未commit本地已刪、重送或重複投遞均commit2 |
| 10 UI與1h／24h | UI契約5/5 PASS；1h PASS、24h RUNNING | [UI](ui-freshness-02/README.md)；[活動長測狀態](soak-sequence-01/status.json)；未先報長測通過 |

## 帳本與判定

bench_run.py固定monotonic測量窗，記錄attempt/read/SQLite commit；背景寫events.jsonl。bench_ledger.py識別漏槽、錯誤、重複及額外槽，並用獨立literal bounds核對noise=0的電壓／電流／功率／電量／state／頻率／溫度。範圍檢查不能取代Delta真機register與golden vectors驗收。

bench_verify.py只驗已完成run，查整個採樣與settle窗口，逐筆核對DB/API的原始時間與四欄位。整體通過必須同時summary.json.pass及db-comparison.json.passed；數量相同不足以通過。

baseline-01啟動時沒有5秒sender寬限及inline golden；保留原紀錄，結束後另做golden補核。後續run測量窗後原sender保留5秒、停止新增採樣，再等DB最多30秒；manifest記錄sender_settle_seconds。這不改採樣分母，也不代表production關機策略已修改。

資料先寫Windows本機Temp，結束才複製此目錄，避免SQLite走WSL共享路徑。後續run保存工具與production來源快照；baseline只有production hash，不追稱已有工具快照。

## 重現（Windows PowerShell）

```powershell
python services/delta/tools/bench_run.py --config output/delta-rtu-bench-20261112/windows-bench.json --output C:/Temp/ems-bench/new-run --count 120 --interval 5
python services/delta/tools/bench_verify.py C:/Temp/ems-bench/new-run
```

輸出目錄必須全新。interval選1/5/10/15/30；count正整數且總窗不超過24h；scenario選day/night/alarm；可重複outage如20:30（第20秒停sim30秒），不得重疊且需保留恢復後採樣。工具限loopback MQTT、RTU及指定demo身分。不要在其他程序占用COM時執行。

## 回歸與審查

完整Delta回歸109 passed，production delta_device line coverage95.20%（不是工具覆蓋率）。帳本／封包／網路／USB新增邊界反例先RED再GREEN；完整輸出見unit-regression.txt。

獨立審查修正了重複commit漏判、同步fsync干擾、子程序清理、重啟未讀值假PASS、電量倍率及對帳窗口問題；code/python審查最終Approve。不新增API／容器／schema／production採集設定或中央ACK契約。

## 尚待實體核對的風險

[遲到回覆重現](memory-late-reply-reproduction/README.md) 使用pymodbus3.6.9與記憶體串口，第一請求逾時後，舊2300可被第二請求接受；工具正確判FAIL。這是替身證據，未當成實體RS485結果。獨立保留script、stdout、來源與SHA256。USB／停止從站驗收另列spanning_reads；跨恢復查詢不充當恢復證據，仍需恢復後新查詢成功。

後續工具bench_usb、bench_frames及bench_network已準備並經獨立審查；只有實際執行且對帳後才能更新相應關卡，不因工具存在而標PASS。

## 關卡3的缺測與恢復

simulator-outage-01以5秒44個排程槽，於第20/80/140秒停止本工具的模擬器30秒，採集程序不中止。32次attempt，其中20次有效並提交，12次讀取失敗；另12個槽因前次等待超時而未發起，總計24個缺測槽。summary.failed_slots是未成功取得數據的槽集合，包含missing_slots，兩者不可相加重複計數。

三次恢復均以重啟後才開始的新查詢判定，10.281秒取得有效樣本；沒有恢復前完成的假值，也沒有用跨越恢復時間的查詢充當成功。讀取失敗期間timeout設定3秒但觀察交易約6.125秒，會跳過5秒槽。此值是目前Windows/pymodbus/串口組合實測，原因尚未進一步拆解；不能將設定值當作整筆讀取的硬上限。

截至10:29（Asia/Taipei），關卡1–3有效樣本合計310筆逐筆DB/API核對通過；故障期間缺測並未被補成0或沿用舊值。關卡4之後尚未完成，60公分台架結果不能代表現場長線、Pi或4G。記憶體串口的遲到回覆風險與中央DB確認缺口仍未解除。

## 關卡4：COM3已插回但未自動恢復

usb-com3-01：離線35.844秒，插回距採樣窗結束僅約5.36秒，沒有重插後的新查詢。原始工具FAIL保留，人工判讀INCONCLUSIVE，見該run的assessment.md。

usb-com3-02：2026-11-12 11:27:25.818離線、11:27:57.627重現（Asia/Taipei），間隔31.813秒，序號與COM3一致，COM4未拔除。重插後仍持續ReadError，直到11:31:56.552採樣結束沒有有效值，故15秒自動恢復門檻FAIL。60槽僅前6槽有效，6筆均DB/API逐筆相符、pending0，剩餘54槽未採得，不能以對帳成功掩蓋採集缺口。

使用者不再改動接線，另跑post-usb-restart-01重新啟動模擬器與採集器，3槽全部有效、DB/API3/3、pending0。此結果證明當下連線經程序重啟可恢復；未分別保留單端程序做控制實驗，因此不能斷言問題只在模擬器或只在採集器。COM3為模擬器端，不能將此結果直接當成現場採集器USB拔插結論，COM4仍須獨立測試。當前測試程序已結束。

使用者要求再測後執行usb-com3-03，未修改程式：11:59:19.151離線，11:59:52.940重現COM3（Asia/Taipei），離線33.781秒；到12:02:59.066採樣窗結束，重插後約186.13秒仍無有效樣本，自動恢復再次FAIL。60槽中16槽有效並提交、44槽缺測，已提交16筆DB/API逐筆相符、pending0。過程未重啟任一端，12:03:04正常完成工具清理。這不是使用者未插回，也不能把16筆對帳成功當成60槽採集成功；下一步需針對串口斷線後的重新開啟與模擬器監聽狀態做單端隔離診斷。

## ADR-040修正及回歸（物理恢復待重驗）

實際pymodbus3.6.9搭配Windows polling／記憶體串口，已先RED重現in_waiting的SerialException使poll task結束而handle不關／不重開；新測試原版1 failed。第一版修正後再用loop exception_handler補抓write-close race，17 passed／1 failed，精確為未回收的AttributeError(NoneType.in_waiting)。最終保存poll task引用並cancel＋gather，18項串口恢復測試通過：同埠連續2次移除／重插、in_waiting／read／write錯誤、取消清理、未知RuntimeError不重試、idle不重開及設定邊界。這些均為記憶體替身，沒有操作實體USB；碼審與Python複核Approve。

完整Delta回歸127 passed，production line coverage95.71%，輸出serial-recovery-unit-regression.txt。修正後實體正常通訊recovery-fix-smoke-01採3槽，3筆golden及DB/API逐筆相符，pending0。該run沒有拔USB，因此不能關閉關卡4。重開僅模擬器端、保留同一context；第一次啟動失敗仍退出，未知錯誤向外傳。設定與限制見ADR-040；未改採集器、依賴版本、API或中央ACK。

### 12:16 修正後COM3實體拔插：PASS

usb-com3-04-fixed於12:15:33.081觀察COM3缺席，12:16:06.404原序號於同埠重現（Asia/Taipei）；離線33.328秒。原模擬器程序在12:16:07.273重新記錄simulator_ready，未重啟其程序或採集程序；12:16:15.558由重插後新查詢取得有效樣本，保守恢復上界9.672秒（使用最後一次缺席枚舉開始時間計算），符合15秒門檻。

60個排程槽中52筆有效並提交，4次查詢失敗及4槽跳過合計8個缺測槽均屬故障／恢復窗口，無未分類缺口、假值、golden錯誤或重複；52筆均逐筆DB/API相符，pending0。正常採樣summary.pass=false因刻意故障造成缺測保留，專項usb-result.json.passed=true才是本次USB判定。這只通過COM3模擬器端一次恢復測試，不等於COM4採集器端或整個關卡4完成。

### 12:22 COM4回復觀察成立、單端隔離條件不成立

usb-com4-01原始usb-result.json.passed=false／automatic_recovery=false，原因為wrong_usb_events=1，不能覆寫為PASS。12:18:38.435記錄usb_other_missing COM3；simulator.log同時記錄串口失效及多次FileNotFoundError，直到12:18:48.643重新ready。這不是單一枚舉空值的孤立證據。COM4於12:18:48.659缺席、12:19:20.496同埠重現，離線31.844秒；新查詢12:19:23.034成功，恢復上界3.047秒。模擬器與採集器程序均未被工具重啟。

60槽中52筆有效並提交、7次讀取失敗、1槽跳過，共8個缺測槽；52筆DB/API逐筆一致、pending0，沒有假值／golden錯誤／重複／未分類槽。可以陳述實際恢復觀察，不能宣稱COM4單端隔離驗收通過；人工判讀INCONCLUSIVE，等待操作情況釐清及重測。工具已正常收尾，接線保持，尚未進入第5關。

早期smoke-01的終止工具曾用RuntimeError留下sample_rejected日誌；後改專用BenchWindowComplete終止訊號。該工具終止事件不歸為實體封包錯誤，原日誌與pending1結果均保留。後續run的5秒sender寬限是驗證窗口收尾，未修改production停止時保留SQLite待送資料的行為。

使用者補充：上一輪不小心拔到COM3。這與usb_other_missing及simulator.log一致；原始FAIL保留，COM4單端隔離驗收仍需另開run重測，不能回改舊結果。

### 12:30 COM4單端恢復已觀察、離線時長略短

usb-com4-02沒有拔錯另一端（wrong_usb_events=0），COM4 12:25:58.725缺席、12:26:25.953同埠重現，離線27.235秒；12:26:27.947新查詢取得有效資料，恢復上界2.516秒。60槽全部發起、55槽有效並提交、5次故障窗口內讀取失敗，無跳槽／重複／假值／golden錯誤／未分類缺口，55筆DB/API逐筆一致、pending0。

因預先設定的離線時長接受範圍是28..60秒，原usb-result.json.passed=false／automatic_recovery=false維持，不放寬範圍回改PASS。這是測試操作時長未滿足，並非再次出現無法恢復的軟體問題；COM4單端正式判讀INCONCLUSIVE。後續改由事件紀錄計時，使用者拔下後先保持缺席，達時後才提示插回。

### 使用者取消秒數補驗

使用者明確表示不用重驗、人工無法精確判讀秒數，usb-com4-03-timed已停止自己的採集／模擬器程序並保存不完整證據與cancellation.json，不算完整測試。USB項目以既有證據結束：COM3正式PASS；COM4已觀察2.516秒內同埠自動恢復、55/55 DB/API一致，但27.235秒離線的工具原FAIL與操作時長偏差保留。依使用者指示不再要求精確秒數拔插，並繼續其他可由程式控制的驗證；不回改成無條件正式PASS。

## 第5關完成：下一個未解問題

[frames-01](frames-01/README.md)完成實體RS485六種故障各20次。分段、截斷、錯誤CRC、錯站號、無回應各20/20通過；遲到回覆20/20誤收舊2300，第二次應為2400，時序均獨立核對。此為production Poller.read路徑，不是完整sample或故障值入庫證據，未連MQTT。原工具FAIL保留，R20-BENCH-01從替身風險升為實體台架重現，真機未驗。第6–10關仍未完成；下一步先核定設備profile時限與交易復原策略，不盲目加timeout或retry讓結果變綠。測試程序均已結束，無需人工拔插。

## ADR-041完成實作及40次實體完整sample驗證

[修正證據](rtu-recovery-policy/README.md)：先以完整sample替身重現舊AC跨close/open污染，再實作不確定交易鎖定；unknown上界停採且既有可信outbox補送，有核定上界才隔離／重建client與framer／清buffer。field RTU也須上界／來源與啟動隔離，範本null拒絕啟動；受信source文字不是自動證明上界正確。

完整Poller.sample實體recovery-01：unknown20/20在舊31bytes已入buffer且重開handle後仍不發新請求；受控lab 1秒上界20/20丟棄舊AC並取得新240V／9.36kW，各案請求數與guard時序均核對。此測試不連MQTT。163項隔離回歸通過、production line coverage96.06%。第5關新增保護在已核定上界契約內通過；原frames-01無界FAIL保留，M70A-262／RPI-M30A時限未核定，R20-BENCH-01仍Open，不宣稱任意延遲均能辨識。

第6關已啟動：只切測試sender上傳5分鐘、採樣5秒，保持RS485與共用broker；正式結果完成後另記。第7／8關工具已建立並進行獨立審查，不因工具或單元測試存在即標實體／端到端PASS。

## 本輪完成：第5關有界保護、第6–8關通過

- 第5關：完整sample實體40案，未知時限20案保持鎖定、受控lab時限20案隔離恢復；原無界遲到FAIL保留，兩款Delta真機時限待核定。
- [第6關](network-01/README.md)：上傳中斷300.016秒、60個離線槽全提交；同一sender於恢復後1.187秒重連，80筆DB/API逐筆一致、pending0。DB完整核對在恢復後96.312秒觀察到，屬上界。
- [第7關](crash-01/README.md)：真實採集child強制終止10次，30筆已提交逐次冷開完整保留、10筆未提交均未混入，最後新程序補送DB/API30/30、pending0；不是主機斷電。
- [第8關](capacity-01/README.md)：小queue／SQLITE_FULL保舊拒新，解除後可新增；損壞私有副本拒啟動且未被覆寫。不代表OS磁碟耗盡或SD斷電。

最終回歸[164 passed／96.06% production line coverage](unit-regression-adr041-final.txt)，code／Python獨立審查問題已修復並Approve。OpenAPI解析、文件新連結與本輪diff格式通過；全樹diff另有原本未提交Guideline兩行trailing whitespace，未改該無關檔案。測試自有程序已全數結束，共用17個EMS容器仍運行；沒有部署本次原始碼修正或新增中央ACK。

## 第9關設計缺口與後續未驗收

現行delivery.drain在publisher返回broker PUBACK後即Outbox.ack刪列，沒有等待中央DB receipt；所以「broker已ACK但DB尚未commit」不能保證本地仍保留，「DB已commit但回覆遺失」也沒有已實作的receipt／去重／對帳契約。這是PRD-0021待實作，不能用本次測試的DB/API事後核對冒充運行時保證。本輪不停止共享DB或以實際資料試刪驗證此缺口。

第9關保持BLOCKED，第10關1秒1小時／5秒24小時與UI回補新鮮度保持NOT RUN，不能報整套驗收完成。下一個實作項是中央committed ACK、持久樣本身分／去重／對帳，再回來做第9關受控故障驗證；另有Pi、4G及M70A-262／RPI-M30A實機profile驗收。現場最大回覆存活時間未核定前，field RTU範本仍拒絕啟動。

## 最新續驗：第9關反例、第10關UI與正式長測

此節取代前段截至各次執行的BLOCKED／NOT RUN快照，原始失敗與歷程保留。

- [第9關](ack-isolated-01/README.md)：真私有broker、production傳送端、受控SQLite接收器，3案重現；系統驗收FAIL。未commit本地pending0，重送／重複投遞均commit2。不是正式Telegraf／Timescale故障或v2 ACK測試；v2仍待實作。
- [UI freshness-02](ui-freshness-02/README.md)：實際本機Monitor加攔截API，5案通過，核對ECharts主series、卡片、表格。不是端到端補送／公開站驗收。初版-01缺少圖表值與失敗收尾檢查，保留而不用作最終依據。
- [正式長測](soak-sequence-01/README.md)：13:49:42啟動1秒／1小時；通過DB/API後才進5秒／24小時。仍執行中，以每30秒更新status為準。保持PC開機及USB，不需人工拔插。

完整隔離回歸[183 passed／production coverage96.06%](unit-regression-continuation.txt)，code／Python審查Approve；UI補強另經code review Approve。前置兩段smoke各3筆DB/API通過，formal=false；[原生Job探針](job-probe-01/result.json)驗證父程序退出後的孫程序可隨Job關閉回收。來源凍結見continuation-source。

未新增production修改、API／schema或v2 receipt，未部署共享服務。之前「測試程序已全數結束」是上一輪快照，現在長測自有程序仍運行。artifact-sha256.json排除整個活動soak-sequence-01與自身及manifest說明，範圍見artifact-manifest-scope.json；活動凍結來源另有source-sha256。

## 14:49更新：1秒／1小時正式PASS，5秒／24小時啟動

完整測量3600秒，3600槽均發起／有效／SQLite提交；golden錯值0、缺口0、重複0、pending0。DB與API各3600/3600逐筆一致，沒有多筆／缺筆／重複／值不符，raw strict亦PASS。poll p99=0.344秒、max=0.375秒。詳[正式結果](soak-sequence-01/one-second-one-hour/soak-result.json)及[對帳](soak-sequence-01/one-second-one-hour/db-comparison.json)。

第二階段已自動開始，5秒／24小時共17280槽；預計2026-11-13 14:49:53（Asia/Taipei）採樣結束，之後還需收尾與DB/API核對。這是預計時間，尚未通過；保持PC開機、不睡眠、USB與共享EMS不中斷。第9關v1遺失／重複FAIL仍未解除，Pi／4G／真機仍未驗。

## 15:20補驗：時鐘完整流程與真TLS 12/12 PASS

[證據及界線](field-security-02/README.md)：正式edge／真Modbus TCP／SQLite／TLS，注入UTC與步進。時鐘2案11階段（5個有效樣本、6個拒收），失同步仍補舊pending，重啟後拒收早於SQLite最後時間的值。TLS10案：正確帳密及mTLS成功，7個拒絕案例全保留pending，同一Publisher於1.0274秒重連並保留原payload。12份已完成私有SQLite另以mode=ro逐份核對。

首輪field-security-01保留9 passed／3 failed；修正測試收尾方法與錯誤碼，未改production。清理路徑先RED後GREEN8/8，code／Python審查Approve。完整回歸[191 passed／12 skipped／coverage96.06%](unit-regression-field-checks.txt)，12個skip的隔離案已在field-security-02另實跑通過。

私有broker與worker已移除，共享17個EMS容器與COM3／COM4長測維持；1秒／1小時已PASS，5秒／24小時仍運行。TLS只驗私有broker的憑證／認證及PUBACK，不是正式ACL身分綁定或中央DB確認；時鐘不驗RTC／NTP精度與同步旗標真假。第9關v1 FAIL、多設備scheduler、日照／貼片profile仍待實作，Pi／4G／真機未驗。
