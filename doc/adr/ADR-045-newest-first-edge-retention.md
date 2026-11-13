# ADR-045：量測容量滿時淘汰最舊資料，保留最新讀值

## Status

Accepted，2026-11-13；已實作及私有驗證，未切共享部署。使用者明確要求「新資料比舊資料重要，應該要從最舊資料開始覆寫」。修改 [PRD-0021](../prd/PRD-0021-multi-device-edge-reliability.md) FR-2105／2106／2109／2113，部分取代 [ADR-030](ADR-030-edge-durable-receipts.md)／[ADR-043](ADR-043-opt-in-committed-telemetry.md) 的滿容量拒收策略；[測試結果](../../output/newest-first-retention-20261113/README.md)，未切換共享部署或重跑長測。

## Context

舊 v2 同時累積 pending／quarantine 與 ACK 後 audit，達任一 cap 拒收新讀值；audit 無回收，甚至中央已全部收到仍會卡住。使用者選擇最新監控優先，接受超出本地容量時放棄最舊量測的補傳機會。

## Decision

1. 新策略作用於 opt-in wire protocol 2 的本地量測資料庫，依持久化 `capture_seq` 由舊至新淘汰，包含未送／隔離資料；不是依 ACK 抵達順序或容易跳動的牆鐘。queue cap 取最舊queue需騰出空間的截止seq，audit cap 取最舊audit截止seq，刪該截止之前的本地queue／audit前綴。byte budget 壓力重試1／2／4…個最舊audit前綴、最多全體，直到新寫入可提交；不承諾每次恰好最少淘汰筆數。未超容量不主動刪樣本。
2. 先完整驗證新樣本；淘汰舊列、新 UUID/hash/seq/window、容量摘要與新樣本在同一 SQLite DELETE/EXTRA 交易提交。若新樣本無法持久化，所有本次淘汰與序號前進回滾；不得先刪舊資料再另交易寫新資料。SQLite FULL 重試整筆交易，只有新寫入成功才提交淘汰。
3. local retirement 與 central committed 分開：容量淘汰不是 ACK、不提高已送達／已核對數。單筆有界 metadata 摘要累積被淘汰 audit 數、未確認送達副本數、已確認／隔離分類與最近淘汰序號範圍及樣本身份；範圍是 span、不是每個序號都缺筆的宣稱。摘要長度有界，不承諾完整逐筆歷史 ledger；EMS gap UI／sealed manifest 仍待實作。已 ACK audit 被回收只降低本地核對歷史，不表示中央遺失。log 明示 capacity_eviction。
4. 已傳送但正等待 ACK 的最舊樣本也可淘汰；遲到 ACK／rejected 只能操作原 UUID/hash。原列已淘汰時返回未解析，不刪新列、不重建舊列、不假記 committed。既有 mTLS/session/generation/batch 驗證保持。
5. SQLite 本地 schema 升至 3（wire 仍為 2），舊版拒開；新版從完整 schema 2 同交易補必要 metadata 並升版，身份／既有資料不變。兩個非唯一加速索引另用交易建立，僅SQLITE_FULL時回滾該索引交易、記retention_indexes_deferred並沿掃描查詢運作；之後重啟可重試，不承諾缺索引時效能。必要metadata也無空間時安全失敗保留舊檔，不為升版先刪資料。部署前停止舊程序並備份；回滾須保留 schema3，禁止降版抹掉容量缺口。原 v1→新版離線轉換仍要求全部 pending 可容納，不因新策略悄悄裁掉來源。
6. 清理無 audit 引用的 window，防止窗口表獨立無界增長。總 page budget、queue cap、audit cap 維持既有配置；此政策不將無限離線變成無損。真正主機磁碟滿、I/O／卡片故障或新樣本大於整個可用 budget，仍可能寫入失敗，必須回滾並明示錯誤。
7. 不改中央 receipt 去重／接受窗、MQTT schema／topic、OT 寫權或 PRD-0022 控制稽核。中央歷史保留及 PRD-0025 受保護控制帳本不在本次全表淘汰範圍。7 天完整保留僅在核定容量內成立；超額明示本地淘汰。

## Alternatives

- 保留舊資料拒新：與本次使用者優先順序不符。
- 先 DELETE commit 再 INSERT：寫新失敗仍失去舊資料，拒採。
- audit 永不清理或只加大 cap：只是延後卡死。
- 原地重用 sample_id／seq 改量測：會破壞 hash 與中央去重，拒採。

## Consequences / Validation

最新量測可持續接納；超額最舊資料可能再也無法補傳。本地未確認不等於中央確實缺失，ACK 遺失時尤其如此。只保留摘要時，完整歷史核對範圍縮短且需明示。

TDD：queue/audit cap、quarantine、SQLite 真 FULL 循環、最舊順序、時間跳動、舊 ACK、反向執行緒競態、寫新失敗回滾、重啟、schema2升版／舊版拒開、windows 有界、離線轉換不得裁切；再跑私有 MQTT／PostgreSQL 與原35槽號案例。不得更新已封存舊測試結果。

2026-11-13補證：[程序／儲存與v2憑證短測](../../output/no-pi-resilience-20261113/README.md)新增9案＋原35槽號共44通過；真SIGKILL三個循環交易邊界、BUSY／READONLY與旋轉期間backup皆符合本ADR，三個server TLS故障後原ID合法恢復中央一次。只增測試／驗收閘門，production／決策／部署不變；主機掉電／SD／Pi及正式容量性能仍待驗。

2026-11-13啟動防護bugfix與補證：[lifecycle紀錄](../../output/no-pi-lifecycle-20261113/README.md)42定點與393相鄰通過／12專用case跳過。既有zero／empty SQLite不可誤當新stream自動建庫；以排他新建區分後，既有先驗schema，只有精確READONLY_ROLLBACK允許rw原生hotjournal復原。這是保持「損壞不清空假恢復」與既有crash耐久的相容修正，wire2／schema3及最新優先政策不變。原RED與測試控制器host檔案邊界修正保留，未切共享或重跑長測。

### 2026-11-13 既有完整性契約bugfix

容量政策與schema3/wire2不變；[PRD-0021 §15.11](../prd/PRD-0021-multi-device-edge-reliability.md)／[本輪證據](../../output/no-pi-integrity-20261113/README.md)修邏輯損壞漏檢、live counter回退可重用seq、audit缺失ACK誤刪、pending讀取跨快照及retention overflow。enqueue淘汰前核現存audit高水位，ACK同交易再驗，pending短read snapshot。新增optional audit_time與原audit_sequence/audit_window同FULL-deferred交易，scan fallback仍正確；不是新增必備schema索引或降低容量安全。拒錯保留原檔／資料，不自動清庫／重設或造audit。私有66定點、500相鄰／12skip、91.36%，正式Pi／600k耗時未驗，沒有部署或長測重跑。
