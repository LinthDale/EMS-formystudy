# PRD-0021：Delta 多設備採集與可靠補傳規格
狀態：Draft（2026-09-29，尚未實作／部署）｜Owner：EMS team
依據：project_rules.md、PRD 架構設計 Guideline。承接 PRD-0020；決策 ADR-030。容量證據見 [調研報告](../research/2026-09-29-sqlite-edge-capacity.md)。

## 1. Overview & Context
使用者擬採購樹莓派＋SIM7600G-H，現場讀取 Delta M70A-262 與 RPI-M30A，经 4G 呈現於 EMS。現有實作是單設備、MQTT broker ACK 即刪本地資料，無中央去重；不能承諾多設備／7 天補傳。

本 PRD 定義**每設備可選1／5／10／15／30秒採樣，預設10秒**；8台／10秒／7天是待驗收的基準容量組合，其他組合須通過§15.2的能力與容量檢查。262 未明列於 V1.35 適用清單；M30A 後綴與兩機韌體仍待盤點。型號確認是實機支援宣稱的必要條件，並不妨礙現在完成容量與硬體規格。

## 2. Goals / Non-Goals
Goals：一台閘道器管理最多 8 台混合指定機型；每台獨立選擇1／5／10／15／30秒、預設10秒採集；持續供電且儲存健康時，斷網 7 天仍保留已取得資料；中央入庫後才移除本地待送資料；能辨識重送、設備離線、時間不可信及資料缺口。

Non-Goals：遠端開關／限功率控制、改併網保護參數、電力交易結算認證、次秒波形、全部 MPPT/故障碼展示、本地永久歷史庫；不以本規格宣稱目前軟體已支援 8 台。16 台是下一級容量方案，需另驗收。

Constraints：Pi Zero 2 W 的 512 MB；SIM7600G-H 整板未定；可能有既有資料收集器佔用 bus；兩款機型須確認協定與韌體；4G 可長時間離線；量測用途不得替代設備自身安全保護。

## 3. User Stories & Personas
- 安裝者以設備清單設定站號、profile、bus，逐台比對銘牌及顯示讀值。
- 維運人員在 EMS 看到即時資料、採集／上傳狀態與 backlog，知道斷網資料正在補傳。
- 工程人員用 stable sample_id 驗證重啟與重送後沒有漏列／重複入庫。
- 採購人員按 §5 套件與 §13 驗收，不以地址上限或模擬器速度決定保證台數。

## 4. Functional Requirements
| ID | 要求 |
|---|---|
| FR-2101 | 配置最多 8 個 device，唯一 device_id；每 bus 站號不可重複。bus 定義 transport、串口／TCP endpoint、baud、parity、stopbits、deadline；各 device 綁 model/firmware/profile。 |
| FR-2102 | 每 RS485 bus 僅一個 owner、一次一個 request；monotonic clock 定時輪詢，錯過週期不爆量補讀；設備失敗獨立退避，不阻塞正常設備。 |
| FR-2103 | M70A-262、RPI-M30A 各自經官方 map／真機 golden vectors 驗收。讀取前校驗 profile；unsupported register、CRC、短讀、timeout 不轉成 0。預設唯讀 FC04，其他函式須另審。 |
| FR-2104 | 完整採樣立即 enqueue 並提交 SQLite；stable UUID sample_id、gateway_id、device_id、time、profile_version、quality、canonical payload hash 同交易持久化。重送不重建 sample_id。 |
| FR-2105 | 10秒基準上限600,000筆；其他間隔依§15.2配置容量，不能沿用此上限宣稱7天；整筆 compact JSON ≤ 1,024 B；實測資料與索引平均 ≤ 2 KiB／筆。4 GiB outbox budget；至少 8 GiB data partition；計數與磁碟高水位皆監測。 |
| FR-2106 | PUBACK 不刪資料；只有 authenticated committed ACK 且 ID/hash 一致才刪除。中央 receipt 唯一鍵與量測寫入必須同一 PostgreSQL transaction，commit 後回 ACK。 |
| FR-2107 | 有界批次最多 32 筆／64 KiB，最多 8 批 inflight；斷線指數退避、jitter；避免 hot retry；live 與 backlog 公平排程。 |
| FR-2108 | 可信 RTC／NTP 決定 time_quality；UTC 不可信時暫停正式量測並告警，不製造假時間。既有 backlog 可獨立續送。離線冷啟動應在可驗證 RTC 時繼續採樣。 |
| FR-2109 | 滿佇列保留舊未送資料，停止接納新量測、標記 coverage gap、告警；不得 silent overwrite。永久拒絕資料進有界 quarantine，不能當 committed 刪除。 |
| FR-2110 | 保留 TCP adapter 與 RTU adapter；以本機已核准 endpoint 配置，不允許雲端任意改寫。未證明逆變器原生 TCP 時，明示需外接 RTU/TCP gateway。 |
| FR-2111 | EMS 四欄相容投影仍為 L1 V、L1 A、三相總 kW、累計 kWh；完整 compact snapshot 在中央 receipt 有限期保存。UI 詳細三相展示另案。 |
| FR-2112 | 重送不得讓過去樣本冒充新鮮量測；received_at、sampled_at 分離，heartbeat 不以歷史 backlog 更新設備即時狀態。 |
| FR-2113 | 每device的stream_id/capture_seq與sample同交易持久化；紀錄排程生效版本與採集失敗／未知區間，区分漏採與漏送。 |
| FR-2114 | 每5分鐘sealed manifest、重連核對與每日最近7天重查；以ID集合／hash確認，不只比count或MAX(seq)。 |
| FR-2115 | 核對中央receipt與實際量測；缺筆可用pending或中央snapshot修復，補後再核對；無來源資料標不可恢復。 |
| FR-2116 | 獨立30秒heartbeat與90秒不可達判斷；EMS呈現採集覆蓋率／交付完整率及缺口分類；audit有界且過期明示。 |
| FR-2117 | EMS每device提供1／5／10／15／30秒採樣選项，預設10秒，可混用；採樣、上傳批次、畫面刷新與圖表聚合分開設定及呈現。 |
| FR-2118 | 間隔变更前驗證bus／型號、queue／audit磁碟、上傳與中央容量；保留requested/effective及版本生效界線，失敗不暗改間隔；對帳依實際排程版本計算。 |
## 5. Non-Functional Requirements
所有數字是設計／驗收目標，非目前效能聲明。

