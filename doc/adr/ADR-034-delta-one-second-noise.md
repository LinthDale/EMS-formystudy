# ADR-034：Delta demo 每秒採樣與量測誤差

## Status
Accepted（2026-09-29，使用者要求參照 sim-001 每秒一值且具誤差）；PRD-0020 FR-2001/2003/2007 增補。

## Context
目前 Delta demo 每次完成採集後等待 10 秒，实际約 10–14 秒；固定 230V 與規則功率使圖表有別於電表。現有 set_scenario 情境切換、累計電量結算及控制介面的並行工作必須保留。

## Decision
本機 demo.json 的 poll_interval 改為 1。edge 使用 monotonic 截止時間排程，正常週期包含讀取耗時；過慢時略過已錯過節拍，不補造資料或密集追趕。field 範本與設定預設仍為 10 秒。

Compose 的 delta-simulator 明示 DELTA_SIM_NOISE=1（未設定時關閉以保留協定固定測試值）。每秒固定一組可重現的三相讀值，同秒分段 Modbus 讀取共用快照；相電壓基準 230V，Gaussian 標準差 1.5V、截於 ±4.5V；相電流依基準功率計算，標準差 0.15A、截於 ±0.45A。三相功率以各相 V×I 計算、假定功率因數 1，總功率為三相相加。這是展示用量測誤差，非廠商精度宣告。夜間/故障功率與電流保持零，電壓可有量測波動。

累計/今日電量保留基準發電曲線的積分，不疊加隨機誤差，防止計數器倒退；與瞬時含誤差功率積分可有小差異。情境切換先結算再清除快照，保留 ADR-033 既有控制行為。noise 可由建構參數/固定 seed 測試，不修改 Modbus/MQTT/REST 格式或量測欄位。

## Consequences
只重建兩個 Delta 服務。重啟模擬器仍會重設示範電量基準，歷史保留且應區分此次切換。1 秒/10000 筆 queue 約 2.8 小時容量；field 10 秒約 27.8 小時。接收仍為既有 PUBACK/Telegraf 管線，非端到端零遺失保證。UI 自動刷新與 2 秒彙整獨立，不需變成每秒 HTTP 查詢。

驗收：單元測試固定 seed、同秒一致、逐秒改變、誤差上下界、三相功率、night/alarm 與 energy；排程耗時補償與超時略過；既有 TCP/RTU/queue 全測試；真實兩服務 → MQTT → DB → BFF 連續至少 60 秒每秒記錄、圖表 min/max 與原有 sim-001 同時前進。


### ADR-034 最終部署補充：保留同期控制介面
驗收期間 ADR-033 的新控制 wrapper 已由另一批更新部署；本次最終以該已上線映像為基底，僅 COPY 已驗證的 delta_device，保留控制介面/認證設定。新映像 `ems-delta-noise-control:20260929` 同時標記為既有 `ems-delta-simulator`；新舊基底與 source hash 證據在 `output/delta-one-second-20260929/`。edge 維持本次一秒排程版本。先前 standalone compose 與 compose.before 只記錄過渡階段，**目前不得直接使用它回復已上線的控制 wrapper**；需回復此補丁時用 `control-runtime-before.json` 的基底映像並保留現有控制 Compose，先核對是否有後續改動。

環境限制：容器內 45 次一秒計時觀察到兩次 UTC 差值約 4.586 秒、monotonic 差值仍為 1.000 秒；主機 UTC 跳快約 3.586 秒。同一時段 sim-001 與 Delta 均有時間缺口，非 Delta 獨有停止採樣。保留真實時間與缺口，不偽造補值。未調整 WSL/主機時鐘或 NTP。最終 API 驗收必須區分正常一秒節拍與共用時間跳動，不宣稱連續 UTC 每秒零缺值。
