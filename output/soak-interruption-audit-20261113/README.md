# 昨夜重開機後的長測稽核

2026-11-13 08:40–08:45（Asia/Taipei）。本輪唯讀核對原始帳本、SQLite、Windows 系統事件及實際 DB／API，未啟動另一個測試或占用 COM。

**結論：5秒／24小時長測已中斷，未通過。** 狀態檔最後停在 11/12 22:28:46 的 `RUNNING`，是重開機前遺留值，不代表原程序仍活著。沒有 window_end／完整24h結果，原 controller4564、bench18924、simulator5524 均不在。

| 項目 | 結果 |
|---|---|
| 原1秒／1小時 | **PASS保持**；本日重開機後重新讀取DB/API，皆3,600／3,600，原時間／四欄值相符 |
| 原5秒／24小時 | **INTERRUPTED／未完成**；11/12 14:49:53起，最後採樣22:29:13，約7小時39分；5,512筆，占原17,280目標的31.9%，其餘11,768筆未取得 |
| 中斷前已提交資料 | **5,512／5,512 DB與API逐筆相符**，無少列／多列／重複timestamp／錯值，SQLite integrity_check=ok、pending0；這只表示已取得樣本完整入庫，不是整個24h通過 |
| 原始採樣槽號帳本 | **嚴格判定FAIL保留**：5,512筆樣本對應5,511個不同槽號；slot5108標了兩次、5109缺記。第二次5108實際在下一個邊界前約15ms，工具用elapsed // interval因此歸前槽；兩筆來源timestamp不同，DB沒有重複入庫。本輪只診斷，不改原帳本／verifier或追稱PASS |
| 昨日v2修復驗證 | 封存證據752檔hash全部相符，原259 passed／12 skipped、90.81%是昨天已完成的獨立驗證，不受後續長測中斷改寫；本日未重跑，也未將共享v1切v2 |

## 中斷原因

[Windows系統事件](windows-system-events.json)顯示兩次計畫重開機：

1. **11/12 22:29:14，User32／1074**：`MoUsoCoreWorker.exe`由SYSTEM發起重新啟動，理由「作業系統: Service Pack（計劃之中）」，0x80020010。緊接最後broker ACK 22:29:13.726。
2. 22:30:38關閉、22:30:52啟動。
3. **22:31:26，User32／1074**：`TrustedInstaller.exe`再發起「作業系統: 升級（計劃之中）」，0x80020003。
4. 22:31:33關閉、22:31:50啟動；[目前開機時間](windows-boot.json)相符。

因此證據支持 **Windows更新／升級安排的重新開機使長測程序停止**。本次查詢時原PID均不存在；原生測試沒有在開機後自動接回，不可把狀態檔RUNNING或已自動起來的共享容器當作長測繼續。

## 證據與查詢範圍

- [本次對帳結果](result.json)、[最終判定](assessment.json)、[原事件完整快照](events-snapshot.jsonl)、[原採集log](five-second-twenty-four-hours.log)、[原狀態快照](status.json)與[資源紀錄](five-second-twenty-four-hours-resources.jsonl)。原檔不修改。
- [預期樣本](expected-samples.json)、[DB列](database-rows.json)、[API列](api-rows.json)。查詢覆蓋完整原計畫24h的時間範圍，與所有5512個已提交timestamp／四欄值逐筆核對，也檢查帳本之外的額外列。使用本機既有BFF `127.0.0.1:8003`經登入後查詢，未重啟4178預覽proxy。
- [SQLite副本](outbox-snapshot.db)保存原pending狀態；來源以mode=ro檢查完整性與數量，沒有開寫入者或送出補傳。
- [槽號診斷](slot-accounting-diagnostic.json)保存兩次5108原始事件，第二筆elapsed=25544.985秒，比5109名義起點25545秒早0.015秒；來源時間不同，資料集合對帳通過與槽號嚴格FAIL分開記錄。
- [一小時本日重查](one-hour-recheck.json)及[原封存完整性](previous-evidence-integrity.json)：原始靜態770檔與v2修復752檔hash均相符。

下一次24h驗收必須另開新run、連續跑滿並完整對帳；本次已取得資料可保留作約7h39m觀察，不能接續湊成24h。重新跑前需處理更新重開機窗口與槽號邊界記帳，Pi／ADTEK／4G驗收依舊另列。本輪沒有改Windows更新設定或啟動重跑。
