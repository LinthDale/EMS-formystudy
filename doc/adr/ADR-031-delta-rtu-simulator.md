# ADR-031：Delta 模擬器支援 RTU 從站

## Status
Accepted（2026-09-29；本機模擬範圍）。延伸 [ADR-029](ADR-029-delta-edge-telemetry.md)，對應 PRD-0020 §15.1；使用者要求補 RTU 從站模式。

## Context
硬體到貨後需由電腦提供原始 Delta 暫存器，經兩顆隔離 USB–RS485 轉接器，讓樹莓派主動採集、解析並測試後續傳輸。原 simulator 僅 TCP；既有 Poller 已有 RTU client。

## Decision
同一 simulator CLI 新增明確的 `--transport rtu`，沿用 FC04 唯讀資料表、倍率、位址基準及 day/night/alarm。TCP 仍為預設；RTU 只開指定本機串口、不開 TCP listener。站號 1–247，9600/19200/38400 baud、8N1；不接受網路 serial URL。未設定/無法開啟串口即失敗退出；錯站號與廣播不回應，寫入與非白名單讀取不能改動資料。

PC 是從站（server），Pi 是唯一主站（client）。不自動尋找、啟動或探測現場設備，也不在已有主站的現場總線掛入第二個主站。SIM 與 parser 保留相同 V1.35 子集，不能當作 M70A-262 或 RPI-M30A 的實機協定認證。

## Consequences
Linux PTY 測試可驗證正式 CLI、RTU bytes/CRC/站號/唯讀與既有 TCP 回歸；不能驗證 RS485 電氣層、Windows 驅動或 4G。實體驗收需兩顆隔離轉接器、線材、終端/訊號地及相同串口參數。Pi → MQTT → DB 的既有 PUBACK 與重送限制不變，ADR-030 仍未實作。
