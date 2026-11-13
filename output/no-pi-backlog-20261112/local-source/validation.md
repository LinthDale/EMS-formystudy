# Delta 本機驗證紀錄 — 2026-09-29

- 新測試：48 passed；delta_device 全模組 line coverage 87.67%，門檻80%。CLI/socket子程序覆蓋未合併，CLI另有實際 smoke。
- 真Modbus TCP：day/night/alarm、讀取FC04、未支援地址exception2、FC03/寫入拒絕。
- 真RTU byte path：Linux PTY、獨立CRC fixture、Base1→PDU與unit3，非實體RS485線路。
- Parser：獨立PDF常數、bit0、動態scale、保留值拒絕、exception2 fallback、zero-scale今日電量特殊、low-word-first、三相。
- Outbox：重開恢復、容量、相符ACK刪除、原payload/時間保留、device identity、0600/0700、停用GC下150操作FD無增長。
- MQTT：Paho2.1 NO_CONN→on_publish、callback早到競態、未ACK/錯MID不刪除、TLS cert+hostname設定。
- Runtime：sender離線時採集持續、重送保留時間；queue_full與pending_rows日誌可觀察。
- 兩Delta容器最終重建後均Up，無publishedhostports；sample_queued與broker_ack持續出現。
- 既有sim-001與delta-sim-001同時持續入庫。沒有改動DBschema或重啟既有services。
- 實際瀏覽器：本機4178登入、選delta-sim-001，狀態「持續接收中」、四指標、70筆原始紀錄、無pageerror。
- UI稀疏2秒bucket主series顯示2px點；每series有non-nullpoint，connectNulls仍false。證據output/delta-verification/ui-result.json及monitor.png。
- CLI --once讀出三相230V/60Hz、state2、35°C及今日/累計電量；只診斷，不發布。
- docker compose config --quiet、git diff --check、OpenAPI PyYAML解析/x-delta-telemetry契約檢查通過。
- 架構、安全與code review通過；review發現的Paho ACK卡住與SQLite未close均修復并回歸驗證。

未驗證：實際Delta機型/韌體、實體RS485、Pi ARM硬體、SIM7600G-H/4G、現場TLSlistener與ACL／接收端device_id綁定、長期flash／資源壓測。
範圍：新本機Delta功能及預覽點位顯示，非完整59頁protocol、非現場production acceptance、非整站資安稽核。


## 2026-09-29 RTU 從站增量

- RED：新增PTY從站／缺串口退出測試在原TCP-only版本出現5項預期失敗；先修正PTY echo設定，確認失敗原因為CLI尚不支援RTU。
- GREEN：隔離 `ems-delta-test` 容器、Python3.11.15、pymodbus3.6.9、無外網；64 tests passed，coverage 95.10%。命令：`python -m pytest tests --cov=delta_device --cov-report=term-missing --cov-fail-under=80 -q -p no:cacheprovider`。
- 新增真實CLI RTU PTY：day/night/alarm、literal230V、FC03/06/16拒絕、非法位址、其他站號及廣播讀寫無回應、badCRC後恢復、CLI互斥參數與缺串口fail-fast。
- 兩PTY bridge：正式Poller→正式RTU CLI→解析器，9600/base0/scale0與38400/base1/scale absent；230V、0kW、1234.56kWh、35°C均符合預期。單元驗證RTU不呼叫TCP啟動且取消時shutdown。
- 既有TCP、protocol、SQLite/outbox、MQTT測試同時通過。Python3.9註記採future annotations，最低版本實際runtime未於本批執行；Windows COM、實體線路與4G仍待驗證。未啟停既有demo/正式服務。

審查完成：architect、security、code review 與 Python reviewer 均無未解決阻擋項。Python reviewer 另於隔離容器獨立執行 RTU simulator/TCP/原RTU共25項測試通過；環境沒有 ruff/mypy/black/pylint，未宣稱執行。


### ADR-034 最終部署補充：保留同期控制介面
驗收期間 ADR-033 的新控制 wrapper 已由另一批更新部署；本次最終以該已上線映像為基底，僅 COPY 已驗證的 delta_device，保留控制介面/認證設定。新映像 `ems-delta-noise-control:20260929` 同時標記為既有 `ems-delta-simulator`；新舊基底與 source hash 證據在 `output/delta-one-second-20260929/`。edge 維持本次一秒排程版本。先前 standalone compose 與 compose.before 只記錄過渡階段，**目前不得直接使用它回復已上線的控制 wrapper**；需回復此補丁時用 `control-runtime-before.json` 的基底映像並保留現有控制 Compose，先核對是否有後續改動。

