# 第7關：10次採集程序強制終止 PASS

正式COM3 simulator與COM4 edge.run子程序、19200/8N1/unit1/base1。私有Gate阻擋上傳，保持同一個私有SQLite。每輪3筆正常採集已commit，在第4筆特定故障點執行INSERT但未commit，parent只強制終止自身的實際Python child。

10輪各3筆，共30筆已提交；每輪冷開都精確比對完整累積集合（pending3、6…30），10筆未提交timestamp全部不在恢復集合；每次integrity_check=ok。停止／未提交時段是故障缺測，沒有補造0或舊值。DB及若存在的journal sidecars在重新開啟前複製保存；未宣稱特定hot-journal header／回滾路徑或主機斷電。

最後改由新的replay子程序，以正式Publisher／drain補送同一SQLite，30筆原時間與四欄位逐筆DB/API一致：missing／extra／duplicates／mismatched全0，pending_end=0。observations保留PUBACK後仍須等非同步入庫的過程，不把broker ACK當DB commit。

單輪前置smoke另存crash-smoke-01（3/3），不併入正式10輪分母。Windows工具直接啟動base interpreter並保留venv purelib，實測Popen PID等於實際child PID；避免venv redirector使父程序檢查／kill指錯對象。所有worker/replay限制在parent manifest、run ID、同run outbox、demo固定ID及loopback。結束後僅自有程序被清理，共用EMS服務不重啟。

執行來源見../storage-tools/source；run.json／config／cycles／各cycle未提交marker及DB副本／samples／crash-result／children.log均保存。這是Windows程序崩潰恢復與端到端補送證據，不是Pi、4G、SD斷電或中央committed ACK驗收。
