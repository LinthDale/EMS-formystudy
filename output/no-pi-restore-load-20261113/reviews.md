# 剩餘三項短測：獨立複核

Architect：ADR-048符合FR-2107，單stream用capture_seq max/min成功1:1交替合理；預設pending最舊、原payload／ACK／schema保持。揭露程序重啟輪次不持久、最新候選非每筆固定SLA、3筆延遲非percentile、200輸入為同一樣本重送及邏輯restore非WAL PITR。已核run-final38、997＋6總帳與restore不可補範圍，Approve。

Python reviewer：驗證公平3RED→GREEN與失ACK不換輪，真pg_dump／newDB restore與完整receipt／投影一致、source oracle未改，C同原ID補回，B只dump＋local不可補。檢查真DB阻塞／queue64及無假ACK、1秒production節奏。最後核run-final38／18.90秒、regression419／12skip／33.49秒／91.04%、各5清理與source不變，無CRITICAL/HIGH，Approve。

Code reviewer：確認固定owneddatabase控制與host檔案邊界、原認證與成功輪次安全。指出run-02將恢復4封計入burst形成204，原gate正確false；已凍結burst200，恢復另列，不放寬gate。補restore完整值核對後驗run-final3proof全true、1003總帳、各5清理，CRITICAL0／HIGH0／MEDIUM0／LOW0，Approve；regression由主代理另核。

Security reviewer：提出HIGH——docker cp會保留容器symlink，host普通read_bytes可外檔讀／FIFO阻塞／無界讀；已改private新目錄＋NOFOLLOW／NONBLOCK FD、regular、16MiB雙上限、hash後atomicbinary發布。新增3反例含Path.read_bytes spy，避免hash失敗才被當綠；複核HIGH關閉、無剩餘CRITICAL/HIGH，固定op／ownedCID／新庫限制不變。沒有要求或執行共享DB／COM／長測。

全部review唯讀、不改檔或操作共享服務。最終以run-final及regression-final來源一致結果為準，run-01／02失敗及初版不安全工具快照保留，不回寫PASS。
