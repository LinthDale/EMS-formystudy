# 單筆槽號異常驗證

2026-11-13 09:07（Asia/Taipei）。依使用者「驗證那筆測試就好，不用重跑」，只讀原始證據、重現原槽號公式並核對 DB／API。沒有開 COM、啟動採集或改 runtime／verifier。

**該筆資料驗證通過：有採到、數值正確、入庫一次；異常是測試工具的槽號誤標。**

| 檢查 | 結果 |
|---|---|
| 該筆來源時間 | 11/12 21:55:38.631664＋08:00；sampled_ns=1794491738631664000 |
| 原始事件 | attempt、read_ok、SQLite committed、broker_ack均有；read／commit／ACK各出現一次 |
| DB／API | 該來源timestamp各恰好1列，四欄與原snapshot一致，golden檢查無錯 |
| 前後文 | 該筆及前後各2筆，共5筆；DB與API均5／5，無缺少、多列、重複或錯值 |
| 槽號原因 | 此次elapsed=25544.985秒，比名義slot5109起點25545秒早約15ms；原凍結程式`int(elapsed // interval)`確實算出5108，與原始記錄一致 |

已核對原執行副本與封存的 bench_run.py SHA256 相同，並以AST確認當時公式；沒有使用事後改過的程式來解釋原紀錄。完整事件快照SHA256與前輪稽核相符。[結果](result.json)、[五筆來源](expected-context.json)、[DB](database-context.json)、[API](api-context.json)、[原始事件前後文](original-context-events.json)、[凍結槽號公式](frozen-slot-formula.txt)。

這是單筆資料與記帳原因的驗證，**沒有修改槽號計算程式或原帳本**。原槽號嚴格FAIL保留，24h仍是已中斷／未完成；此次不重跑長測，也不啟動新硬體測試。
