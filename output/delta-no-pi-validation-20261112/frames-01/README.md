# 第5關：實體RS485封包故障

2026-11-12，COM3 FTDI BG04PB77A → 約60公分雙絞線（使用者估計）→ COM4 FTDI BG04PB7RA，19200/8N1、unit1、base1、timeout設定3秒。Python3.12.14、pymodbus3.6.9、pyserial3.5。

實際執行production Poller.read，從站由獨立literal／CRC工具回覆，每個案例兩次不同位址的FC04查詢。不是完整edge.sample→SQLite→MQTT測試；本輪不連MQTT、不發布故障資料、不驗證Delta真機。

| 注入 | 次數 | 通過 | 結果 |
|---|---:|---:|---|
| 合法分段 | 20 | 20 | 完整解碼2300，下一讀取2400 |
| 截斷 | 20 | 20 | 首次拒收，下一次正確2400 |
| 錯誤CRC | 20 | 20 | 首次拒收，下一次正確2400 |
| 錯站號 | 20 | 20 | 首次拒收，下一次正確2400 |
| 無回應 | 20 | 20 | 首次逾時，下一次正確2400 |
| 遲到舊回覆 | 20 | 0 | 首次逾時後，舊2300被第二次查詢誤收，應為2400 |

## 遲到回覆證據

每案先送request1（PDU49152/count1），從站不回應，等實際read1結束才送request2（PDU49153/count1）；從站偵測request2後才送舊2300，原訂100ms後送新2400。20案皆確認 `first.finished <= request_times[1] <= sends[0].monotonic`，不是用timeout設定值猜測read1已逾時。第二次read均接受2300，20案late_order_verified=true、errors=[]。

第二次read已錯誤接受2300並結束，工具清理可能在新2400實際傳送前停止從站；此不影響舊值已被誤收的結論，不能宣稱新回覆也已送達或被丟棄。完整raw hex、時序及讀值見cases.jsonl；統計見summary.json／analysis.json；來源與雜湊見source／manifest.json。

無回應及late首次讀取實際約6.109–6.141秒，不能把3秒設定當作完整交易硬deadline。合法分段約0.078–0.110秒。數字只適用當次Windows台架。

## 結論與限制

第5關FAIL：格式正確不足以判定回覆對應當前查詢。本測試刻意讓舊回覆於下一請求後出現，是無既定最大遲延保證的故障模型；不能藉延長timeout或預先flush一次宣稱解決。不能據此聲稱Delta真機已發生相同故障，或此read-path錯值已通過完整sample進入EMS。

從[Delta V1.35 §2.2（PDF第7頁）](https://solarstorageaccount.blob.core.windows.net/pvi/manual/modbus/DELTA_Three-phase_products_protocol.pdf)的FC04回應格式可知，其列有站號、功能碼、byte count、數據與CRC，未回傳起始位址／交易序號。由此推論，相同站號／功能碼／長度的跨交易舊回覆存在識別歧義。[Modbus Serial Line Guide §2.4.1](https://www.modbus.org/file/secure/modbusoverserial.pdf)要求應用設定回覆等待，且足以容納設備處理。尚未核定M70A-262／RPI-M30A對應韌體的最大回覆時限，不自行填寫廠商保證值。

下一步先定義設備profile回覆時限與逾時復原契約，再TDD驗證串口／framer狀態清理、受控隔離等待、錯誤／恢復品質及整輪sample錯值拒收。無法證明時效時明示不確定，不把收包時間當設備新鮮度。此為修正方向，尚未實作；第6–10關未因此通過。
