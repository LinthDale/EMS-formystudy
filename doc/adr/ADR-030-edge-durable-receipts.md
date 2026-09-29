# ADR-030：邊緣 SQLite 與中央提交確認
## Status
Proposed，2026-09-29。對應 [PRD-0021](../prd/PRD-0021-multi-device-edge-reliability.md)。
ADR-029 的已實作v1行為仍有效；本ADR不宣稱已替換部署。

## Context
現有單設備Delta採集器先存SQLite、PUBACK後刪除；Telegraf到中央DB可能尚未commit，亦無唯一sample_id。需求擴為M70A-262／RPI-M30A、8台10秒、7天offline。容量研究顯示SQLite本機儲存合理，主要缺口在bus排程、持久化／電源、入庫責任與重送去重。

## Decision
保留SQLite本機outbox與中央PostgreSQL/Timescale分工。基準使用單一序列化寫入、DELETE/EXTRA、短交易；WAL/FULL只在修補版本核實及實測後採用。不因容量需求在Pi上新增PostgreSQL。

新增v2 MQTT bounded batch與authenticated committed ACK；stable sample_id及canonical payload hash先本機提交。中央receipt複合唯一(gateway_id,sample_id)與量測同交易寫入，commit後ACK，本地驗證後才刪。相同ID異hash拒絕。receipt保留至max(committed_at,sampled_at)＋90天＋24小時以上，清理須確保原樣本已超接收窗，避免未來時間偏移造成重放空隙；明確at-least-once transport＋deduplicated insert，非無條件exactly-once。

v2使用ems/v2/gateways/{gateway_id}/samples與/acks，隔離舊Telegraf以免雙寫；只讀RTU/TCP adapters，各型號profile經真機確認。8台為待驗收設計目標，16台雙bus另驗收。

## Consequences
正面：現有SQLite與中央DB可延續，離線責任明確；去重不依賴來源時鐘唯一性；多bus可獨立擴展。
成本：需durable receiver、schema migration、ACK身份綁定、版本化queue、retention/restore治理與更多故障測試；不再能單靠既有Telegraf滿足v2契約。SD與電源仍是系統風險，DB設定無法保證壞卡零遺失。

替代方案：只開Mosquitto persistence／Telegraf persistent_session不足以提供producer到DB逐筆commit契約；Pi PostgreSQL增加維運而未解決ACK窗口；HTTPS batch可行但本案保留既有MQTT通道，避免同時維護兩套上傳契約。
依據與benchmark：[調研報告](../research/2026-09-29-sqlite-edge-capacity.md)。

中央fsync／同步commit為前提；receiver重算canonical hash。中央災難另定RPO≤15分鐘／RTO≤4小時，異機WAL與備份驗收；不宣稱災難零遺失。PITR切換需隔離ACK路由、重連握手與不回滾的recovery_generation，拒絕前一session ACK，詳細契約見PRD。

2026-09-29對帳補充（仍Proposed）：PRD-0021 FR-2113～2116／§15.1加入per-device stream序號、sealed manifest與ID/hash集合差異、中央實際量測核對、採樣缺口分類。ACK後本機僅保留7天audit索引，中央receipt snapshot可修復缺失投影；兩端原始payload均不存在時標不可恢復，不宣稱能補回。新對帳回覆不能替代committed ACK。尚未實作。

對帳審查補充：不可變sample schema與server receipt明確包含stream_id/capture_seq/window_id/config_revision並納入hash；receipt新增stream/seq唯一約束。首次ingest／重送／缺列修復共用receipt交易鎖，鎖內重查量測數量，避免並行repair雙插入。詳PRD-0021 §8／§15.1。

採樣間隔補充（Proposed）：PRD-0021 FR-2117/2118及§15.2定義每設備1/5/10/15/30秒preset、預設10秒、可混用；8台10秒7天仍是基準級距。requested/effective與版本化排程分開，切換按實際slot核對，採樣／傳送／顯示／聚合互不混淆。快採樣須通過bus、pending＋audit空間及補傳驗收，不承諾8台在同一RS485能1秒採完；操作介面／設定下發尚未實作。
