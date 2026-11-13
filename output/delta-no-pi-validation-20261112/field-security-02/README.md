# 時鐘與真TLS完整流程補驗：12/12 PASS

2026-11-12 15:20:30–15:20:49（Asia/Taipei）。[最終結果](result.json)、[逐案證據](cases.json)、[JUnit](junit.xml)、[原始測試輸出](pytest.log)、[broker日誌](broker.log)。這是隔離Linux／Docker測試，不是Pi、4G、真機或中央DB ACK驗收。

## 時鐘：正式edge完整流程，2案／11個受控階段

使用正式edge.run／ClockGuard／Poller／parser／Outbox／Publisher，加真實Modbus TCP simulator、SQLite及TLS broker。只在測試子類輸入指定UTC與步進節拍，並控制一個sender permit；沒有改主機時間、NTP服務、production程式或COM。測試節拍0.01秒只縮短階段等待，不作採樣效能證據。

- 未同步冷啟動、同步旗標消失、時間回撥、時間重複、2025年前時間：共5個拒收階段，每次均0次Modbus poll、0次SQLite commit。
- 同步恢復及時間恢復後正常取得3筆；在時鐘失同步時仍把既有pending補送，原payload／時間不變，最終3筆接收、pending0。
- 兩次edge啟動：第一次commit並送出後，第二次由同一SQLite讀取latest timestamp；較舊時間被拒收、恢復較新時間後成功。共2筆接收、pending0。

共11階段：5個有效樣本、6個拒收，與完整payload集合逐筆相符。時間值是注入fixture，不是逆變器內部時鐘。本測試不能證明RTC漂移／NTP精度、同步旗標內容真偽／時效或任意時間大幅向前跳的辨識能力。

## 真TLS／認證：10案

| 案例 | 實際結果 |
|---|---|
| 正確CA＋帳密 | 原payload收到一次、pending0 |
| 不受信CA | OpenSSL verify code19、未連線、pending1 |
| server名稱不符 | verify code64、未連線、pending1 |
| 已過期server憑證 | verify code10、未連線、pending1 |
| 錯誤密碼／未提供認證 | 兩案均收到Not authorized、pending1 |
| 正確mTLS、無帳密 | 原payload收到一次、pending0 |
| 缺client cert／不受信client cert | 兩案均被斷線、pending1 |
| TLS傳輸中斷、同Publisher自動重連 | 1.0274秒重連，原payload送出一次、pending0 |

7個拒絕案例均沒有刪除原pending，沒有接收到量測。憑證指紋／效期見[公開metadata](certificate-metadata.json)；私鑰、CA簽署key及隨機測試密碼僅在私有tmp目錄使用，未保存於專案。

## 隔離、清理與可重現性

broker採network=none、無host port，只聽私有loopback；worker加入該namespace，先比對FIELD_QA_NETNS才允許測試。兩個映像使用當時已快取的immutable image ID，見result.json。測試broker的1883埠實際設定TLS，以重用既有Gate的固定上游；這不是共用EMS的1883，也沒有降級為plaintext。這次ACL只服務隔離測試，不是正式gateway/device身分綁定驗收。

測試結束兩個自有容器均已移除，無log／cleanup錯誤；共享17個EMS容器與COM3／COM4長測持續運作。正式1秒／1小時先前已3600/3600通過；5秒／24小時仍進行中，本次不能代替其結果。

重現（WSL權威checkout）：

```bash
python3 services/delta/tools/bench_field_checks.py --output "$PWD/output/delta-no-pi-validation-20261112/field-security-new"
```

輸出目錄必須全新，需本機Docker、OpenSSL3、已建好的ems-delta-test及快取eclipse-mosquitto:2。工具不拉映像、不使用既有credentials、無共享broker或Docker socket掛入worker。來源凍結在source，含Gate與pytest設定，SHA256見source-sha256.json。

## 首輪失敗與獨立審查

field-security-01原9 passed／3 failed保留。兩個時鐘案例主要流程達成但測試收尾誤呼叫不存在的Poller.close；不受信CA實測為code19而初版期待20（server送出自簽CA chain）。修正測試工具後另開本run，沒有改production或放寬「拒絕且保留pending」標準。首輪只保存source hash，沒有完整來源副本，不追稱完整凍結。

審查另發現收集log失敗會跳過容器移除；先用TimeoutExpired及檔案寫入錯誤重現，再修正為日誌／逐容器獨立清理，log錯誤使最終FAIL。新8項純判定／故障測試通過；code與Python審查Approve。完整回歸[191 passed／12 skipped、production coverage96.06%](../unit-regression-field-checks.txt)：12項只因一般回歸沒有私有namespace而跳過，它們已在本run實跑12/12，不能把skip當通過。

中央receipt／去重／對帳仍未實作，第9關v1 FAIL不變；多設備bus owner／sensor profile、日照與貼片溫度入庫／顯示仍待實作與型號確認。這些未以本次TLS或時鐘測試宣稱可用。

安全唯讀複核亦無阻擋項，檢查namespace、credential保存與自有清理證據。namespace guard防誤用，不防操作人刻意偽造環境；本工具沒有SIGKILL／Docker daemon故障後保證回收的能力。本次實際cleanup2/2成功，詳[審查紀錄](../field-checks-tool-regression/review.md)。
