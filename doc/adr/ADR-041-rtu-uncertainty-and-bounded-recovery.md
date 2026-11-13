# ADR-041：RTU 不確定交易鎖定與有界恢復

## Status
Accepted（2026-11-12；本機實作範圍），對應PRD-0020 FR-2003，補充ADR-029／031／040。真機profile上界仍待核定。

## Context
第5關實體台架20/20重現read逾時後誤收前次合法回覆。完整sample記憶體反例亦重現：舊AC區塊可跨越串口關閉／重開，組入下一輪量測。RTU FC04不回傳起始位址或交易ID，不能只靠CRC、清buffer或固定sleep排除任意遲延。

## Decision
1. RTU請求可能送出後，若發生本機I/O錯誤、壞包、短回覆或無法確認的回覆，丟棄整筆sample並鎖定不確定狀態。鎖定跨read／sample／close／connect；不發送下一個請求，不在當輪立即重試。已確認的Modbus ExceptionResponse不等同遺失交易，exception2的倍率fallback保持。
2. modbus新增response_lifetime_seconds（可省略；配置時有限數0.01..120秒）與response_lifetime_source（配置上界時必填1..256字非空來源）。它是舊請求最後一個byte可能抵達主站的已核定上界，涵蓋設備、USB與驅動，不等於timeout，不自動由timeout推導。
3. 有上界時，從失敗時間起等待完整上界，期間每次poll直接回報RecoveryPending、不阻塞排程。期滿後關閉舊client、建立全新client／framer、開埠並清除接收buffer，再開始全新sample；失敗仍保持不確定。未知上界則SynchronizationUncertain，停新採樣，既有可信outbox繼續傳送。
4. Field RTU啟動必須有上界及來源，並先執行完整啟動隔離等待，避免重啟清掉記憶體鎖定成為旁路。CLI --once也先完成啟動等待。來源欄僅記錄受信operator核定依據，不自動證明文件／上界真實性；錯誤或被設備違反的上界不提供保證。Demo診斷初始總線由測試建立乾淨條件，但遇錯同樣鎖定；無上界不自動恢復。
5. TCP、解析倍率、MQTT／SQLite／DB契約不變，無遠端解除鎖定API。ADR-040模擬器同埠重開保持；採集器自動恢復證據此後須限定於有界profile，不能沿用舊USB報告宣稱未知field profile已合格。

## Consequences
未知field時限會拒絕啟動或停新採樣，優先避免不確定資料。台架可明示本機模擬器的測試上界，但不是M70A-262／RPI-M30A廠商保證。正常模式沒有額外等待；故障後有可追溯缺測，不補零、不改時戳。最大上界影響可恢復時間，1／5秒採樣不代表故障時仍不漏槽。

測試必須包括完整sample跨次舊AC、同連線和重連不可繞過、已知上界內遲到資料的丟棄及新值恢復、field啟動隔離、設定範圍／來源、合法exception2、未知上界下sender仍可送可信資料。任意超出上界的舊回覆不宣稱可辨識，原無界故障證據保留。

## 驗證（2026-11-12）

完整sample實體台架unknown鎖定20/20、有界lab隔離恢復20/20，未連MQTT；164項隔離回歸通過、production line coverage96.06%。[證據](../../output/delta-no-pi-validation-20261112/rtu-recovery-policy/README.md)。五分鐘上傳中斷、程序強殺10次及私有SQLite容量故障亦已執行，詳[逐關紀錄](../../output/delta-no-pi-validation-20261112/README.md)。真機上界待核定，無界原FAIL及R20-BENCH-01 Open保留；本機修正未部署共用runtime。
