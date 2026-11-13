# 無 Pi 接手測試（2026-11-12 16:06）

使用者確認替換 Pi 尚未到位，要求接續不需要 Pi 的測試。此輪對應 PRD-0020 §13、ADR-040／041 與既有無 Pi 計畫；沒有修改 production 程式、設備設定、API、schema、共享容器或活動長測來源，未 commit／push。權威 checkout 為 `/home/dalelin/synaiq/EMS`，原有未提交變更保留。

## 本輪實測結果

| 項目 | 結果 | 證據及範圍 |
|---|---|---|
| 凍結來源回歸 | 191 passed、12 skipped；production line coverage 96.06% | [完整輸出](regression-02/pytest.log)、[JUnit](regression-02/junit.xml)、[結果](regression-02/result.json)；52 個程式／測試檔之外另補 config 範本，實跑來源與 checkout 雜湊一致。network-none、0.5 CPU／256 MiB，無 COM 掛入 |
| 私有時鐘／真 TLS | 12/12 PASS、0 skipped | [結果](field-security/result.json)、[逐案紀錄](field-security/cases.json)；一般回歸跳過的 12 案在此實跑。正式 edge、真 TCP／SQLite／TLS，注入 UTC；非 RTC／NTP 精度或 Pi 驗收。兩個自有容器皆已移除 |
| 長測已完成區間 | 863/863 有效及提交，DB／API 各 863 逐筆一致 | [區間結果](interim-01/result.json)、[原帳本快照](interim-01/events-snapshot.jsonl)；14:49:53.637469 至 16:01:48.637469 的半開區間（Asia/Taipei），另留至少 30 秒入庫時間；缺槽／重複／錯值／golden 錯誤均 0，poll p99=0.360 秒、max=0.375 秒。不是 24 小時最終驗收 |
| 真實本機 Monitor | 1440px／390px 兩個寬度 PASS | [介面結果](live-ui-02/result.json)；實際登入 `127.0.0.1:4178/live/Monitor.html`，選 `delta-rtu-sim-001`。無假 API 回應，卡片及四張圖的 720 個 signal/bucket 項目與實際 history API 相符；100 筆原始紀錄數值、時間一致。頁面無橫向溢出、JS 錯誤或控制寫入；完整登出後關閉自有瀏覽器 |
| UI 到採樣來源追溯 | 100/100 | [跨層核對](live-ui-02/cross-layer.json)、[顯示時間核對](live-ui-02/time-cell-check-02.json)；上述 100 筆 UI／API 原始紀錄再與活動採樣帳本及 DB 逐筆比對，無缺少／額外／重複／錯值。時間顯示到秒，保留 API 原始微秒；390px 是桌面 Edge 窄視窗，不是 iPhone 實機 |
| 長測來源與舊證據保護 | 全部相符 | [完整性結果](integrity-check.json)：舊靜態證據 770 檔、歸檔凍結來源 17 檔、Windows 活動凍結來源 17 檔及 verifier 依賴 3 檔全部 SHA256 相符；未修改或重算舊 manifest |
| 共享服務 | 17/17 原容器 ID 維持 | [本輪狀態](status.json)、[前](containers-before.json)／[後](containers-after.jsonl)；未重啟共享服務，無遺留本輪測試容器 |

## 長測仍進行中

16:06:22 唯讀核對 controller PID 4564、bench PID 18924、simulator PID 5524 的 parent／啟動時間／命令列仍符合原 run，並保存 [程序](processes-after.json)、[status 快照](soak-status-after.json)、[事件尾端](soak-events-tail-after.jsonl)。活動來源仍是 [原動態 status](../delta-no-pi-validation-20261112/soak-sequence-01/status.json)，本目錄快照不會自動更新。

1 秒／1 小時的 3,600 筆結果沿用原證據，本輪未重跑。5 秒／24 小時共 17,280 槽，預計 **2026-11-13 14:49:53（Asia/Taipei）** 採樣結束，之後仍須收尾及 DB／API 完整對帳。此次 863 槽與 UI 100 筆檢查均不能抵扣剩餘時長或代表最終 pending0。

維持電腦、USB 及既有 EMS 服務；不占用 COM3／COM4、不更動凍結 verifier、不做已取消的人工秒數拔插補驗。完成時由原 controller 保存階段結果，接手者核對 soak-result、summary、db-comparison、退出碼、缺口分類及 pending 後才能判定。

## 本輪檢查流程偏差（保留原結果）

- [首輪回歸](regression.log)為 190 passed／1 failed／12 skipped：本輪快照漏帶 `config`，不是產品測試行為失敗。另開 `regression-02` 補齊快照後重跑，未修改 production 或測試斷言；原結果不覆寫。
- 首次 Windows Node 從 UNC 工作目錄啟動時，解析父目錄 package.json 失敗，尚未啟動瀏覽器；改從本機工作目錄啟動。
- [live-ui-01](live-ui-01/result.json)兩個寬度的資料檢查均通過，但收尾直接點擊收合選單內的登出按鈕逾時，整輪保持 FAIL。`live-ui-02` 先展開帳號選單再登出，完整通過；未改產品介面。
- [時間字串首驗](live-ui-02/time-cell-check.json)失敗原因為 Node Intl 使用 U+2009 空格、瀏覽器使用一般空格（[診斷](live-ui-02/time-locale-diagnostic.json)）。另以明確 UTC+08:00 解析顯示時間、比對 API 同一時間到秒，兩寬度各 100 筆通過；原字串失敗保留。

## 重現與來源

- 回歸的完整容器命令與 immutable image ID 在 [command.json](regression-02/command.json)，唯讀來源在 `regression-02/source/`，其 [SHA256](regression-02/source-sha256.json)於執行前保存且執行後核對。新 run 使用新證據路徑／名稱。
- 時鐘／TLS：在權威 WSL 執行 `python3 services/delta/tools/bench_field_checks.py --output /home/dalelin/synaiq/EMS/output/<全新目錄>`。工具自行保存來源、JUnit、結果與清理資訊；不得指向本輪或既有目錄。
- 區間對帳以讀取時的完整 JSONL 行做快照，依 window_start、monotonic 與 5 秒間隔建立已完成槽數，保留至少 30 秒 settling；使用現有 summarize_slots／golden_errors／reconcile 與唯讀 DB／records API。沒有捏造 window_end 或對未完成 run 呼叫正式 verify。
- UI 使用真實登入與 API，只允許登入／登出兩種非 GET 請求。四個實際 served 檔及 hash 保存於 `live-ui-02/`；帳密只由既有本機登入檔載入，未寫入證據。

## 仍未完成

中央 committed receipt／去重／缺筆對帳仍未實作，原第 9 關 v1 FAIL 維持；本輪沒有把正常送達、TLS 或 UI 通過當作可靠送達保證。Pi／SD／4G、ADTEK 真溫度全鏈路、真機 register profile／回覆上界及現場線路仍待驗證。Pi 未到位時先維持此無 Pi 範圍，不要求使用者提供替換機 SSH。
