# 可靠送達缺口修復

2026-11-12，Asia/Taipei。使用者要求修復 [前輪實際接收程式的兩個反例](../no-pi-ingest-20261112/README.md)。依 PRD-0021／ADR-043 實作 opt-in v2，已用真 MQTT／PostgreSQL／mTLS 及正式 TCP 採集程序驗證。**共享 v1 與原 24h 未切換，歷史 FAIL 不改寫**；這是已實作並私有驗證的可靠送達子集，不是完整 PRD 或 Pi field 上線。

## 修復與證據

| 原缺口／測項 | 新 v2 行為與實測 | 證據 |
|---|---|---|
| 接收服務停止，broker 已 ACK／本地已刪而 DB 缺筆 | 現在 **PUBACK 不刪**；先建立 session，再停 receiver、發送取得 broker ACK，本地仍 pending／DB0。producer 關閉重開後沿原 ID/hash，receiver 恢復後 DB1／pending0 | [JUnit](final-07/integration.xml)的 `test_receiver_stopped_after_session_puback_keeps_sample_and_producer_restart_recovers`；[MQTT broker log](final-07/broker.log) |
| 相同樣本重送變 DB2 | 中央receipt與投影同交易。先真 commit、攔掉 application ACK，本地仍pending／DB1；再真 MQTT相同payload重送，仍 DB1；恢復ACK後pending0／audit1 | 同 JUnit 的 `test_commit_then_lost_ack_and_duplicate_publish_recover_with_one_database_row` |
| 並行重送／缺列修復 | 6 個並行 connection 重送同 ID 只留1 receipt／1投影；刪私有投影後6個並行repair也只重建1列。錯值拒絕、不覆寫 | `test_identical_retry_and_parallel_receivers_insert_once`、`test_missing_projection_parallel_repair_inserts_once_and_bad_projection_rejected` |
| ID與資料污染 | 同ID改內容、同stream/seq改ID拒絕；同timestamp不同合法ID各保留1列；hash、gateway、session/generation/batch、retained／duplicate ACK及巨整數等拒絕 | [回歸／整合log](final-07/integration.log)、[判定測試](../../services/delta/tests/test_reliable_delivery.py) |
| DB只寫到一半 | 私有DB CHECK故意拒絕投影，實際發生CheckViolation，receipt及投影皆0；解除故障後原資料可重送commit | `test_partial_database_failure_rolls_back_receipt_and_retries_original`；不是DB實體掉電／中央PITR |
| 真 TCP採集＋程序崩潰 | 正式 simulator→Poller→ClockGuard→edge→v2 queue；receiver停機時累積至少3筆已commit，對edge **SIGKILL（exit −9）**。SQLite integrity正常、完整rich snapshot仍在；重啟sender後原ID／原時間／四欄值逐筆相符，每筆中央1列，pending0 | [獨立expected/actual帳本](final-07/tcp-edge-crash-ledger.json)；未使用COM或Pi |
| 真 mTLS／ACL | gateway憑證可發自有samples（positivecontrol）；**自有ACK／跨gateway samples／session response／跨gateway ACK**四個禁止topic均未送達QA observer，broker明列Denied PUBLISH。合法receiver→gateway committed ACK及DB1／pending0通過 | [獨立TLS broker log](final-07/tls-broker.log)、[ACL](final-07/tls-acl.txt)、[設定](final-07/tls-broker-config.txt)、[公憑證metadata](final-07/certificate-metadata.json) |
| Migration及DB權限 | migration019連續執行兩次、舊API view仍6欄；web_anon不可讀receipts；專用群組角色可commit但不能DELETE量測；synchronous_commit=off角色被啟動檢查拒絕 | [第一次](final-07/migration-1.log)、[第二次](final-07/migration-2.log)、JUnit的migration/least-privilege case |
| v1 queue切換 | 唯讀來源、逐筆核對ILP／snapshot，保留原時間、clock高水位及新ID映射。完整暫存成功才hardlink原子發布全新v2檔；已有目的檔拒覆寫；錯payload無可啟動的半成品 | [轉換測試](../../services/delta/tests/test_reliable_migration.py)、[轉換工具](../../services/delta/delta_device/migrate_delivery.py)。未對原活動queue執行 |

**最終 259 passed／12 skipped，combined production line coverage 90.81%**：[完整log](final-07/integration.log)、[coverage JSON](final-07/receiver-coverage.json)、[命令](final-07/test-command.json)、[整輪結果](final-07/result.json)。coverage包含Delta與新receiver／migration utility，比前輪只量Delta96.06%的分母更大，不能直接比較成退步。receiver本體81%、store96%，整個receiver package約83.8%。12 skip是既有專用時鐘／TLS fixture，本輪未重跑；[前輪獨立12/12證據](../no-pi-takeover-20261112-1600/README.md)保留。

## 實作與契約

