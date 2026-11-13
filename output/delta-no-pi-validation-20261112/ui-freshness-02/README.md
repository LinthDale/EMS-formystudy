# Monitor新鮮度與數值契約：5/5 PASS

實際開啟本機4178 Monitor，攔截API提供固定fixture；沒有使用登入憑證、沒有API寫入或資料庫寫入。這不是實際補送全鏈路或公開站驗收。完整DOM判定見 [result.json](result.json)，當時實際提供的四份前端來源與 [SHA256](source-sha256.json)並列保存。

新資料→live、兩分鐘前資料且registry last_seen為現在→stale、未來兩分鐘資料→stale、空資料→empty、history回502→error，五案通過且無JS錯誤／API寫入。新資料與歷史補傳另核對四張卡片、四個ECharts主series的非空數值與原始表格，分別為230V、13A、9kW、655.38kWh。

工具完成、來源保存及browser清理全部成功才輸出passed=true；來源下載／清理失敗也須輸出false並以失敗exit退出。原ui-freshness-01保留：初版只查圖表容器，且來源保存或清理失敗可能假PASS，不作最後驗收依據。修正後另開本run並經獨立code review Approve。

重現：在已運行的本機4178預覽上，以具Playwright的Node環境執行`node services/delta/tools/bench_ui_freshness.cjs output/delta-no-pi-validation-20261112/ui-freshness-new`；輸出目錄必須全新。不改UI資產或現有圖表樣式。

僅證明Monitor按量測時間區分新舊資料；device-service接收時間／心跳拆分與v2 receipt仍未完成，不代表全系統在線狀態已解決。

失敗收尾另以[故障探針](../ui-verifier-negative-02/README.md)2/2確認：情境全過後來源404或收尾拋錯，最終artifact仍為false、exit1。第一次探針設定失敗保留，不當成通過證據。
