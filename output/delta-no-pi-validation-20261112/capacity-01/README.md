# 第8關：私有SQLite容量／故障邊界 PASS

Windows原生Python執行正式Outbox；全新私有DB，不碰實際採集outbox或填滿系統碟。

1. row limit=3，先保存3筆，再新增被OverflowError拒絕；原pending逐列不變。
2. 在私有連線將PRAGMA max_page_count固定為目前頁數；新增仍在production snapshot大小界線內的大樣本，得到真SQLITE_FULL；原pending逐列不變。
3. 移除頁數注入，正式enqueue再次成功；原3筆保留並多1筆，integrity_check=ok。
4. 複製這個私有DB並破壞header；正式Outbox拒絕啟動，損壞副本bytes hash不變，沒有刪除重建成空DB。

capacity-result.json全部條件true。這是SQLite page-limit故障注入與受控毀損副本，不是OS整碟耗盡、隨機page corruption、SD磨耗、Pi供電中斷或資料自動修復。損壞資料庫需保留證據及人工處理，不宣稱能自行還原。來源見../storage-tools/source。