| 項目 | 8台全部10秒的基準規格（其他組合見§15.2） |
|---|---|
| 型號 | M70A-262 / RPI-M30A，可混合；各 profile 先通過機型閘門 |
| 採集介面 | 1 路隔離 RS485，最多 8 個 slave；TCP transport 保留 |
| 串口 | 初始驗證採 19,200 / 8N1；需依兩款現場手冊確認並統一 bus 設定 |
| 排程 | 各 10 秒；健康設備完整 poll p95 ≤ 0.5s；全 bus scan p99 ≤ 8s；採樣間隔 p99 ≤ 12s |
| 故障隔離 | 單次完整 poll deadline ≤ 1s，當周期不立即重試；離線 probe 退避至 60s；7 台健康＋1 台失聯時健康台仍達間隔目標 |
| 斷網容量 | 7 天＝483,840 筆；cap 600,000；持續供電、不含設備本身沒回應的缺測 |
| 儲存 | 64 GB 工業／耐寫 microSD；RW data ≥ 8 GiB；outbox budget 4 GiB；不可放 RAM overlay |
| 空間政策 | data 使用率 70% 警告、85% critical；free < 1 GiB 或 queue cap／outbox budget 命中停止接纳；保留資料、告警與缺口計數 |
| DB | SQLite，基準 DELETE/EXTRA；單一寫入序列、交易中不等網路；schema_version；啟動核實 pragma |
| 補傳 | RTT 200ms、封包丟失 1%、有效 uplink ≥512 kbit/s、中央容量充足時，入庫 ≥20 筆/s；同時採集0.8/s，7 天 backlog ≤7h |
| 正常延遲 | 上述穩定網路無 backlog 下，sample 到中央 commit p95 ≤15s；EMS顯示 p95 ≤25s |
| 資源 | Pi Zero 2 W / Lite OS / systemd；採集服務RSS ≤150 MiB；全機 MemAvailable ≥100 MiB；CPU平均 ≤60%，72h無OOM |
| RPO | 已 SQLite commit 樣本於程序 crash／驗收電源事件後零遺失；以獨立 ledger 驗證。不承諾卡片永久損毀／未提交或斷電期間的採样 |
| RTO | 穩定供電、可信時鐘下 boot-to-collection ≤120s；4G恢復後開始重送 ≤120s |
| 时鐘 | RTC＋NTP；UTC最大誤差目標2s，離線7天後仍需驗證；不可信即標記停採，不能誤稱連續覆蓋 |
| 測試 | 純邏輯覆蓋 ≥80%；所有 FR 有用例；兩款各至少1台實機＋其餘受控模擬負載，正式容量承諾需8台混合實機驗收 |

採購套件（數量為每 gateway）：
| 品項 | 數量 | 採購／驗收條件 |
|---|---:|---|
| Raspberry Pi Zero 2 W | 1 | 不以第一代 Zero 取代本基準；Lite OS，保留散熱／USB可用性 |
| SIM7600G-H 擴展板 | 1 | 鎖定廠商、完整板型、接口、Linux支援、當地電信相容性；含LTE天線、SIM方案 |
| 隔離 USB–RS485 | 1 | Linux 驅動、穩定 by-id、電氣隔離與 ESD／浪湧規格由供應商提供；auto direction |
| 工業／耐寫 microSD 64 GB | 1＋備用1 | 具體SKU／溫度／保固／耐寫條件可追溯，不能套用最大容量卡TBW |
| 電源＋UPS | 1組 | 按modem峰值＋Pi＋外設選型；有失電通知、≥30s關機餘量、來電自啟，整機負载測試 |
| RTC＋電池 | 1組 | I2C/GPIO與HAT相容；離線開機及7天漂移驗收 |
| 機箱、端子、線材 | 1組 | 隔離雙絞線、屏蔽／接地依現場設計；終端電阻依bus兩端及機型手冊配置，不每台都加 |
| USB Hub | 視板型 | HAT(B)已有Hub，不預設重複購買；確認供電拓樸 |

16 台擴充提案：Pi 4 Model B ≥2 GB、2 路隔離 RS485、每 bus 8 台、queue ≥1,200,000、outbox budget ≥8 GiB、RW data ≥16 GiB、重新測試資源及補傳。現有 config 最大1,000,000需調整；本次不承諾16台已可用。1秒採樣級距見§15.2，30天斷網另核算。

## 6. System Architecture
圖內部署標示是提案；中央 durable receiver 尚不存在。Owner：現場硬體由安裝維運，Python軟體與中央服務／DB由EMS team。

