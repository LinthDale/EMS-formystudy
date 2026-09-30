# Delta simulator / parser 本機驗收與現場交接

2026-09-29。正式原始碼位於 WSL /home/dalelin/synaiq/EMS。
詳細安裝與限制見 [services/delta/README](../../services/delta/README.md)。

## 本次已完成
- Delta V1.35唯讀FC04 profile、Base1、动态倍率、low-word-first電量；TCP/RTU simulator及TCP/RTU edge。
- 本機 `delta-sim-001` 手動註冊為confirmed，vendor/model/location明示模擬，四信號source_ref記錄L1與總功率語意。
- 新增 `ems-delta-simulator`、`ems-delta-edge`；Compose profile delta-demo，无hostports；非root唯讀容器。
- 實際MQTT→Telegraf→TimescaleDB→BFF→Monitor已通過；畫面狀態「持續接收中」、四指標、原始紀錄、稀疏趨勢點均可見。
- 本機4178預覽在重啟後恢復。初次本機驗收後，依使用者要求將選單簡稱與2px點位發布為20260929-delta-monitor-v1；既有React並行工作保持不變。
- 新增SQLite持久化queue、TLS field設定、systemd與broker ACL範本；架構與安全審查通過，Paho重連競態及SQLite連線釋放已修復。

## 查看
開啟 http://127.0.0.1:4178/#Monitor ，用既有demo帳號登入，選delta-sim-001。
四個EMS欄位：L1 V/A、三相總kW、累計kWh。其他三相/今日電量/狀態/選用溫度只在CLI診斷及未ACK outbox snapshot。

## 驗收證據
`services/delta/tests/`；`output/delta-verification/ui-result.json`、`monitor.png`。
測試命令、詳細輸出摘要與最終數量見 [validation.md](../../services/delta/validation.md)。
原始 `sim-001` 管線需同時維持新數據；無DB schema改動、無新增HTTP API。

## 尚待現場
目標Delta為M70A-262／RPI-M30A，已知SIM7600G-H；採購規劃Zero 2 W及HAT(B)。到貨版型、設備韌體、RS485/TCP實際選用、APN及TLS broker入口待確認。
必須完成接收端payload身份綁定、真機倍率/電氣接線、可信時間及4G斷線回補驗收。
PUBACK非DB ACK，現有資料庫不去重；這一版不能宣稱現場production-ready或端到端零遺失。

## 回滾
`docker compose --profile delta-demo stop delta-edge delta-simulator`。
保留queue volume與既有歷史；不操作整組down、不刪volume、不動公網。

## RTU 從站與請購更新（2026-09-29）
已新增 PC 原生 RTU simulator；隔離 USB–RS485 請購改為2組，PC與Pi各1組，不含UPS。現場最低配請購單及採購連結頁已更新，已知單價小計 NT$5,970，線材/SIM/運費/待確認稅額另計。檔案位於 Windows 請購資料夾的 `MD-OI-001-002-A4請購申請單(非專案類)_EMS現場最低配_20260929.xlsx`。

