# 無 Pi 補測：弱網、積壓、真 EMS 介面與 Linux 服務

2026-11-12 16:51（Asia/Taipei）。使用者授權直接執行其餘無 Pi 測試。對應 PRD-0020 FR-2003／2005、§13；介面沿 PRD-0018。新增測試工具及判定測試，未修改 production 採集器、API／schema 或既有部署。這是 PC／WSL 的實測，Pi／SD／4G／真 ADTEK 仍待到貨驗收。

## 實跑結果

| 項目 | 結果 | 證據 |
|---|---|---|
| 10,000 筆積壓＋120 次同步採樣 | **10,120／10,120，缺少／額外／錯內容／重複均 0，pending0** | [原結果](private-sequence-01/bulk-10000/result.json)、[原始預期 payload](private-sequence-01/bulk-10000/expected-payloads.json)、[接收 payload](private-sequence-01/bulk-10000/received-payloads.json)；正式 Outbox／edge／TCP Poller／Publisher，私有 Mosquitto＋SQLite sink。預填為合成舊資料，120 筆新值實際由 TCP simulator 採集；不是等待 10,000 次真實採樣 |
| 積壓補傳時間與資源 | 預填 33.392 秒；runtime 146.293 秒，觀察接收速率約 **69.70 筆／秒**；queue 峰值 10,001 | [資源時間列](private-sequence-01/bulk-10000/resources.json)。此速率包括持續採樣及 sender 的 batch／1 秒等待；是本機 v1、私有 SQLite receiver 的觀察值，不能當中央 durable receiver 或 Pi 的吞吐承諾。worker 限 0.5 CPU／384 MiB，broker 限 0.25 CPU／64 MiB；有 CPU 累計與 SQLite bytes，未量測 RAM 峰值 |
| 弱網＋三次斷流 | **155／155，無缺少／額外／重複，pending0** | [結果](private-sequence-01/weak-stream/result.json)：80 筆積壓＋75 次一秒採樣；名義 RTT 200ms、抖動 50ms、stream cap 16 KiB/s，10／30／50 秒各斷流 3 秒，原 Publisher 自動建立 4 次連線，採樣持續。TCP proxy 的 delay/rate 與斷流是測試注入，**不是 IP packet loss 或真 4G 測試** |
| 使用中 SQLite 備份／還原 | **1,000 筆完整前綴通過** | 在繼續預填時使用 SQLite backup API；[強化獨立判定](private-sequence-01/bulk-10000/backup-independent-check.json)核對備份開始前至少 1,000 筆、完整 timestamp／payload／snapshot 前綴、latest_timestamp metadata 與 integrity_check。改設備身分開啟被拒絕。不是主機斷電或 SD 測試 |
| 實際 EMS 歷史補傳 | **60／60，DB／API／畫面原始紀錄逐筆一致** | [跨層核對](historical-cross-layer.json)：專用 QA 設備先離線 8 秒，再經 100ms stream delay 上傳保留原時間的 60 筆歷史值。接收新近發生，但介面正確顯示 **stale**，未把補傳當成新量測；[真介面](ui-historical-02/result.json)在 1440／390px 的卡片、四張圖及 60 列全通過 |
| 真 EMS 弱網新採樣 | **30／30，pending0** | [結果](local-fresh-01/result.json)：正式 TCP 採樣、名義 RTT 200ms／抖動 50ms／16 KiB/s、兩次斷流（3 秒及 2 秒），同一 Publisher 3 次連線後自動補齊 |
| 介面恢復即時＋總對帳 | **全部 110 筆 DB／API 一致，live 畫面 40 筆可追溯** | 另開 20 秒真採樣窗，在資料持續更新時驗到 **live**：[介面](ui-restored-live/result.json)、[完整對帳](all-local-cross-layer.json)。總數為歷史 60＋弱網新採樣 30＋介面觀察窗 20；真實 DB/API 各 110 筆，無缺少／額外／重複／錯值。1440／390px 卡片與圖表值相符，畫面時間與原始來源時間到秒相符，無 JS 錯誤 |
| Linux systemd 生命週期 | **PASS，自動重啟約 11.300 秒** | [結果](linux-service-01/result.json)、[journal](linux-service-01/journal.log)、[接收證據](linux-service-01/messages.json)。唯一命名 user service 執行正式 edge，SIGKILL 後 MainPID 改變、NRestarts=1；6 筆來源時間嚴格增加，SQLite 完整且 pending0；正常 stop 後不再送資料。RestartSec=10／TimeoutStopSec=30 沿部署範本；路徑與使用者為 WSL 測試環境調整，未驗 Pi 開機／dialout／硬化權限／SD |
| 工具與回歸 | **203 passed／12 skipped，production line coverage 96.06%** | [回歸](regression.log)、[JUnit](regression.xml)。新增 12 項判定測試含同數不同內容、重複、pending／錯誤／未停止、namespace、備份截斷及錯 metadata。12 個 skip 是既有私有時鐘／TLS 測試，本輪未重跑；其先前 12/12 實跑見 [16:06 接手紀錄](../no-pi-takeover-20261112-1600/README.md) |

