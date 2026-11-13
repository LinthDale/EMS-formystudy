# 記憶體串口遲到回覆重現（非實體證據）

本資料夾是 **記憶體串口替身測試**，不是 USB、RS485、COM3／COM4 或 Windows 串口驅動的實體驗證，也不是第 5 關實體驗收通過紀錄。

## 實際結果

- 使用正式 `Poller.read` 與 pymodbus 3.6.9、pyserial 3.5。
- 在 Linux 隔離容器中將 Poller 的 platform 判斷設為 `win32`，以使用 `strict=False`；這不代表執行於 Windows。
- `serial.Serial` 與 `serial.serial_for_url` 全部換成配對記憶體緩衝區；只有 `MEMORY_SLAVE`／`MEMORY_MASTER` 端點，沒有真正開啟串口。
- 第一筆請求不回覆，讀取失敗；從站收到第二筆請求後才送出第一筆的舊值 2300。
- 第二筆讀取接受舊值 2300，而不是其應有的新值 2400。工具正確記錄 `late_order_verified: true`、`passed: false`。
- 讀取快速返回後，工具停止從站工作執行緒，因此預定再隔 100 ms 發出的新值 2400 尚未送出。這不影響已觀察到的舊回覆被接受事件。
- 兩端記憶體串口已關閉，沒有留下新的工作執行緒。

`stdout.json` 是本腳本實際執行的完整 stdout；`stderr.txt` 為空，`exit-code.txt` 為 0。**Exit 0 / `finding_reproduced: true` 表示成功重現問題，不代表通訊驗收通過。**

## 重跑

在 Windows PowerShell 執行下列單行命令。沿用現有本機 `ems-delta-test` image，不拉取或啟動任何服務。容器沒有網路、沒有硬體掛載，repo 與容器檔案系統皆唯讀。

```powershell
wsl -d Ubuntu -- docker run --rm --network none --read-only -e PYTHONDONTWRITEBYTECODE=1 -v /home/dalelin/synaiq/EMS:/repo:ro -w /repo/services/delta ems-delta-test python /repo/output/delta-no-pi-validation-20261112/memory-late-reply-reproduction/reproduce.py
```

腳本預設由自身位置定位 repo；也可用 `--repo` 明確指定。它執行指定 repo 當下的程式，並在 stdout 記錄 `bench_frames.py`、`poller.py` 與自身的 SHA-256。當後續實作修正此問題，腳本可能回傳非零；應對照來源 hash 與實際欄位判讀，不可把不同版本結果混用。

`source/` 保留這次執行所對應的兩個來源檔快照；`image-inspect.json` 記錄本次隔離容器 image 身分，`artifact-sha256.json` 記錄交付檔案的 hash。

此證據僅證明該版本軟體在明確控制的記憶體位元組時序下會接受跨交易遲到回覆；不證明現場實體連線的發生頻率或硬體測試結果。
