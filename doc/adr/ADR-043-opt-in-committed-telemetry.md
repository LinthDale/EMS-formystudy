# ADR-043：以獨立 v2 路徑修復入庫前刪除與重送重複

## Status

2026-11-13：[ADR-045](ADR-045-newest-first-edge-retention.md)部分取代Decision3的容量條款：使用者核定最新量測優先，schema3本地queue／audit滿淘汰最舊，含未送／quarantine，與新資料同交易；淘汰不記committed。wire仍2、中央receipt與session／mTLS不變。以下滿cap停採與audit永不清理是歷史版本。

Accepted for implementation，2026-11-12；使用者要求「缺口修復」。承接 [PRD-0021](../prd/PRD-0021-multi-device-edge-reliability.md) FR-2104／2106／2111 與 [ADR-030](ADR-030-edge-durable-receipts.md)。僅可靠送達子集；正式部署、Pi 與完整 PRD 驗收另列。

## Context

[實際接收程式反例](../../output/no-pi-ingest-20261112/README.md)證明 broker PUBACK 不等於 DB commit，且相同樣本重送會多列。只調 Mosquitto persistence／Telegraf session 或加 timestamp 去重，無法提供既有 PRD 的逐筆提交責任；不同合法樣本也可能同 timestamp。

## Decision

1. 以明示 `delivery.protocol=2` 啟用，不修改既有 v1 topic、共享 runtime 或原 24h 凍結來源。新 SQLite 專用檔案、schema_version=2；v1/v2 相互拒開。採樣器仍唯讀，兩執行緒維持。
2. 使用 PRD-0021 §8 samples／acks／session topics。首階段每批 1 筆、最多 1 批 inflight、最多每秒 2 批；保留 32 筆／64KiB 協定上限但不宣稱 20 samples/s。未知欄位、重複 JSON key、bool-as-int、非有限值、retained 一律拒絕。canonical JSON：UTF-8、ASCII escaping、sorted keys、無空白；四欄統一 float，負零轉 0.0，其餘整數嚴格 int；hash 排除 payload_hash。
3. 新 outbox 同一 SQLite DELETE/EXTRA 交易持久化 sample UUID、gateway/device、stream、seq、window、revision、profile、原始時間、hash。stream／revision／profile 由部署者配置，queue 綁定不可重用；window 在該樣本寫入前同交易持久化。PUBACK 不刪。ACK 與 reconnect／disconnect 共用 lock；先驗完整回覆、當前 challenge／generation／batch／pending ID/hash，再同交易保留 audit 身分索引並刪 payload。rejected 轉 quarantine，仍計入 queue cap。audit 不自動清除，達 cap 停新採樣；本階段未完成 sealed manifests 與 7 天對帳。
4. 新 receiver 僅訂閱 v2，權威靜態登錄 gateway→device→stream／revision／profile 與採樣生效時間範圍。普通 PostgreSQL receipt 表唯一 gateway/sample 及 gateway/device/stream/seq；量測增 nullable gateway/sample 欄位與索引，舊 v1 投影不變。READ COMMITTED 交易先建立 receipt、鎖定 receipt，再核對量測：0 列插入／修復、1 列逐欄核對、>1 或異值 conflict。commit 成功返回後才發布 committed ACK；DB 失敗、commit 結果不明或 ACK 遺失都靠原 ID 重送。
5. DB 核實 fsync=on、每連線 synchronous_commit=on；接收窗取 DB UTC，90 天前至 2 分鐘後。receipt 與 snapshot 暫不自動 purge，避免未實作清理造成重放洞；需監控中央磁碟。migration 冪等、只在私有 DB 驗證，不對共享 DB 自動執行。
6. 每次 MQTT reconnect 清空 session／batch，先 subscribe SUBACK 再用新 challenge 握手。generation 來自 DB 外的必填 UUID 檔案，不自動建立／fallback；PITR 前須隔離 ACK、換 generation 並強制重連。正常 receiver 重啟不重建樣本 ID。
7. field 強制 mTLS／broker principal ACL，只有 receiver 可發布 ACK／session response；client 本身不假稱能辨識 broker principal。demo v2 必須核對指定 network-none namespace 且僅 lo，不允許接既有匿名共享 broker。機密從 env 取得，不輸出 DSN／原始錯誤。

維護入口：wire/store/sender 在 `services/delta/delta_device/reliable_*.py`；receiver 在 `services/edge-receiver/edge_receiver/`；schema migration 019；部署設定及 ACL 範本在 receiver deploy，測試對應 unit／private integration。Owner EMS；無新 UI、品牌、素材、RWD，這些項目不適用。

## Consequences

可用實際 MQTT／PostgreSQL 故障注入驗證兩個缺口及假 ACK／並行 repair；v1 歷史 FAIL 保留，已被 v1 刪除的樣本不憑空恢復。切換需停止目標舊 sender、保留舊 queue 備份並轉換仍 pending 的列；不回退成 PUBACK 刪除 v2 queue。

此階段不是多設備 scheduler、sealed manifest／每日對帳、heartbeat UI、7 天容量／20/s 補傳或 Pi／4G／實體掉電驗收。新的 opt-in 路徑測過後才能標子集已實作，不能將全 PRD-0021 改成 Implemented；共享 v1 長測依舊是 v1。