## 執行隔離與保留資料

- 大量／弱網案例使用 `--network none` 私有 broker，worker 只加入該 namespace；無 host port、COM、Docker socket 或共享 credentials 掛入 worker。namespace 不符拒絕啟動。原 [controller 結果](private-sequence-01/controller-result.json)保存自有兩個 worker 與 broker 的移除結果。
- 少量真 EMS 案例僅寫新的 `delta-backlog-qa-20261112`，以正式 OPS API 建立後人工確認為 electricity，vendor／model／location 明示模擬 QA。註冊前要求不存在，未覆寫其他設備。這個 QA 身分及 110 筆量測保留供追溯，並非真設備資料；sender 均已停止。參見 [註冊紀錄](local-ems-registration.json)。
- 本機 EMS 案例為明示 demo plaintext，只連 loopback broker；不作 field TLS／ACL 驗收。Windows COM3／COM4、原 24h run、共享容器及其來源不變。
- systemd 只建立唯一的臨時 user unit `ems-no-pi-qa-20261112`，並在最後停止；自有 simulator 與 broker 已結束，沒有安裝或更動正式服務。純 Python runtime dependencies 從快取測試映像複製到本證據目錄，未安裝／升級主機套件。
- v1 仍只承諾 broker PUBACK；私有 sink 的接收／commit 以及此次正常中央對帳，不能改寫第 9 關的已知反例。`completion_passed` 表示此 run 的原始集合完整，`unique_delivery_passed` 另列重複；兩者本輪都通過，但中央 committed receipt／去重機制仍未實作。

## 工具判定修正與原失敗

1. 先保存 [RED](tool-red.txt)，新增工具後 11 項反例通過；獨立 Python 複核發現原備份 subset 判定可能把只剩 1 筆的備份當成通過，已改完整前綴／metadata 判定，另加第 12 項反例。修正只在新工具，未改 production。
2. 首批 private run 已凍結舊工具，保持其原結果及 SHA256；bulk 備份再用新版工具另存 [獨立完整前綴核對](private-sequence-01/bulk-10000/backup-independent-check.json)，不是追稱當時已具備新判定。新版 local run 使用修正後來源。
3. [ui-historical-01](ui-historical-01/result.json)與 [診斷](ui-diagnostic-01/result.json)保留窄螢幕 FAIL：setViewport 後立即讀取，canvas 仍為桌面寬度 555px，ResizeObserver 尚未完成重排。工具改為等待 ECharts width 與容器 clientWidth 相等後另開 ui-historical-02，390px 通過；**未修改產品 CSS／JS**。早期推測為設備名稱過長已被此量測排除。
4. 歷史 UI 的額外 registry.json 是 Playwright APIRequestContext 在 loopback HTTP 未回送 Secure cookie 所得 401，未納入通過依據；真瀏覽器頁面的 history／records 回應與 DOM 才是此次 UI 證據。不據此宣稱已額外驗證 registry last_seen 新鮮度。

## 重現入口

- [bench_backlog.py](../../services/delta/tools/bench_backlog.py)、[判定測試](../../services/delta/tests/test_bench_backlog.py)。只補既有 PRD-0020 的測試工具，沒有實作 v2 receiver。
- 私有執行：建立全新 network-none Mosquitto namespace，把其 `/proc/self/ns/net` 傳為 `BACKLOG_QA_NETNS`，worker 加入該 namespace；以 frozen source 唯讀掛入執行工具，輸出目錄必須全新。[bulk 命令](private-sequence-01/bulk-10000-command.json)、[弱網命令](private-sequence-01/weak-stream-command.json)保留實際完整參數；broker／worker 的 image、網路與清理見 controller-result。
- 本機 EMS 僅允許 `--scope local-ems --device delta-backlog-qa-20261112`，拒絕活動長測身分。[歷史命令](local-historical-command.json)、[新採樣命令](local-fresh-command.json)均保留；不要在不知道此 QA 身分是否已存在資料時直接重跑同一日期／時間窗。
- systemd [命令](linux-service-01/command.json)只為本輪路徑／port／unique unit；先建立新的私有端點及工作目錄，不把臨時 port 當部署設定。
- Python reviewer 與 code reviewer 均複核新工具／測試後 Approve。Bandit 無中高風險；未安裝的 ruff／mypy／black／pylint 未宣稱執行。

## 接續

原 5 秒／24 小時長測仍由原 controller 執行，預計 11/13 14:49:53 採樣結束，再做完整 DB／API 對帳。本輪結果不抵扣它的時長。中央 commit receipt／去重、多設備 scheduler、Pi／4G／溫度表完整鏈路保持未完成；這些不以本輪 PASS 宣稱已交付。
