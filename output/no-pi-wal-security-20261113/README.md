# 無 Pi 短測：中央 DB／WAL TLS、WAL 滿載恢復、備份／WAL 損壞與跨庫誤用

日期：2026-11-13。完成使用者指定三項；未重跑1h／24h長測、未使用COM3／COM4、未修改共享容器或正式DB。僅自建隔離network-none容器與短生命測試PKI，未部署正式服務。

| 完成項目 | 真實故障與結果 |
|---|---|
| 中央DB與WAL複寫TLS | 合法雙向TLS可用；DB七種、WAL八種反例：錯CA、錯hostname、過期server、缺client、非信任client、過期client、合法憑證角色不符，WAL另加明文。逐項驗實際拒絕原因，故障時來源保留且無假ACK。另建立確實連上的明文peer／錯角色TLS peer，同步ACK predicate仍拒絕。 |
| WAL儲存滿與恢復 | 只填自有128MiB tmpfs，真正ENOSPC使pg_receivewal子程序exit1、容器仍存活；slot inactive且主庫保留WAL增加33,403,936 bytes。釋放測試filler後原slot重連；peer flush覆蓋固定LSN `0/5003870`，最終保留落後0，來源原ID入庫一次、pending0，無部分寫入。 |
| 備份／WAL損壞、跨庫誤用 | 真實PG_VERSION損壞被pg_verifybackup拒；後續WAL翻位元觸發CRC錯誤／目標不可達；外cluster WAL因system ID不符拒；整套checksum有效外cluster備份亦被外置可信expected_system_id擋在啟動之前。正常basebackup＋WAL成功promote並恢復備份後marker；原始輸入hash均未變。 |

## 修復內容

1. field DB強制`db_tls` CA／hostname／client cert，禁止DSN主機覆寫、Unix socket及明示TLS降級。設定與程式為 [database_tls.py](../../services/edge-receiver/edge_receiver/database_tls.py)、[receiver範本](../../services/edge-receiver/deploy/receiver.example.json)。
2. [migration021](../../infra/timescaledb/migrations/021_edge_tls_wal.sql) 增加受限`sync_tls_wal_flushed`：唯一具名同步peer、固定LSN、TLS、client DN與固定`ems_wal_archive`角色共同通過才能ACK。runtime直接呼叫新函式，漏裝021不會降回舊檢查；保留舊名強化wrapper。migration實際連續執行兩次。
3. [backup_preflight.py](../../services/edge-receiver/edge_receiver/backup_preflight.py) 在啟動還原前核外置cluster身分再核checksum；不再把「內部自洽」當成「正確目的cluster」。新增解壓前layout／資源檢查，拒絕路徑穿越、link、device、PAX／GNU sparse與過量展開。初版sparse漏檢已以兩個RED反例重現，改成固定512-byte header檢查，在讀extension payload前拒絕。
4. 私鑰外置PGDATA；補正式TLS／HBA範本與 [唯一WAL/PITR操作手冊](../../services/edge-receiver/WAL-PITR.md)。測試器證書reload確認、活tmpfs的WAL匯出、實際填滿觸發、錯誤原因與完整案例閘門均已修正，原失敗紀錄保留。

## 驗證結果與證據

| 檢查 | 最終結果 | 入口 |
|---|---|---|
| 三項整合定點測試 | **55通過／62.52秒**：20新案＋35既有槽號邊界；20獨立證據條件全真，26自有容器清理成功 | [result](run-verified/result.json)、[JUnit](run-verified/integration.xml)、[TLS正例](run-verified/db-wal-tls-positive.json)、[ENOSPC](run-verified/wal-enospc.json)、[recovery](run-verified/recovery-inputs.json) |
| 相鄰整體短回歸 | **568通過／12既有專用案skip／34.71秒**，coverage **90.99%**；6自有容器清理 | [result](regression-final/result.json)、[JUnit](regression-final/integration.xml)、[coverage](regression-final/receiver-coverage.json) |
| 已ACK且本地已刪資料的原PITR相容性 | **36通過／12.32秒**；原主庫停止、備份後B救回、目標後C仍由pending補送、舊ACK拒、缺WAL拒；12自有容器清理 | [result](pitr-regression/result.json)、[JUnit](pitr-regression/integration.xml) |
| TLS／還原／archive單測 | **28通過**；包含sparse兩個反例 | [JUnit](security-unit-verified.xml) |
| 案例完整性與證據反例閘門 | **38通過**；缺案例、錯原因、假恢復及任意控制注入均不得判PASS | [JUnit](gate-final.xml) |

以上套件存在重疊，不加總成獨立測試數。最終三組實際執行期間source hash均未變；後續只同步文件／範本。程式、Python、安全與架構獨立複核通過，記錄見 [review](review-status.json)。封存與舊證據完整性見 [final audit](final-verification.json)、[manifest](artifact-sha256.json)。

保留原始RED：security-red（17失敗）、archive-red（7失敗）、sparse-archive-red（2失敗）。run-01～06是中途FAIL，不能當成完成；run-07是早期53案；run-final是加client過期後55案但早於sparse修復；**run-verified才是本輪最終55案**。bootstrap-tls、早期單測與這些中途run皆留存，不以重寫結果掩蓋缺陷。

## 適用範圍

跨庫指PostgreSQL實體cluster，不是同cluster內不同logical database；同system ID複製分支仍需維運核定timeline／target。archive預檢只支援標準未壓縮regular-file／directory tar；上限預設8GiB／100000 entries，外部tablespace／其他封裝另驗。預檢後的檔案須保持不可變，解開到受控空目錄。

tmpfs僅驗容量耗盡與恢復，不證明掉電耐久；本輪同宿主私有容器不代表正式跨主機HA。正式CA分發／輪替、受管HBA／LOGIN、獨立持久archive與首份basebackup仍須部署驗收。Pi／ADTEK／SD掉電／4G仍待硬體。沒有留下WAL的舊歷史缺口無法事後憑空補回。