環境限制：容器內 45 次一秒計時觀察到兩次 UTC 差值約 4.586 秒、monotonic 差值仍為 1.000 秒；主機 UTC 跳快約 3.586 秒。同一時段 sim-001 與 Delta 均有時間缺口，非 Delta 獨有停止採樣。保留真實時間與缺口，不偽造補值。未調整 WSL/主機時鐘或 NTP。最終 API 驗收必須區分正常一秒節拍與共用時間跳動，不宣稱連續 UTC 每秒零缺值。


### 一秒 demo 驗證補充（2026-09-29）
新邏輯以 7 項 RED 測試重現缺少 noise/固定節拍能力；GREEN 後完整 Delta 測試共 72 passed、總 line coverage 95.19%，涵蓋 TCP/RTU、協定倍率、情境切換、queue/publisher 及新增噪聲/節拍。
驗收期間另一批 ADR-033 控制介面已上線，本次誤差模型已補入該運行映像，保留控制與認證。`runtime-current.json` 及 simulator.py / edge.py 的運行檔案雜湊已比對一致。
注意：主機 UTC 約每隔一段時間跳快 3.586 秒，容器 monotonic 仍每次前進 1.000 秒；sim-001 與 Delta 都留下同時段缺口。因此驗收列出所有共用缺口、檢查中位間隔為 1 秒，並拒絕 Delta 獨有的缺口；不宣稱 UTC 每秒零缺值，也不補造資料。詳 output/delta-one-second-20260929/clock-probe-result.json。


### 最終正式 API / 畫面驗收
- 區間：2026-09-29T08:42:47.725Z 至 2026-09-29T08:44:47.725Z（UTC），Delta 110 筆，原 sim-001 111 筆。
- Delta 間隔：最小 1 秒、中位數 1 秒、最大 4.587 秒。3 個非一秒缺口與既有電表時間缺口吻合；45 秒探針確認 UTC 跳動，monotonic 最大 1.000147 秒。
- 電壓 226.0–234.1 V，50 種不同讀值；電量於同一次運行不倒退。
- 正式 Monitor 的 2 秒彙整有 56 個新電壓桶出現 min/max 差異；四圖渲染、390px 無橫向溢出、JS errors=0。桌面截圖已檢視，圖表反映後端量測與同期情境切換。
- 證據：output/delta-one-second-20260929/live-result.json、live-chart-desktop.png、live-chart-mobile.png、clock-probe-result.json。沒有修改既有歷史或用前端補出一秒樣本。


### 2026-11-12 Windows 實體 RS485 bench（無 Pi）

兩台 USB–RS485 接同一台 Windows PC，COM3 從站／COM4 採集；修正 Windows 短封包後 110/110 成功。獨立 `delta-rtu-sim-001` 的 SQLite 暫存／補送、DB 與 EMS records API 15/15 通過，完整回歸 78 passed、coverage 95.20%。Pi、4G、Delta 真機與長期可靠性仍待驗證；舊紀錄的「Windows COM／實體 RS485 待驗證」僅由本次 bench 範圍更新。重現、證據及限制見 [驗證紀錄](../../output/delta-rtu-bench-20261112/README.md)。


### 2026-11-12 無 Pi 逐關驗證（進行中）

以正式 edge.run 搭配旁路slot帳本驗收，實際PASS/FAIL及限制見 [逐關結果](../../output/delta-no-pi-validation-20261112/README.md)。固定10分鐘5秒基準120/120、DB/API逐筆120/120；其餘關卡按紀錄更新，不能將待測或v2設計當成已驗收。

### 2026-11-12 RTU listener恢復修正

先RED重現Windows poll task死掉但listener未重開，再以loop exception_handler抓出write-close未回收例外。修正後新18項測試通過，完整127 passed、delta_device line coverage95.71%；隔離無網路／無硬體容器驗證。修正後recovery-fix-smoke-01實體正常採集與DB/API3/3。code／Python審查Approve；物理USB重驗尚未完成，關卡4舊FAIL保留。[證據](../../output/delta-no-pi-validation-20261112/README.md)；[ADR-040](../../doc/adr/ADR-040-delta-rtu-listener-recovery.md)。

