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