### 6.1 C4 Context
~~~mermaid
flowchart LR
 subgraph OT[現場 OT - 安裝維運]
  D[Delta M70A-262 / RPI-M30A]
  G[Pi Gateway - Python - EMS team]
  D -->|唯讀 RTU 或 TCP| G
 end
 subgraph IT[中央 IT - EMS team]
  E[EMS 入庫與查詢系統]
  U[維運使用者]
  E --> U
 end
 G -. outbound 4G MQTT TLS .-> E
 E -. committed ACK .-> G
~~~
### 6.2 C4 Container
~~~mermaid
flowchart LR
 subgraph PI[OT Pi - systemd - EMS team]
  S[Python scheduler / profiles]
  Q[(SQLite persistent outbox)]
  P[Python sender / ACK validator]
  S --> Q
  Q --> P
 end
 subgraph SERVER[IT Central - EMS team]
  B[Mosquitto TLS / ACL]
  R[Proposed durable receiver]
  DB[(PostgreSQL receipts + Timescale measurements)]
  A[Existing BFF / PostgREST]
 end
 P -. MQTT batches .-> B
 B -. subscription .-> R
 R -->|DB transaction| DB
 R -. committed IDs .-> B
 B -. ACK .-> P
 P -->|verified deletion| Q
 A --> DB
~~~
### 6.3 Data Flow
~~~mermaid
sequenceDiagram
 participant D as Delta OT
 participant P as Pi Python
 participant Q as SQLite
 participant M as MQTT TLS
 participant R as Durable receiver
 participant DB as PostgreSQL/Timescale
 P->>D: read approved profile
 D-->>P: registers
 P->>Q: sample_id + immutable payload, commit
 P-)M: QoS1 bounded batch
 M-->>P: PUBACK (keep row)
 M-)R: validate identity/schema
 R->>DB: receipt + measurement in one transaction
 DB-->>R: COMMIT success
 R-)M: application committed ACK
 M-)P: ID + hash + gateway
 P->>Q: delete matching committed rows
~~~

## 7. Data Model
提案採不可變樣本；delivery metadata可更新，量測內容不可原地改寫。
~~~mermaid
erDiagram
 EDGE_OUTBOX {
  string sample_id PK
  string gateway_id
  string device_id
  bigint sampled_at_us
  string profile_version
  string payload_hash
  text canonical_payload
  string state
  integer attempts
 }
 INGEST_RECEIPT {
  string gateway_id PK
  string sample_id PK
  string device_id
  string stream_id
  bigint capture_seq
  string window_id
  string config_revision
  string payload_hash
  bigint sampled_at_us
  timestamp committed_at
  jsonb snapshot
 }
 ELECTRICITY_MEASUREMENT {
  timestamp time
  string device_id
  float voltage
  float current
  float power_kw
  float energy_kwh
 }
 INGEST_RECEIPT ||--|| ELECTRICITY_MEASUREMENT : atomic_insert
~~~
ER關係表示同交易責任，非既有量測表已有FK。receipt為普通PostgreSQL表，複合唯一鍵(gateway_id,sample_id)；避免以time以外鍵違反hypertable唯一索引限制。既有表無sample_id；新receiver必須是v2樣本的唯一入庫路徑，禁止同筆再送舊Telegraf。

Edge索引(state, next_attempt_at, sampled_at_us)由實作壓測選定；gateway_id不可透過換設定重綁已有queue。receipt device_id應驗證授權registry；FK可行性待既有registry生命週期確認，刪設備不能cascade刪除receipt。無PII／無憑證，屬營運資料。

Edge待送保留到committed；quarantine保留且計入總容量，不無限增長。receipt與snapshot的retention_until至少為max(committed_at, sampled_at)＋90天＋24小時安全裕度；只有超過retention_until且原sample已超出接收窗才可清理。接收與清理交易使用中央DB UTC及一致的邊界條件，避免清理／接收競態；接收端只接受 sampled_at 在目前UTC前90天內及後2分鐘內且quality可信的樣本。超窗重送進人工處理，不盲目重入。來源時間超窗與去重保留共同限制重放期限。量測長期保留沿中央既有政策；本案新增10秒原始資料，未新增壓縮／聚合保證。receipt清理與中央備份復原需一致，避免回復後去重與量測分離。中央ACK要求PostgreSQL fsync=on、synchronous_commit=on，底層正確持久化；不得把commit降為非同步。

§15.1補充stream/sequence、audit索引及中央量測身份關聯；ERD為原始交付主路徑示意，實作前需隨schema migration補齊audit模型。

## 8. API Contract
全部是Draft；api/openapi.yml的x-planned-delta-edge-v2只登記提案，無新REST endpoint。

MQTT topics：
- publish: ems/v2/gateways/{gateway_id}/samples
- ACK subscribe: ems/v2/gateways/{gateway_id}/acks
- QoS1、retain=false；TLS驗主機名稱與CA，gateway各自mTLS credentials。
- 裝置僅publish自己的samples、subscribe自己的acks；只有receiver可publish ACK。

Session握手topic：ems/v2/gateways/{gateway_id}/session/request及/session/response；request僅該gateway發布，response僅receiver發布。request带隨機challenge，response回challenge及recovery_generation；QoS1、retain=false、≤1 KiB、每gateway最多1次/s。每次連線使用新challenge，未驗證完成不收committed ACK。

Sample envelope：schema_version=2、gateway_id、session_challenge、recovery_generation、batch_id、samples[]。每筆sample_id UUID、device_id、stream_id(UUID)、capture_seq(1..2^63−1)、window_id(UUID)、config_revision、sampled_at_us(int64)、profile_version、time_quality、measurements{voltage,current,power_kw,energy_kwh}、可選bounded三相／state／temperature；數值finite，明確單位；unknown fields拒絕。sample_id在本機生成一次，retry不變。

