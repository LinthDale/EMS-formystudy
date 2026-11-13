# ADR-048：v2最新量測與最舊補傳交替送達

## Status

Accepted，2026-11-13；已實作與私有短測，未切共享部署。使用者要求實測大量舊資料補傳時新資料延遲、發現問題即修復。承接[PRD-0021](../prd/PRD-0021-multi-device-edge-reliability.md) FR-2107既有live／backlog公平目標與[ADR-045](ADR-045-newest-first-edge-retention.md)最新優先容量政策；不更動wire2、本地schema3、認證或中央去重。

## Context

現sender只取最舊pending。背壓時新資料只能排整批歷史之後，與最新量測重要及FR-2107不符。[RED](../../output/no-pi-restore-load-20261113/fairness-red.log)以50舊＋1新與持續新資料重現公平排程缺口，未跑長測。容量輪替只決定保留哪些樣本，不能代替傳送排程。

## Decision

1. sender採固定1:1成功解析輪替：最新capture_seq pending一筆→最舊pending一筆，重複；初始優先最新。索引仍用queue唯一capture_seq，不以timestamp或ACK先後判斷新舊。queue.pending()預設仍取最舊，sender明示選擇。
2. 新est讀取是queue目前最新待傳，不是重寫snapshot或新建sample。每筆仍原UUID/hash/來源時間，quarantine不送、不被當作成功。正常authenticated committed ACK成功解析後才換邊；timeout／retryable不消耗成功輪次。原筆因容量淘汰而收到遲到ACK不算committed、不消耗成功輪次。
3. 保持單筆／單inflight、.5秒最小成功間隔、edge原有1秒loop及退避，不藉本修復宣稱20/s／7天回補性能。最新可在至多兩次成功送達機會中被選中，但若又有更晚新筆到來，較早的新筆會進最舊通道；不是每一筆都享有固定秒數SLA。斷線／DB故障／退避、採集速度大於吞吐仍可能延遲或容量淘汰。
4. 持續新資料下，每兩筆成功至少服務一筆最舊，避免歷史永久飢餓；只有一筆時同一候選不重複提交。成功輪次為程序記憶體狀態，重啟從最新開始，不變更schema；反覆程序重啟可能降低最舊服務機會，維運須處理重啟風暴，不能宣稱跨重啟嚴格公平。
5. 新測試使用私有DB完整pg_dump／pg_restore到新庫，外置generation換代＋舊ACK拒絕，分開有pending可補與ACK已刪且backup未含的不可補資料；此為邏輯備份還原演練，不等於WAL PITR或中央RPO/RTO已驗收。接收超量測試只動私有broker／DB／worker；queue滿可丟輸入但不得回假committed，來源保留／原ID重送恢復。

## Consequences / Validation

新量測不需等整批歷史完成，最舊也有進度；傳送順序可不同於capture_seq，但中央receipt與投影依原ID冪等。保持既有拒絕衝突與來源時間，不讓舊資料冒充新鮮狀態。Owner EMS；維護在[store](../../services/delta/delta_device/reliable_store.py)／[sender](../../services/delta/delta_device/reliable_sender.py)，config無新key，1:1為此階段spec-locked規則。無UI／素材／RWD變更。

驗證：[本輪證據](../../output/no-pi-restore-load-20261113/README.md)定點38通過／18.90秒，419相鄰通過／12既有專用case跳過／coverage91.04%。公平單測3RED→GREEN、1000歷史下3新筆以原edge1秒節奏在1.044／2.091／2.098秒commit，最舊持續前進、6確認＋997待傳＝1003完整。這不是percentile或現場SLA。另有真pg_dump／pg_restore新庫、generation換代／舊ACK拒及不可補資料揭露；200封同樣本重複訊息下queue64/drop135/rate拒65，恢復後原／新各1列。architect／Python／code／security複核通過，原RED／失敗run及工具修正保留；未切共享服務或重跑長測。
