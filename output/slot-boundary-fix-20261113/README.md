# 槽號邊界修正與定點補測

2026-11-13。依使用者要求只修槽號誤標並補該邊界；**沒有重跑長測、沒有開COM、沒有啟動MQTT／DB或修改production採集器**。原24h仍中斷，原帳本及凍結來源不變。

## 修正

唯一程式修改是 [bench_run.py](../../services/delta/tools/bench_run.py)：原先用實際喚醒時間的`elapsed // interval`標槽，下一槽提早15ms喚醒會歸前槽。現在觀察**真實scheduler回傳的原定deadline**，以該排程位置決定slot；原deadline原值回傳，不改取樣週期／睡眠／catch-up政策。`start_delay`改記實際時間減原定deadline，早到為負數，不再顯示成接近5秒的正延遲；attempt另記scheduled_monotonic供追溯。

只對排程deadline做浮點格點驗證（4 ULP的表示誤差），不對實際喚醒時間加15ms容差或四捨五入。因此真正跳過的slot仍缺、同deadline重複仍重複；scheduled slot或actual時間任一達終界即關閉，不因提早最後一次喚醒多採。

## 結果

- **66項定點與相鄰判定測試通過，0失敗／0跳過，0.10秒**：[log](targeted.log)、[JUnit](targeted.xml)。只選新邊界測試及既有ledger／soak純判定，不跑整個系統回歸／長測。
- 新 [test_bench_slot_boundary.py](../../services/delta/tests/test_bench_slot_boundary.py)共35案：原5109邊界前15ms／剛好／後15ms、1／5／10／15／30秒週期的一個ULP前後、真跳槽、真重複、actual／scheduled結束邊界、off-grid及無效輸入，以及2個run_bench虛擬時間接線案。串口、simulator、poller、outbox、timer皆替身，沒有真的採樣或網路服務。
- 同35案另量測新增`slot_observation`函式行覆蓋 **84.62%**：[範圍與缺行](new-function-coverage.json)、[原coverage](boundary-coverage.json)。這不是整個bench或production的覆蓋率，沒有重測或改寫昨日259項數字。
- [原五筆邊界replay](original-boundary-replay.json)：原始`5107,5108,5108,5110,5111`在新的排程標號為 **5107,5108,5109,5110,5111**；該筆延遲正確記成 **−0.015秒**。只回放已保存的觀察時間與原scheduler函式，原timestamp／數值／帳本不改，沒有重新讀設備。

## 複核與保留

Python reviewer與code reviewer均Approve，未發現剩餘必修問題；確認deadline回傳值不變、真skip／duplicate不被掩蓋、early final wake及late actual end都關窗。Python reviewer唯讀核對66項JUnit，Bandit -ll兩檔無中高問題。[複核收據](reviews.md)、[新來源hash](source-sha256.json)、[修改前來源](bench_run.before.py.txt)另存。

[保護檢查](protection-check.json)核對原封存manifest、原runtime凍結檔與verifier依賴。只更動權威repo工具與新測試；不替換舊run的source、舊slot欄位或原嚴格FAIL，不把24h改成PASS。未重啟任何共享服務。
