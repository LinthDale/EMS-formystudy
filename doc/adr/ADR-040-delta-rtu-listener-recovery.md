# ADR-040：Delta RTU 模擬器串口斷線恢復

## Status
Accepted（2026-11-12；隔離模擬器本機範圍），延伸 ADR-031，對應 PRD-0020 FR-2008。

## Context
Windows COM3 模擬器端 USB 拔插後，兩次實體台架確認串口同號重新出現，但持續186／239秒沒有有效回應。pymodbus3.6.9 的 Windows serial polling 在 in_waiting 讀取失敗時可能直接結束 task，而 server 仍等待 serving future；目前沒有對此狀態的復原。記憶體串口使用實際 pymodbus transport 已重現 handle 不關閉／不重開。

## Decision
RTU 模擬器在第一次成功開啟後監看指定串口的 transport／serial handle／Windows poll task；斷線或 poll task 的 OSError 導致失效時關閉舊 server，再重建同一個 operator 指定的本機端點。共用同一個資料 context，保留情境、倍率及累積電量。第一次開啟失敗仍立即退出；未知程式錯誤不無限重試。取消時關閉串口與背景 task。

監看間隔與重開等待集中由 config 讀取 DELTA_SIM_RTU_HEALTH_SECONDS（預設0.5秒）及 DELTA_SIM_RTU_RECONNECT_SECONDS（預設2秒），範圍0.01–60秒、有限正數。僅模擬器 RTU 模式適用，不探測其他COM、不因COM改號自動換設備、不新增網路 listener，也不改採集器的讀值、CRC或時戳判定。

## Consequences
同一COM的模擬器USB重新插入後可嘗試恢復，並記錄 serial_disconnected／simulator_ready；不宣稱15秒必達，須實體重驗。Windows 記憶體串口與 Linux PTY 回歸不能代替 USB 實測。COM4採集器端仍須獨立驗證。中央DB ACK及遲到封包風險不由本修正解決；無依賴升級、API、資料表、服務或部署拓樸變更。

2026-11-12 12:16更新（ADR-040）：COM3修正後實體拔插usb-com3-04-fixed通過，離線33.328秒，恢復上界9.672秒，原程序持續運行，52筆DB/API逐筆相符、pending0；COM4仍待獨立測試，關卡4只部分完成。實際證據以逐關紀錄為準。
