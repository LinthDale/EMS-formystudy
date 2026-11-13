# 首輪完整流程測試：FAIL，原結果保留

12項中9 passed／3 failed，見result.json、pytest.log與JUnit。兩項時鐘測試主流程成功後，在測試收尾呼叫不存在的Poller.close而失敗；不受信server CA實際OpenSSL code19（self-signed certificate in chain），初版期待20。不得把本輪改成PASS。

兩個自有容器已成功清理，無共享服務／COM／主機時鐘變更。初版只存來源hash，不追稱完整來源快照。修正測試工具後另開[field-security-02](../field-security-02/README.md)，結果與限制分開記錄。
