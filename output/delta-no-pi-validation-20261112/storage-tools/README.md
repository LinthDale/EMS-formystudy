# 程序崩潰與容量邊界工具

對應原計畫第7／8關，只有實際run完成才能標PASS。

bench_storage.py crash：私有outbox、COM3真實sim與COM4正式edge子程序、私有loopback Gate阻上傳。每輪3筆正式SQLite commit後，在第4筆特定故障點開啟INSERT但未提交，parent只強制停止自身child；保存DB及若存在的journal sidecars，重新開啟確認所有已提交集合完整、未提交列不出現。10輪後以新子程序正式Publisher／drain補送，逐筆核對DB與EMS records API。這不是主機斷電，也未證明特定hot-journal header或回滾路徑。停機與未提交槽列為故障缺測，不補造。

bench_storage.py capacity：全新私有SQLite以小row limit驗證拒新不刪舊；以PRAGMA max_page_count觸發真SQLITE_FULL，確認pending不變，解除後再新增；另複製私有DB後毀損header，確認拒啟動且毀損副本bytes不被重建覆寫。此為SQLite page-limit故障注入，不是填滿OS磁碟、SD磨耗或Pi斷電證據。

安全與清理：worker/replay僅允許live parent的run manifest／ID、同run私有outbox、demo固定ID、COM4及loopback gate；不接受任意現有設定。marker先fsync臨時檔再atomic replace，避免kill到半份標記。每個自有child／Gate／log獨立嘗試清理，失敗將結果改為false。共享broker／容器維持運行；DB非同步入庫採30秒有界觀察，沒有用PUBACK冒充DB commit。

單元反例先RED再GREEN；目前5項pure storage測試通過，code／Python審查問題已修復。最終實測結果見各run及上一層README，source保留執行來源。

## 已知關卡順序與剩餘範圍

第7／8關執行前維持第6關測量窗，不讓第二個工具同時占用COM3/COM4。第9關所需的中央committed ACK／去重是PRD-0021尚未實作功能；本次驗證授權不把它當成已完成能力。前面逐筆DB/API核對通過，也不能替代運行時receipt協定。

因此不能以1小時／24小時正常採樣掩蓋第9關缺口。長期運行、UI對歷史回補的新鮮度顯示、Pi／4G及兩款真機profile均需保持獨立狀態，不能把本台架補送結果升格現場可靠性驗收。

2026-11-12最終補充：儲存工具新增Windows venv redirector反例，改直接管理真實Python PID並保留venv依賴。storage pure tests共6項；整體164 passed／production line coverage96.06%。第6關80/80補送與DB/API相符、第7關10次強殺30/30恢復與DB/API一致、第8關私有容量故障通過，詳上一層逐關紀錄。第9關中央DB ACK仍待實作，1h／24h未跑。