2026-11-12 12:16更新（ADR-040）：COM3修正後實體拔插usb-com3-04-fixed通過，離線33.328秒，恢復上界9.672秒，原程序持續運行，52筆DB/API逐筆相符、pending0；COM4仍待獨立測試，關卡4只部分完成。實際證據以逐關紀錄為準。

12:22 usb-com4-01：恢復上界3.047秒，52/52對帳、pending0，但wrong_usb_events=1（COM3也曾失效並重開），原工具FAIL不改；COM4單端判讀INCONCLUSIVE，關卡4仍部分完成。詳逐關紀錄。

2026-11-12 12:30：COM4-02單端恢復上界2.516秒、55/55 DB/API對帳、pending0；離線27.235秒未達28秒預設下限，原FAIL不改，操作時長判讀INCONCLUSIVE待受控計時補驗。COM3維持已通過，整關未完成。

usb-com4-03-timed依使用者指示取消，不完整run不計驗收。COM4-02恢復2.516秒、55/55對帳，但27.235秒離線操作偏差保留，使用者不再補驗秒數。COM3正式PASS；不能將COM4工具FAIL改稱無條件正式PASS。

### 第5關實體故障（2026-11-12）

六類各20次、共120案；前五類100案皆通過，late 20案皆先逾時、第二查詢誤收舊2300（應2400），late_order_verified全部true，errors全部空。Gate5 FAIL，原始資料與來源快照見[frames-01](../../output/delta-no-pi-validation-20261112/frames-01/README.md)。沒有MQTT／DB寫入，也不能當成真機或完整sample測試。USB精確秒數補驗已依使用者取消。

### ADR-041完整sample保護（2026-11-12）

原版完整sample替身重現舊AC跨close/open污染；修正為不確定交易鎖定、未知時限停採、有核定時限隔離重建與field啟動等待。實體完整sample unknown20/20不發後續請求，有界lab1秒20/20丟棄舊AC並取得240V／9.36kW；未連MQTT，未將故障值入庫。163項隔離回歸、production line coverage96.06%。真機上界未核定，無界late舊FAIL與R20-BENCH-01 Open保留。詳[修正證據](../../output/delta-no-pi-validation-20261112/rtu-recovery-policy/README.md)；共用runtime未部署本次修正。

2026-11-12最終逐關結果：ADR-041完整sample實體40案通過有界契約；第6關離線300秒、80筆DB/API完整；第7關強殺10次、30筆恢復且DB/API完整；第8關私有SQLite容量故障通過。完整164 passed、production line coverage96.06%。中央DB ACK仍缺、第9關BLOCKED，1h／24h未驗，未部署共享runtime。[完整紀錄](../../output/delta-no-pi-validation-20261112/README.md)。

## 2026-11-12 續驗：DB確認反例與長測

[最新逐關紀錄](../../output/delta-no-pi-validation-20261112/README.md)：第9關以私有真MQTT／production傳送端／受控SQLite重現3案，v1系統驗收FAIL；未操作共享DB，v2中央commit receipt／去重待實作。本機Monitor攔截API的5案新鮮度及圖表／卡片／表格值通過，只屬UI契約。1秒1小時於13:49啟動，通過才進5秒24小時，當前以紀錄內活動status為準；未先報長測通過。保持PC開機及兩顆USB，不再人工拔插。回歸183 passed、production coverage96.06%；無API／schema變更、未部署共享runtime。

## 2026-11-12 時鐘／TLS補驗完成

[補驗紀錄](../../output/delta-no-pi-validation-20261112/field-security-02/README.md)：正式edge加真Modbus TCP／SQLite／私有TLS broker，時鐘2案11階段、TLS10案，共12/12通過；7個憑證／認證拒絕案保留pending，同Publisher1.0274秒重連。只注入測試UTC／節拍及sender permit，不改主機時鐘或COM。首輪9/12失敗保留，工具修正後另驗；完整回歸191 passed／12 skipped，12項隔離案已另實跑，production coverage96.06%。私有容器已清理，無API／schema／production改動、未部署共享runtime。1秒／1小時已PASS、5秒／24小時仍運行；中央receipt／去重、多設備仍待實作，非Pi／4G／真機准入。
