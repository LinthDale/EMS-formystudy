# COM3 第一次拔插：恢復觀察不足

2026-11-12 Asia/Taipei。usb-result.json 原始 passed=false 保留。

- COM3 離線35.844秒，重新出現仍為COM3，未拔錯COM4。
- usb_present=03:26:03.125 UTC；sampling_window_closed=03:26:08.485 UTC，只餘約5.36秒。
- 重插後沒有新的attempt（最後一次attempt在03:25:58.470 UTC），不能據此判定15秒恢復門檻失敗；人工判讀為INCONCLUSIVE，需重測。
- 52個有效樣本均逐筆通過DB/API核對，pending0；故障段有缺測，未填假值。
- 原工具五分鐘窗口未替使用者操作預留足夠恢復時間，此為測試限制，不將不足證據歸因於設備。