hash定義：SHA-256對已持久化canonical sample JSON之UTF-8 bytes計算（含所有schema允許的樣本欄位，包括sample_id/gateway_id/device_id/stream_id/capture_seq/window_id/config_revision/time/profile/quality/量測，不含hash本身與可變session/batch資訊）；實作固定canonicalization規則與跨語言vectors。receiver必須先驗證schema，把envelope gateway_id確定性納入canonical sample，重新計算hash並與claimed hash比對；不一致則在去重／寫DB前拒絕。ACK使用server計算並持久化的hash，不回顯未驗證的client hash。sample最大1,024 B包含hash；batch最多32筆且wire≤64KiB。相同ID、相同hash冪等成功；同ID異hash永久衝突，原值不覆寫。

ACK envelope：schema_version=2、gateway_id、session_challenge、recovery_generation、batch_id、results[{sample_id,payload_hash,status,committed_at?,error_code?}]。status為committed／retryable／rejected，最多32結果；committed_at只在DB提交後生成回覆。ACK合法topic與身份、gateway、當前session/generation、已發batch_id、pending ID/hash、schema均通過才delete；unknown/duplicate ACK忽略並計數。rejected不得當成功刪除；人工更正需保留原始證據。

中央每gateway限流40 samples/s、burst64，batch≤2/s，inflight≤8；超限回retryable，不回committed。client ACK timeout30s、退避1–60s加jitter；disconnect不重新分配ID。不在SQLite transaction中等待網路。接收端總容量依gateway數另驗收，20/s是單gateway補傳目標。

Modbus：只有核准profile的FC04地址白名單。目前V1.35通用候選讀40995×1、49152×13、53248×9，0-based PDU=文件地址−1；條件式40962與溫度另驗收。**這不是M70A-262已確認map**；配置需按型號版本，不用掃描全部地址猜profile。

### 8.1 對帳與心跳契約（Draft）
新增自有gateway topics：
- edge publish / receiver subscribe：ems/v2/gateways/{gateway_id}/reconcile/request、ems/v2/gateways/{gateway_id}/health
- receiver publish / edge subscribe：ems/v2/gateways/{gateway_id}/reconcile/response
QoS1、retain=false、mTLS及權威device/stream綁定。health≤4KiB、30秒一次，只接受當前session序號遞增的新鮮訊息，不重送舊heartbeat。

reconcile request：schema_version、gateway_id、session_challenge、recovery_generation、request_id、op(manifest或page)、device_id、stream_id、window_id、config_revision、sealed、seq_start/end、count、digest；page帶有限entries(seq/sample_id/hash)。response回同身份/session/request/window與status(matched/diff/retryable/rejected)、bounded差異清單及opaque next_cursor。cursor綁session/request/範圍，過期重開核對，不擴大授權範圍。每訊息≤64KiB、每頁≤256項、每gateway request≤2/s、inflight≤2；超限retryable並退避。manifest按window_id/version冪等；同版本不同內容視為conflict不覆寫。hash canonicalization／digest vectors列為實作contract test，不新增遠端採集／寫入控制。
## 9. Security & Privacy
OT/IT分區，Pi只主動出站，沒有公網serial／502／1883；不向edge分發中央DB或OPS金鑰。Modbus側只读，不能將gateway變成remote control。

mTLS身份由broker權威映射至gateway；receiver驗payload/topic gateway與registry允許device一致。client-side格式驗證不算身份綁定。ACK只允許receiver發布，禁止gateway偽造別人的committed回覆；retained ACK拒絕。雙向payload限大小、深度、筆數、finite數值與timestamp，避免DoS與資料污染。

Secret檔0600、目錄0700、專用低權限systemd帳號；日誌不寫金鑰、環境或完整payload。支援憑證輪替及撤銷；憑證過期fail-closed但持續本機採樣。實體SD被取走的營運資料外洩風險由機箱管理；需要磁碟加密時另解鎖定策略，不假稱已有at-rest encryption。

## 10. Observability
metrics：per-device poll成功／CRC／timeout、poll duration、last_good_sample_age；queue_rows、oldest_pending_age、db_bytes、free_bytes、quarantine_rows、committed/s、retry/s、dedup/conflict、clock_quality、RSS、4G registration／訊號。
queue>70%或oldest>5天warning；>85%、free<1GiB、integrity fail、clock untrusted、>3次連續poll失敗critical；保持本地可見，網路恢復補送告警。用sample_id/gateway_id/batch_id關聯，不記敏感payload。Runbook含電源／線路／時鐘／queue滿／corruption分類，禁止自動刪journal。

## 11. Risks & Mitigations
| 風險 | 機率 | 衝擊 | 緩解 |
|---|---|---|---|
| M70A-262不相容既有map | M | H | 每型號／韌體獨立確認與golden vectors，未確認不啟用 |
| 舊收集器與Pi同bus雙master | M | H | 安裝前盤點；移交bus owner或使用既有gateway轉接，不直接並接 |
| 離線設備拖住bus | H | M | 整次poll deadline、單獨退避、公平排程 |
| PUBACK誤作入庫成功 | H | H | committed receipts與原子去重 |
| SD掉電／磨損 | M | H | UPS、指定卡片、同步提交、實際power-cut tests |
| 假ACK導致刪資料 | M | H | TLS ACL、server-only ACK、pending ID/hash驗證 |
| 時鐘錯誤導致假時間 | M | H | RTC／NTP、品質與時間窗；不可信停採並揭露缺口 |
| 多日斷網超cap | M | H | 空間與age告警、保留舊樣本、採購容量留裕度 |
| v1/v2雙寫或不同DB恢復點 | M | H | 單writer路由、原子receipt、備份復原一致性測試 |
| WAL版本缺陷／無界checkpoint | M | H | 基準DELETE/EXTRA；WAL前檢查修補並壓測 |

