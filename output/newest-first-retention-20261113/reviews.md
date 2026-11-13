# 最新優先容量策略：獨立複核

使用者明確核定新量測優先，ADR-045取代滿容量拒收條款；以下複核僅本地量測，不涉及中央或控制帳本資料刪除。

- Python reviewer：確認新資料驗證、原子淘汰＋新寫、FULL整交易重試、UUID/hash舊ACK隔離、序號／window／摘要一致及migration防裁切。已核baseline-01 335／12skip／91.07%與兩個真MQTT結果，無剩餘CRITICAL/HIGH。
- Code reviewer：提出HIGH時間尺度反例（wire微秒合法，但本地奈秒metadata超int64導致重啟失敗）。已統一交易前時間範圍，補5拒絕案例與最大有效重啟案例，複核關閉；不把已淘汰ACK假報committed。三個production檔與rollback／migration證據通過。
- Architect：以真正封存舊程式建立接近滿載schema2，重現強制新增兩索引造成升版SQLITE_FULL；原先新版DB降version模擬仍帶新index，漏掉該邊界。真fixture RED保留；修成必要metadata／schema先原子升、非唯一加速index另transaction且FULL時延後，23案GREEN；架構複核Approve。必要metadata若仍無空間會安全失敗、舊檔不刪；無索引效能待驗，文件同步。
- Security reviewer：驗證只在本地量測範圍淘汰、遠端無新增刪除權、schema降版guard、mTLS/session/generation/batch/ID/hash保持、非法輸入先驗及有界摘要；索引延後不移除原有唯一constraint、不放寬安全條件，僅明確FULL可延後、其他錯誤raise。Approve，無新增CRITICAL/HIGH。

Bandit有1個MEDIUM是_retire固定queue／audit常量表名拼接的通用提示；值皆參數化，無外部表名輸入，Python及安全review人工核對非阻擋，不宣稱掃描零MEDIUM。所有reviewer唯讀、不改檔、不操作COM／共享服務／長測。最終baseline-final／faults-final-02結果及清理由主代理核對，不把中途版本的結果當最終碼驗證。