從 services/delta 執行 `python -m delta_device simulator --transport rtu --serial-port COM5 --baudrate 19200 --unit-id 1`；PC從站回應Pi唯一主站。9600/19200/38400、8N1、站號1–247，唯讀FC04。Windows與Linux原生安裝、兩顆轉接器接線、Pi --once、後續4G分段驗收見 [DeltaREADME](../../services/delta/README.md#rtu-從站電腦模擬-delta樹莓派採集)。

64項軟體測試通過、coverage95.10%；兩PTY串接正式Poller與RTU CLI成功。實體RS485、Windows COM驅動及4G仍待硬體到貨；不表示已驗收兩款Delta真機或端到端漏送對帳。


## 2026-09-29 Delta demo 一秒採樣與量測誤差（ADR-034）
- `delta-sim-001` 本機 demo 的 `poll_interval=1`，採集用 monotonic 截止時間補償讀取耗時；逾時略過節拍，不補造或密集追趕。
- `DELTA_SIM_NOISE=1` 開啟每秒一致的三相量測誤差：相電壓 σ=1.5V（限 ±4.5V）、相電流 σ=0.15A（限 ±0.45A），功率依三相 V×I 相加。這些為模擬參數，非原廠精度。
- night/alarm 電流與發電功率為零；電量保持基準發電曲線積分，無隨機倒退，情境切換先結算。模擬器重啟仍會回到既有電量基準，新舊資料保留。
- field 範本/預設仍為 10 秒；REST/MQTT/schema、OPS 登入及公開前端版本未變。API 可每秒入庫，畫面刷新/圖表彙整週期獨立。
- 1 秒採樣的 10000 筆 outbox 約 2.8 小時，10 秒約 27.8 小時；PUBACK 非 DB ACK，沒有新增端到端去重/零遺失保證。
- 本次只部署兩個 Delta 服務的既有 standalone runtime，使用 `output/delta-one-second-20260929/compose.yaml`（project=ems，外部既有 network/volume）。主 Compose 正在同步開發 ADR-033 控制介面，僅補上 noise env，沒有將該批尚待驗收的服務一併上線。後續控制介面發布須保留此 env 與 demo 採樣設定。
- 回復：先確認沒有後續部署，再使用同目錄 `demo.before.json` 恢復 demo 設定、`docker compose -p ems -f output/delta-one-second-20260929/compose.before.yaml up -d --no-deps delta-simulator delta-edge`；保留原 queue volume 和 DB 歷史。回復舊 image 會回復原 standalone 程式；不要在 ADR-033 後續上線後盲目套用。


### ADR-034 最終部署補充：保留同期控制介面
驗收期間 ADR-033 的新控制 wrapper 已由另一批更新部署；本次最終以該已上線映像為基底，僅 COPY 已驗證的 delta_device，保留控制介面/認證設定。新映像 `ems-delta-noise-control:20260929` 同時標記為既有 `ems-delta-simulator`；新舊基底與 source hash 證據在 `output/delta-one-second-20260929/`。edge 維持本次一秒排程版本。先前 standalone compose 與 compose.before 只記錄過渡階段，**目前不得直接使用它回復已上線的控制 wrapper**；需回復此補丁時用 `control-runtime-before.json` 的基底映像並保留現有控制 Compose，先核對是否有後續改動。

環境限制：容器內 45 次一秒計時觀察到兩次 UTC 差值約 4.586 秒、monotonic 差值仍為 1.000 秒；主機 UTC 跳快約 3.586 秒。同一時段 sim-001 與 Delta 均有時間缺口，非 Delta 獨有停止採樣。保留真實時間與缺口，不偽造補值。未調整 WSL/主機時鐘或 NTP。最終 API 驗收必須區分正常一秒節拍與共用時間跳動，不宣稱連續 UTC 每秒零缺值。


### 最終正式 API / 畫面驗收
- 區間：2026-09-29T08:42:47.725Z 至 2026-09-29T08:44:47.725Z（UTC），Delta 110 筆，原 sim-001 111 筆。
- Delta 間隔：最小 1 秒、中位數 1 秒、最大 4.587 秒。3 個非一秒缺口與既有電表時間缺口吻合；45 秒探針確認 UTC 跳動，monotonic 最大 1.000147 秒。
- 電壓 226.0–234.1 V，50 種不同讀值；電量於同一次運行不倒退。
- 正式 Monitor 的 2 秒彙整有 56 個新電壓桶出現 min/max 差異；四圖渲染、390px 無橫向溢出、JS errors=0。桌面截圖已檢視，圖表反映後端量測與同期情境切換。
- 證據：output/delta-one-second-20260929/live-result.json、live-chart-desktop.png、live-chart-mobile.png、clock-probe-result.json。沒有修改既有歷史或用前端補出一秒樣本。