## 12. Rollout & Migration Plan
1. 用兩型號台架確認profile與線路；準備指定Pi／SD／HAT。
2. RED測試，再實作多設備＋outbox v2＋durable receiver。新topic隔離舊demo；中央schema先部署且可向後相容。
3. 新DB schema version及backup：停止舊sender後轉換未送queue，每舊row賦予一次ID並記migration ledger。已被v1刪除資料不可重建；切換點之前不承諾完整性。
4. 單gateway canary 72h，再7天offline與回補；最後8台混合真機現場驗收。
5. 任何identity違規、checksum衝突、integrity failure立即自動停送並保留queue；poll錯誤率>1%連5分鐘（排除人工離線用例）停止擴展並告警。
6. 人工回滾至最後相容版本；不得讓v1 sender開v2 queue或以PUBACK清空它。保留新DB／receipt，恢復備份時核對切換後樣本；必要時僅停sender，持續安全採集。

中央災難復原另訂目標RPO≤15分鐘、RTO≤4小時，採異機持續WAL歸檔（可恢復落後≤15分鐘）、每日base backup與定期還原測試；歸檔落後超標即告警並停止宣稱達標。這容許災難時已ACK資料在RPO內遺失，不能稱端到端零遺失；若業務要求此類事故RPO=0，需同步異機耐久副本後才ACK，另行規格化。Pi的已commit程序／電源故障RPO與中央災难RPO必須分開報告。

中央PITR／舊備份復原時先隔離receiver与ACK路由、强制gateway MQTT重連並清除舊session ACK佇列；server recovery_generation需存於不隨DB回滾的控制狀態。重開前各gateway以當次新隨機challenge完成server-only authenticated session握手，將challenge／generation綁進每批與ACK，edge只接受當前session回覆；舊generation／舊challenge ACK不可刪pending。尚未完成握手的gateway保持本地queue。恢復前已刪除的樣本仍受上述中央RPO限制，不能由Pi憑空還原。

中央TLS、receiver和資料庫需在持續運作主機部署；PC／WSL開發展示路徑不作現場可用性承諾。尚未選定中央正式主機，屬部署前待定項。

## 13. Test Strategy
採RED→GREEN→REFACTOR；邏輯覆蓋≥80%。只使用合成／授權台架資料，電源破壞測試用備用卡與測試DB。

| 用例 | 對應FR | 驗收 |
|---|---|---|
| 配置／型號golden vectors | 2101,2103,2110 | 兩款實機倍率、字序、相電壓、能量，錯profile拒絕；同bus重站號拒絕 |
| 8台排程72h，含1台失聯 | 2102 | §5間隔、CPU/RAM達標，故障不污染其他設備 |
| 7天WAN離線 | 2104,2105 | 8台10秒，共483,840成功樣本可逐ID核對；設備失敗另列缺口 |
| 重啟／程序crash／實體斷電 | 2104,2108 | 已commit ID零遺失；未commit另記；RTC離線冷啟動；至少100次受控電源事件，非壽命保證 |
| 收到PUBACK後中央崩潰 | 2106 | 本地資料仍在，恢復後入庫一次 |
| DB commit後ACK遺失 | 2106 | 重送回committed，DB只有一次寫入 |
| 補傳與live並行 | 2107,2112 | 指定網路條件≥20/s，7h補完，舊資料不冒充online |
| queue滿／磁碟滿／DB損壞 | 2105,2109 | 不刪未送資料，明示缺口、可診斷、無自動空DB假恢復 |
| 假ACK／跨gateway／hash衝突 | 2106 | 拒絕並保留pending；超大payload與timestamp超窗拒絕；同ID改值但沿用claimed hash時拒絕 |
| E2E UI／retention／復原 | 2111,2112 | device身份及L1語意正確；90天窗口與DBrestore保持receipt一致；未來偏移2分鐘樣本跨90天清理邊界不得二次入庫；PITR後舊session ACK不得刪資料 |

目前研究probe只完成PC上的容量與程序crash，**上述硬體／v2用例全部待實作驗收**；既有單設備測試不能抵扣。

## 14. Open Questions
- M70A-262確切官方手冊／韌體／Modbus profile；RPI-M30A完整後綴、韌體。
- HAT品牌與版型、當地SIM／APN／LTE相容性、現場溫度及供電。
- bus長度、現有master、線路端接、是否允許统一baud及站號。
- 中央正式主機與維運Owner；receipt/measurement備份保留與正式SLA。
以上是採購指定SKU／上線前須封閉的項目；本案已提供容量級距與驗收，不把未知項目當作已通過。

## 15. Appendix
參考：[調研與官方來源](../research/2026-09-29-sqlite-edge-capacity.md)、[ADR-030](../adr/ADR-030-edge-durable-receipts.md)、[PRD-0020](PRD-0020-delta-edge-telemetry.md)。

品質自查：15章、三張架構圖、ERD、FR追蹤、量化NFR、10項風險、rollout/rollback、三層測試齊備；API及README/operations同步標為Draft。架構／安全審查紀錄於完成後補註；硬體驗收與stakeholder核定尚未完成，狀態維持Draft。

機型來源補充（2026-09-29）：M70A-262專用官方手冊PDF第42–43頁確認RS485與菊鏈，V1.35 register相容性仍待確認；M30A_120/121手冊p37確認19,200預設／8N1。來源、端子及注意事項見調研§10。M70A-262的串口格式未確認，§5的19,200/8N1只是台架候選；混接前須確認兩款相同設定。Auto-ID圖示不作最大台數證據。


