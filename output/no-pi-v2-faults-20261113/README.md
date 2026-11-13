# 無 Pi 短測：v2 故障恢復與防回歸

2026-11-13。使用者要求繼續其他不需要Pi的測試、不重跑長測，並確保剛才的錯誤不再漏檢。本輪只新增測試與私有測試控制器的驗收閘門，**production、共享runtime、COM3／COM4、原長測及封存證據不變**。

## 實際結果

**8個新增故障情境＋35個固定槽號回歸，共43項通過，0失敗／0跳過，9.63秒**：[最終log](final-04/integration.log)、[JUnit](final-04/integration.xml)、[機器驗收](final-04/suite-assessment.json)、[整輪與清理](final-04/result.json)。另有 **16個測試控制器／反例單測通過**：[log](controller-final-coverage.log)、[JUnit](controller-final.xml)。重複執行次數不疊加成新測試數。

| 新情境 | 真實故障／判定 | 證據 |
|---|---|---|
| DB逾時 | 私有投影表鎖住，接收端實際拋`TimeoutError`並發`retryable/database`；本地原ID/hash保留。完整回滾後receipt／投影=0／0，解鎖補傳後1／1、pending0 | [結果與實際回覆](final-04/database-timeout.json) |
| DB交易程序被終止 | 等自有backend確實阻塞在投影SELECT，再`pg_terminate_backend`該PID；未commit的receipt／投影皆0，原樣本重送後1／1，本地在沒有application ACK時仍保留 | [結果](final-04/backend-termination.json)。不是終止共享DB、OS斷電或PITR |
| 中央已有兩筆投影 | 只在私有DB故意製造同ID兩列，接收端拒絕回committed、本地轉quarantine並保留完整payload，中央1 receipt／2列原證據不覆寫、不悄悄刪除 | [結果](final-04/duplicate-projection.json)；測試通過表示正確拒收，不表示損壞資料被驗收 |
| 兩個接收端同時處理 | 兩個live Receiver實例，各自MQTT client／event loop及DB connection均處理同筆，中央仍1 receipt／1投影、local audit1／pending0 | [結果](final-04/two-live-receivers.json)。實例位於同一私有worker，不是跨主機HA驗收 |
| 外置generation換代＋舊ACK回放 | 捕捉真commit後遺失的ACK，receiver換generation重新啟動／握手後，經真MQTT回放舊ACK不能刪pending；新session重送同ID仍中央1列、pending0 | [結果](final-04/generation-old-ack.json)。這是舊session／generation合併拒絕情境，不單獨隔離generation條件，也不是DB PITR |
| v2 SQLite空間滿 | 私有檔案限64KiB，真實命中`SQLITE_FULL`；此前已commit的2筆、ID/hash／sequence／latest timestamp全保留，重開integrity=ok，檔案61,440bytes | [結果](final-04/sqlite-full.json)、[關閉後DB副本](final-04/sqlite-full-outbox.db)。未填滿主機磁碟／SD |
| ACK後audit容量滿 | audit cap=1，第一筆commit ACK後保留索引；第二筆拒絕接納，sequence仍1、原audit未覆寫 | [結果](final-04/audit-capacity.json) |
| 不受信任client憑證 | 同一mTLS listener先以合法client正向連線，再以rogue CA簽client；broker明列certificate verify failed，無MQTT session、原pending1／中央0 | [結果](final-04/untrusted-mtls.json)、[TLS broker log](final-04/tls-broker.log)、[公憑證metadata](final-04/certificate-metadata.json) |

## 防止槽號誤標與測試假通過再漏檢

1. `verify_private.py --suite faults`明確只選本輪8案與原35個邊界案，不收長測。`baseline`保留原檔案集合，兩個入口都必須通過35案檢查。
2. [固定完整catalog](../../services/edge-receiver/tools/boundary-cases.json)鎖定35個**模組＋完整參數化案名**，包含原5109前15ms／零點／後15ms、ULP、真漏槽／重複、終界及虛擬接線。不是只比數量：缺案、跳過、同群組替代、重複案名湊數、未知案例均拒絕。
3. 即使pytest exit0，也必須有完整JUnit及真DB逾時證據：`TimeoutError`、`retryable/database`、故障後0／0、恢復1／1／pending0；只有sender等待ACK逾時不能當DB逾時通過。
4. [16案控制器單測](../../services/edge-receiver/tests/test_private_suite.py)含上述反例。新增3個控制器函式覆蓋率為100%／88.89%／100%，見[範圍](new-controller-functions-coverage.json)。本輪私有43案是**定點路徑覆蓋**，不是全系統覆蓋率；log的45%分母含大量本輪沒跑的模組，不能與昨日完整回歸90.81%直接相比，也沒有重測／改寫昨日259項結果。

這些是固定回歸與失敗閘門，不能宣稱任何未來改動都不會產生新錯誤；會讓已知15ms邊界與本輪假通過情況無法在這個補測入口被略過。

## 先前run與複核

- [run-01](run-01/result.json)8案原始exit0保留，但DBtimeout初版可能先發sender ACK timeout，放鎖後DB仍成功，**不作真DB逾時已驗到的依據**。獨立Python／code review提出同一缺口，已加接收端真例外及回覆觀察；backend輪詢另補`pg_stat_clear_snapshot()`與實際投影SELECT確認。
- [run-02](run-02/result.json)收緊後8案通過；[final-03](final-03/result.json)加入35案固定回歸及14個控制器反例。Python複核再重現「同群組用重複參數名遮掉另一案」仍可假PASS，遂改完整35案identity catalog並加2個反例；final-04為最終43案／16防呆。
- 初次coverage以檔案路徑當module未收資料，原warning log保留；後續改正模組名稱後另存有效coverage，不將無資料結果當覆蓋率。
- [獨立複核](reviews.md)最終均Approve。原fixture XML由已保存的真8案與35案報告取出，不從待驗controller常數生成，避免同源自證。

## 隔離與接續

[控制器](../../services/edge-receiver/tools/verify_private.py)只建立自有network-none anchor、demo broker、獨立mTLS broker、TimescaleDB與worker，共5容器；無hostport、worker無Docker socket／serial device。故障測試再核namespace、僅lo及固定loopback私有DSN才執行SQL鎖／終止自有backend。一次性PKI結束清除，只留公憑證metadata、命令與log。各run自有容器皆收回，來源凍結／hash及清理收據保留。

重現：`python3 services/edge-receiver/tools/verify_private.py --suite faults --output <全新目錄>`。既有共享v1未切換、新production沒有改動；原24h仍INTERRUPTED，沒有開新長測。Pi／ADTEK／4G／實體電源／中央PITR、正式憑證撤銷輪替、多設備scheduler及完整manifest對帳依然另案。

## 封存核對

[保護檢查](protection-check.json)逐檔確認原770、v2修復752、積壓384、實際接收321、事故18、單筆7與槽號修復20檔封存皆不變；production 17檔、原frozen 17檔、verifier依賴3檔及本輪最終測試來源70檔相符。[Windows frozen](windows-frozen-check.json)另核對17檔；共享17容器ID不變、臨時PKI無殘留。文件[連結檢查](link-check.json)、[結果](status.json)與本輪[SHA256清單](artifact-sha256.json)另存，清單不雜湊自身。
