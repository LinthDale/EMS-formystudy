# 正式長測序列（11/13稽核：24h已中斷）

**2026-11-13更新**：[事故對帳](../../soak-interruption-audit-20261113/README.md)。11/12 22:29:14起Windows更新安排重開機，原三程序已不存在；`status.json`最後22:28:46的RUNNING是遺留值，保留作原始證據。1h保持PASS；24h只取得5,512筆、約7h39m，DB/API逐筆相符但未滿24h，另有槽號邊界記帳異常，不能算PASS。未啟動重跑；以下為原始執行說明。

2026-11-12 13:49:42（Asia/Taipei）啟動；實際採樣窗約13:49:45開始。狀態以 [status.json](status.json) 為準，不能因本文件存在宣稱通過。

1. 1秒採樣、完整3600秒、3600槽。
2. 第一階段通過後才啟動5秒採樣、完整86400秒、17280槽。

各階段接受條件：有效採集率≥99.9%、所有缺口分類、錯值／golden錯誤／重複／額外槽為0、SQLite提交數等於有效樣本、pending0、所有已提交樣本逐筆DB/API相符；正式採樣窗結束事件必須達全時長。原bench嚴格100%判定仍保留，不覆寫成PASS；soak-result另依本計畫99.9%判定。失敗則不開始下一階段。

工具先凍結production與台架來源至本目錄runtime／controller-source，保留SHA256；每次DB/API核對前檢查verifier及依賴未變。私有SQLite在Windows本機寫入，階段結束後才將完整證據複製到此處。每30秒保存CPU累計秒數、RSS／private bytes、SQLite檔大小與磁碟剩餘容量；結果是Windows加帳本的量測，不能推估Pi記憶體需求。

controller PID4564，原生bench與simulator納入Windows Job Object；父程序先退出時也能在關閉Job後回收孫程序，獨立證據見 [job-probe-01/result.json](../job-probe-01/result.json)。任務deadline為每段採樣時間加120秒、磁碟保留至少1GiB；不停止共享容器。

目前保持電腦開機、USB連接及既有EMS服務。若確實需要停止，只建立`C:/Users/User/AppData/Local/Temp/ems-no-pi-20261112/soak-sequence-01/STOP.txt`；工具下一輪檢查後回收自己的程序，保存STOPPED／FAILED狀態，不算通過。勿重複啟動另一套COM3／COM4測試。

重現命令：`python services/delta/tools/bench_soak.py --config output/delta-rtu-bench-20261112/windows-bench.json --local-root C:/Temp/ems-soak-new --archive-root output/delta-no-pi-validation-20261112/soak-new --mode full`。需Windows原生Python及既有台架環境，兩個目錄必須全新且互不包含。虛擬環境redirector PID與實際解譯器PID不同，本次以base Python搭配固定venv site-packages啟動，以便Job正確持有程序。

前置 [soak-smoke-01](../soak-smoke-01/status.json) 只有1秒3槽及5秒3槽，各DB/API3/3，用於驗證程序與階段切換；formal=false，不能抵扣1h／24h。

此為v1正常採集長測；第9關DB receipt／去重反例不因長測成功而解除。Pi／4G／真機未測。進行中的status每30秒變動，未納入靜態證據hash manifest；本輪manifest明示排除整個活動目錄，凍結來源另有source-sha256。