審查紀錄：2026-09-29架構審查提出receipt未來時戳保留邊界問題，已補retention_until與回歸用例；安全審查提出中央災難RPO及server-side hash重算，已補commit／復原握手與用例。安全復核無剩餘必修。研究程式碼審查確認容量公式與結論一致。以上為文件審查，不是實作或實機認證。

架構復核完成：retention邊界修正已關閉，無新增必修問題；維持Draft／待實作與硬體驗收。

### 15.1 資料對帳與缺口分類（2026-09-29 補充，Draft）
對應FR-2113～2116；這是本地採集紀錄與中央實際量測的雙向比對，不能只比「已發送筆數」或最大序號。所有頻率／驗收時間是設計目標，尚未實作。

**身份與序號**
- 每台設備新增stream_id（UUID）與capture_seq（64-bit正整數）。只有成功持久化樣本才在同一SQLite交易中增加seq，同時寫sample、序號metadata與audit索引；sample_id仍作去重主鍵。
- 一般程序／設備重啟沿用stream及seq；DB重建、還原舊備份或identity變更必须啟用新stream，登錄前一stream的未知結尾，不重用舊seq。migration一次性指定既有待送列的stream/seq並記錄。
- 序號不會揭露未成功取得的採樣。另記config_revision與生效採樣時段、poll attempt結果及缺口區間；依各config_revision實際啟用的採樣間隔與排程槽計算應採筆數（詳§15.2），不固定除以10秒，維護停採、夜間無回應、timeout、queue_full、clock_untrusted、gateway unavailable各自分類。夜間無回應不能填成0。
- 中央在Pi不可達時只能標記gateway unavailable／原因待確認；無法單靠斷心跳區分4G斷線與Pi斷電。恢復後用本機記錄補分類；未提交的最後一次讀取記unknown，不能假稱查得原因。

**對帳節奏與內容**
- 每30秒發送獨立health heartbeat，90秒未收到標記gateway unavailable；不把歷史補傳當heartbeat。heartbeat包含目前連線session、各device last poll/last success、queue總量、時間品質、stream高水位，禁止直接記committed。
- 每5分鐘封存當期manifest；同一stream／range的sample成員封存後不可改。每device含seq起迄、筆數、依seq排序的(seq,sample_id,payload_hash)摘要、window_id、manifest_version、config_revision及scheduled/read_failed/storage_failed/unknown統計。空窗口也傳manifest，避免末尾整段遺失無從發現。封存與本機高水位以一致SQLite快照產生。
- 只對已封存範圍對帳，避免把仍在採集的新資料誤判漏送；正常連線下封存後≤60秒完成核對。重連120秒內開始pending重送與對帳，每日重查最近7天sealed windows；速率受有界分頁限制，不承諾日掃時間早於實測。
- 筆數與摘要相同先判manifest相符；不同時逐頁比對ID/hash集合，每頁≤256項且≤64KiB，回覆missing_ids、hash_conflicts、extra_ids。最高已收到seq只是觀察值；只有連續區間已核對才可提高verified_through，不能用MAX(seq)直接宣稱之前全到。

- stream_id/capture_seq/window_id/config_revision是§8不可變sample schema的一部分，server在首次ingest驗證並持久化，不可只信後來manifest聲稱。stream綁gateway/device；config revision與生效區間須已註冊。window_id在採集前配置並持久化，sample提交時綁定；封存後不得插入新成員，重送既有成員允許。中央首次收到manifest時可有missing成員，後續遲到資料依原sample身份入庫，不修改manifest。
- receipt另加唯一(gateway_id,device_id,stream_id,capture_seq)，並建立(gateway_id,device_id,stream_id,window_id)查詢索引；同seq不同sample_id或window/config/hash不一致均conflict。中央容許合法亂序，獨立重建成員清單與digest，canonicalization測試涵蓋所有新增欄位。
**中央核對對象與修復**
- 核對receipt身份／hash及實際量測列：v2量測需有可索引的gateway_id/sample_id關聯欄位（舊v1列可NULL），且一個v2 sample只對應一列；沿用receipt唯一鍵保護插入。索引設計在migration時按hypertable分區限制驗證，不假稱既有表已具備。
- 從已驗證canonical snapshot計算預期四欄投影，對照實際time/device_id/L1 V/L1 A/total kW/lifetime kWh；不能只看到receipt就宣稱歷史表存在，不能盲目信任存入的payload_hash而不檢查欄位。
- 中央缺sample且Pi仍有pending：重送原ID及原內容。中央receipt存在但量測缺列：從receipt保存的snapshot，以同一身份、交易與冪等修復規則重建缺列。若已有列值不同則標conflict、保留證據，禁止自動覆寫。
- 首次ingest、重送與repair皆需對(gateway_id,sample_id)使用同一交易鎖。先原子建立／取得receipt（競爭插入由唯一鍵收斂），再SELECT FOR UPDATE並驗證hash與不可變身份；在鎖內重新查實際量測：0列才插入、1列則驗證、>1列標conflict且不自動刪除。不可在receipt已存在時只靠其唯一鍵防止量測雙插入；dedup「已存在」也不可跳過缺列檢查。
- 補傳後重新核對；缺筆歸零且hash相符才標reconciled。pending送達不等於所有歷史窗口都已對帳。
- 本機在committed ACK後可刪量測payload，但audit索引(sample_id/stream/seq/hash/window)保留至少7天；中央receipt snapshot依§7保留90天以上，支援中央投影修復。本機已刪payload且中央receipt與量測皆失去時，只能識別缺筆並列unrecoverable，需備份救援；不得宣称此機制可重建所有資料。
- gateway未取得的瞬時讀值無法靠重送重建；只有設備提供經確認的歷史記錄API才可另做回讀，目前兩機未驗證。累計kWh差值可作合理性檢查／缺口總發電量線索，須處理reset/rollover，不能還原每10秒的功率曲線。

