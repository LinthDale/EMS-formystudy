# 第6關：5分鐘上傳中斷 PASS

2026-11-12；保持COM3→60cm估計雙絞線→COM4正式採集不中斷，只阻擋私有loopback Gate到共用broker的測試sender連線。沒有停止共用broker、重啟採集器或重建Publisher。

離線300.016秒；恰有排程slot2..61共60個採樣槽，全部提交SQLite，離線期間broker ACK為0。整個80槽皆有效且提交，無漏槽／重複／golden錯誤／讀取錯誤；poll p99=max0.344秒。

同一Publisher實例恢復連線並清空outbox。80筆均以原始採集時間與四欄位逐筆核對DB、EMS records API，missing／extra／duplicates／mismatched均0；pending_end=0。恢復後96.312秒觀察到完整DB核對，符合2分鐘目標；工具在整個採樣窗結束才做DB核對，因此這是上界，不是精確DB入庫時間或實際補送耗時。additional-metrics.json另列連線及ACK觀察。

本次採用rtu-recovery-policy/lab-bench.json明示的受控本機時限，不是Delta真機核定值。這證明本台架的正常採集／SQLite／sender自動重連／DB與API集合一致，沒有補上中央DB committed ACK協定，也不是4G或主機斷電驗收。設定／來源快照／事件／SQLite／summary／network-result／db-comparison均保留，不含密碼。