- [ADR-043](../../doc/adr/ADR-043-opt-in-committed-telemetry.md)、[PRD-0021 §15.3](../../doc/prd/PRD-0021-multi-device-edge-reliability.md)、[三圖](../../doc/architecture/edge-committed-telemetry.md)、[維護／部署／轉換／回滾](../../services/edge-receiver/README.md)。
- 本地使用獨立schema v2，DELETE/EXTRA及SQLite max_page_count；sample/seq/window/hash同交易持久化。未知表／舊5欄／必要metadata缺失拒開。ACK驗整份回覆及當前身份／session／batch，與reconnect及刪除同lock；audit＋payload刪除同交易。rejected進quarantine不刪、計入cap。
- 中央普通receipt unique gateway/sample及gateway/device/stream/seq；新增nullable edge_gateway_id/edge_sample_id投影欄，row lock後重查0／1／>1，commit返回成功才ACK。sample timestamp取DB UTC90天／+120秒窗，strict canonical schema、hash重算、權威stream/revision/profile／生效時間；舊Telegraf不收v2，不雙寫。
- field強制mTLS／principal ACL；generation必填DB外UUID檔。demo v2只准明示network-none且僅lo，拒接共享匿名broker。私有驗證用兩個**不同broker process**，避免anonymous listener旁路TLS topic plane。沒有新REST或OT控制。

## RED、原失敗與複核修正

1. [本地RED](unit-red.log)、[sender RED](sender-red.log)、[receiver RED](receiver-red.log)、[轉換RED](migration-red.log)先保存，再實作通過。
2. [db-01](db-01/result.json)保留FAIL：首次6並行重送時，指定PK的ON CONFLICT仍可能先命中另一stream/seq unique索引；改成所有unique衝突收斂後，再鎖／查原receipt。另一case原測試把整數240重算hash，與約定float canonical不符，已改240.0；投影故障case改明確CheckViolation而非泛用Exception，避免假驗到rollback。
3. [mqtt-db-02](mqtt-db-02/result.json)保留啟動FAIL：controller在DB初始化暫時server上看到schema就開始migration，server接著退場；改等最終TCP listener。之後 [mqtt-db-03](mqtt-db-03/result.json)13項真DB/MQTT通過、[mqtt-db-tls-04](mqtt-db-tls-04/result.json)15項含mTLS通過。
4. [full-05](full-05/result.json)保留256 passed＋12 fixture error：controller誤用noconftest，停用了專用field fixture；未涉及產品程式失敗。改保留snapshot內自己的conftest後 [full-06](full-06/result.json)256 passed／12 skipped、90.32%。其間曾嘗試停止已自行完成並清除的自有worker，Docker回報No such container；沒有停止其他容器。
5. 獨立Python／code／security複核發現且修復：巨大JSON int的float轉換溢位、Paho callback／session lock逆序、sample rate與session size限制、舊v2 schema缺snapshot仍可啟動、清理逾時跳過後續容器。補反例後 final-07 為259 passed／12 skipped、90.81%；[審查收據](reviews.md)及[source hash](reviewed-source-sha256.json)保存。
6. 依專案要求另同步 `tests/integration/test_migrations.py` 的019 class；快取測試image沒有psycopg2，此class未另跑、不計入259。**同一019 twice／legacy／權限行為已由final-07的asyncpg實際DB測試執行**，不是將未跑的舊class追稱通過。

## 保護與收尾

[完整性檢查](integrity-check.json)：舊原始770檔、前輪backlog384檔、實際接收補測321檔、活動／封存來源各17檔與verifier依賴3檔均相符。[共享容器](container-comparison.json)前後17個ID相同；[原程序](soak-processes-after.json)、[status快照](soak-status-after.json)、[事件尾端](soak-tail-after.jsonl)持續運行。只修改權威repo原碼；活動24h凍結來源／verifier／COM3／COM4／原始sealed證據不變。

每個run只收自己建立的container ID，final-07自有5個容器logs／移除均成功。edge／simulator子程序只在worker namespace，退出收回。臨時PKI在最外TemporaryDirectory生命週期清除，沒有把私鑰納入證據；保留公憑證fingerprint及配置。若logs／rm逾時逐個記失敗並繼續，不能因清理失敗宣稱整輪通過。

## 尚未切換的範圍

本輪沒有執行共享migration、重啟共享服務或切換任何活動v1 sender；新[可選Compose](../../compose.edge-receiver.yml)及field範本供commission。v1已刪而中央未收的舊資料不能由新機制恢復。切換須按receiver README先建權威mTLS／schema／generation，再停止目標舊sender、備份並只讀轉換；原24h完成前不動它。

單筆／單inflight上限2batch/s、edge loop約1秒；不承諾20/s或7天backlog七小時補完。完整多設備scheduler／sealed manifest及每日對帳／heartbeat UI／remote sampling尚未實作；audit／receipt暫不purge，cap滿停新採樣，長期容量需另驗。Pi／SD／ADTEK／4G／實體掉電／正式PITR／憑證輪替撤銷尚未驗收；中央災難RPO保持既有邊界。