**容量、保留與安全**
- audit另設256MiB budget，基準最多600,000筆sample索引及20,000個manifest/區間摘要，涵蓋8台/10秒/7天；以實測確認索引平均占用。計入既有4GiB outbox與8GiB data budget，不能扣掉600,000筆pending保證。完整採購容量仍須連journal一起重驗。
- 超7天的audit窗口以out_of_audit_window表示，仍pending的樣本不因audit到期被刪；容量不足須明示audit_degraded並告警，不把未核對改為成功。已核對記錄才按保留政策清除；未核對超窗不得悄悄當成無缺口。
- 核對請求只針對自有gateway/device/已登錄stream與受限範圍，不允許SQL／檔案路徑／OT指令。保留mTLS/ACL、當前session_challenge、recovery_generation、request_id綁定；retained、舊session或不匹配回覆拒絕。
- reconciliation相符回覆不能當committed ACK刪queue，正常刪除仍走§8逐筆ID/hash驗證。hash_conflicts／extra_ids只是告警，不授權遠端刪中央或本機資料。

**驗收與介面顯示**
測試逐項涵蓋：中間缺101/104、末尾整段漏送、亂序、重複、ACK遺失、同筆數不同ID、同ID異內容、同stream/seq不同ID、stream/window/config欄位被竄改、兩個repair並行／ingest與repair並行只留一列、manifest本身遺失重送、設備poll失敗、Pi重啟、DB還原開新stream、時鐘跳動／採樣設定變更、receipt存在但量測被刪、兩端payload均消失、跨gateway偽造核對、滿audit與7天保留邊界。所有用例比對獨立expected ledger，補傳不增加重複列。
EMS按設備／時間窗呈現：應採、已採、已入庫、待補傳、採集缺測、內容衝突、未知／不可恢復、最後核對時間。分開計算採集覆蓋率=有效採樣/應採，以及交付完整率=匹配入庫/已持久化採樣；分母0顯示N/A，未知窗口不計為100%。

示例：Pi封存100～105共6筆；中央只有100、102、103、105，應列缺101及104。若Pi仍留兩筆則補傳後重新比對；另一種情況是10:00:10的poll失敗：該時間槽不會生成capture_seq，應由採样缺口記錄呈現；不可用成功樣本序號推論每個10秒時間槽都已採到。




對帳補充審查完成：2026-09-29架構與安全審查通過；stream/sequence嚴格schema與並行修復鎖定問題已修正。YAML與PRD契約一致性檢查通過；未實作或部署對帳功能。

### 15.2 可選採樣間隔與容量級距（2026-09-29，Draft）
本節補充並限制先前「8台／10秒／7天」數字的適用範圍；FR-2117～2118。目標是EMS可選真實採集頻率，非只讓圖表每秒重畫。現有單設備config雖接受poll_interval整數1..3600，edge.py仍為poll後wait(interval)，本規格中的固定週期、多設備混用與EMS設定回報尚未實作。

**設定與時間語意**
- 每台device的sampling_interval_s提供1、5、10、15、30秒，預設10。第一版EMS只開這五個preset；其他整數秒先保留資料模型擴充性，不因舊config接受就宣稱已驗收。每次取得目前核准profile的一份完整快照，暫不拆成各訊號不同週期。
- requested_interval_s是操作者要求；effective_interval_s是gateway已驗證、持久化並回報實際啟用值。介面分別呈現驗證中／待套用／已生效／拒絕與原因；未收到可信gateway applied回報不可顯示已套用。可批次選設備，但各bus整體組合都須通過。
- 採樣間隔決定讀設備與保存原始資料；upload batch只決定封包傳送，不丟掉中間樣本；UI refresh決定畫面更新；chart aggregation決定一分鐘等視覺桶。四者不可共用一個含糊的「更新間隔」設定。1秒原始資料即使5秒刷新畫面仍保留全部5筆，不以平均值取代。
- 固定週期採用monotonic due time，記錄slot_due、actual_poll_start／end及UTC sampled_at；同bus錯峰、一時只一request。量測包內各register是依序讀取，1秒poll不代表所有訊號同步更新或設備內部1Hz刷新；需驗證兩款profile的實際更新行為。
- 來不及的slot記overrun／缺測，不排隊累积大量過時poll，不以同一舊snapshot重複寫成新樣本，不默默把1秒改成5秒。健康情境目標每device採樣間隔p99≤1.2×T；poll deadline、離線probe和不可中斷操作須符合最短T，不能直接沿用10秒基準的1秒timeout。

