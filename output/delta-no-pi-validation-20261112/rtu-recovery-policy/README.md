# RTU不確定交易修正與驗證

2026-11-12；ADR-041／PRD-0020 FR-2003。只代表Windows本機來源與雙USB台架，不是Delta真機或Pi驗收，未部署共用EMS容器。

## 反例與修正

red.txt保存原版完整sample的失敗反例：第一輪AC逾時後，close/open仍可讓舊AC被新sample接受。red-contract.txt另保存新增契約在修正前的17項失敗。Poller遇本機I/O、不完整／不可確認回覆後丟棄整筆，鎖定跨sample/read/close/connect。合法FC04 ExceptionResponse（含exception2 fallback）不作遺失交易處理。

未知回覆存活上界：停止新請求，既有可信SQLite仍由原sender送出。已核定上界：從_poison實際時點等待完整時限，重建client/framer、開埠清buffer後才開始全新sample；恢復失敗保留鎖定。field RTU必填上界及來源且啟動隔離；--once也等待。field範本null刻意拒絕啟動。

response_lifetime_source僅保留受信operator提供的核定依據，不自動驗證真實性。上界須含設備、USB與驅動的最後byte抵達時間；timeout不是這個上界。超出核定上界的任意舊回覆／惡意重播無法由RTU FC04格式保證辨識。M70A-262／RPI-M30A真機profile尚未核定。

## 實體結果

recovery-01為完整正式Poller.sample；COM3原始slave／COM4主站，19200/8N1/unit1/base1、timeout3。未知時限20/20鎖定、重開舊handle也不送新請求；受控lab 1秒上界20/20隔離恢復。

每案第一輪scale成功、AC無回應；失敗後重開已鎖定舊handle，向接收buffer送入真實31 bytes舊AC（230V/9kW），確認in_waiting=31。未知上界後續sample保持拒絕、請求總數2；有界profile在正式guard_deadline前沒有新請求，之後完整scale/AC/energy三塊取得240V/9.36kW，總請求數5。每案worker errors為空。僅原始串口測試，沒有MQTT或故障值入庫。

兩組各20案全通過；第一輪實測失敗耗時6.140–6.188秒，仍不能將timeout3當硬性3秒上限。此lab1秒只限制受控fixture的遲到發送，不是Delta設備保證。

recovery-smoke-01保留最早2案與其原工具來源；後由獨立審查發現工具曾用清理完成時間而非_poison作guard起點（可能假FAIL），已改用正式起點並增加慢close反例，再跑正式40案。原smoke不回改。

## 軟體回歸

unit-regression.txt：163 passed，delta_device line coverage96.06%，隔離network-none Linux容器。包括完整sample跨次舊AC、unknown重連鎖定、field重啟隔離、恢復開埠／flush失敗、合法exception、未知狀態下正式edge＋真SQLite繼續補送、CLI --once等待、慢close時點及工具判定反例。這不是工具全覆蓋率或實體Pi證據。審查已修正舊field設定測試、測試用未來時戳導致hang及工具計時問題。

source/與source-sha256.json保留正式40案使用來源。lab-bench.json為後續隔離補送測試專用，不能帶到現場。歷史frames-01的20/20誤收FAIL保留，沒有把無界情境改名為無條件PASS。

## 現場profile核定前的准入資料

每款M70A-262／RPI-M30A分別保留：機型與韌體、unit與baud/8N1、實際register範圍／base／倍率／能量word order、獨立儀表或設備面板對值、正常與故障情境、USB轉換器／驅動版本及線路條件。最大回覆時限須有可追溯依據，涵蓋請求到最後byte抵達主站的完整路徑；只量到p99或手冊timeout建議，不是硬上界證明。

未核定上界時不啟動field RTU，不把Windows受控fixture1秒複製到現場。現場若觀察到違反上界，該profile驗收失效，停止以既有結果宣稱新鮮度保證。1秒採樣是否可行另由實測整輪耗時與多設備排程預算決定；60cm單設備測試不能直接外推長線或多台。

中央DB ACK／去重／跨重啟對帳仍是PRD-0021缺口；本次DB/API逐筆核對屬測試觀察，不是已上線的可靠送達協定。