**更改設定、離線與對帳**
- 操作權限限授權OPS／管理者，可選device與preset，不提供任意serial地址、SQL或OT寫入。中央與gateway都驗證allowlist、授權及容量；使用預期current_revision做版本比較，拒絕過期／重放／競爭更新；限制每gateway每分鐘最多一次完整設定套用。
- 生效以gateway本地持久化原子切換為準：完成／分類舊revision最後一個slot，封存舊window，再開新window；持久化applied_revision、生效邊界、scheduler epoch與monotonic/UTC對照。正常改週期不重置sample_id或capture_seq；後續樣本帶新config_revision。
- 僅畫面選值不改現場狀態。離線時保留舊effective值，requested標待套用；恢復後重新驗證當時bus/磁碟/queue容量，通過才生效。遠端設定通道尚未實作，不能把MQTT samples/reconcile topic當配置命令通道。
- gateway保留版本與applied回報直至中央持久化確認；中央按已登錄revision接納。若sample先到而revision事件後到，回retryable並保留edge pending，不因合法事件亂序永久拒絕。CPU／磁碟不足時拒絕套用並保留舊revision，不自動清除backlog。
- 期望筆數按每個revision生效的半開區間與排程槽計算；交界不重複計數，config切換也不能抹掉原本應採卻overrun的slot。範例：完整一分鐘10秒共6槽，下一分鐘1秒共60槽，共66筆應採，不固定用120/10。重啟離線無可信排程證據則記unknown，不虛構精確缺筆原因。

**bus能力檢查**
- 每個profile記錄實測完整poll成本與設備允許的最低間隔，包含request間隔、serial turnaround、重試／timeout策略。19,200 baud或站號上限不足以推出可用台數。
- 以保守成本C_i與週期T_i估算bus占用U=Σ(C_i/T_i)，提案先留40%餘裕，U≤0.60只是篩選條件；仍須驗證不可搶占阻塞、慢設備、CPU／SQLite延遲與故障probe，通過72h混合負載測試才核准該組合。
- 純示例：若每台完整poll成本為0.5秒，8台10秒占用40%，8台5秒為80%，8台1秒為400%。後兩者不通過此假設下的60%門檻；這不是兩款Delta的實測速度。可減少每bus台數、增加獨立bus，或選較慢週期；不把8台任意間隔當成保證。
- 混用示例：1台1秒、7台10秒，總資料率為1.7筆/s，7天1,028,160筆；bus可行性另外按成本與deadline判斷，不能僅看資料庫容得下。

**7天容量：8台全部採同一間隔**
2KiB／筆是含索引的工程假設，非硬體量測；未含audit、journal、OS與磁碟保留空間。

| 每台間隔 | 每日筆數 | 7天筆數 | 資料＋索引預算 | 建議pending cap |
|---:|---:|---:|---:|---:|
| 1秒 | 691,200 | 4,838,400 | 9.229GiB | 6,000,000 |
| 5秒 | 138,240 | 967,680 | 1.846GiB | 1,200,000 |
| 10秒 | 69,120 | 483,840 | 0.923GiB | 600,000 |
| 15秒 | 46,080 | 322,560 | 0.615GiB | 600,000 |
| 30秒 | 23,040 | 161,280 | 0.308GiB | 600,000 |

混合頻率以λ=Σ(1/T_i)，7天rows=ceil(604800×λ)計算；pending cap=max(600000,ceil(rows×1.24/10000)×10000)，約24%列數餘裕。不得把目前config最大1,000,000誤當6,000,000已可用。既有60萬cap若8台1秒僅20.83小時；5秒僅4.34天。

採購／驗收空間提案：10/15/30秒沿4GiB outbox、8GiB RW data；8台5秒需至少8GiB outbox、16GiB RW data；8台1秒需至少32GiB outbox、48GiB RW data，建議128GB工業／耐寫儲存並評估Pi 4／工業gateway。所有數字包含留白的預算，不代表換卡或換Pi就能解決bus瓶頸；以實機journal高水位與寫入耐久驗收。

audit索引cap至少等於對應pending cap；budget按列cap與實測索引成本調整，10秒基準256MiB、5秒先估512MiB、1秒先估2.5GiB，仍須實測。manifest数量按設備數／5分鐘封存及實際revision切換另計，不能只放大sample cap。套用較慢間隔不直接縮減queue／audit配額或刪舊資料；只有舊資料到期／已確認且新7天容量仍成立時才允許縮限。

切到較快間隔之前，同時計算現有pending bytes/rows加「接下來7天」的新資料與audit、journal保留空間；若混合新舊資料會超限則拒絕／延後套用，不以清空舊queue換空間。

**補傳能力也需按週期驗證**
若中央實際入庫能力μ固定20筆/s且持續採樣，追趕時間=backlog/(μ−λ)，μ≤λ時無法追上：
| 8台週期 | 7天backlog補完時間（μ=20的假設） |
|---:|---:|
| 1秒 | 112小時 |
| 5秒 | 約14.61小時 |
| 10秒 | 7小時 |
| 15秒 | 約4.60小時 |
| 30秒 | 約2.27小時 |

因此§5「7小時補完」僅適用10秒基準；若8台1秒仍要求7小時補完，需μ≥200筆/s，必須另升級目前40/s admission limit、2 batches/s、網路與中央服務容量並驗收。本次不擴大已提案的rate limit或宣稱20/s為實機結果。

**驗收**
五個preset與混合週期各有scheduler/容量測試；拒絕非法值／未驗證profile／超bus成本／磁碟不足；涵蓋10→1→30秒切換、離線requested不等於effective、revision亂序／競爭／重啟、1秒窗口超256筆分頁、不同採樣間隔的缺筆計數、時間回撥、slot overrun與單台失聯。每組輸出requested/effective/實測間隔p50/p95/p99、poll成本、coverage與backlog；固定期採樣數、資料與audit容量、補傳吞吐必須同時通過，不能以選單可選視為驗收。


採樣間隔補充審查完成：2026-09-29架構／安全審查無新增必修問題；五種頻率的容量／補傳公式與YAML preset一致性已驗證。此為Draft規格，不代表EMS設定UI、gateway套用或任意1秒硬體組合已完成。
