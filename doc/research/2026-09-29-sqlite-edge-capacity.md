# SQLite 是否足夠：Delta 現場採集容量與可靠性調研
日期：2026-09-29｜狀態：研究結論與設計提案，未部署｜適用：M70A-262、RPI-M30A、Pi + SIM7600G-H

## 決策摘要
**建議保留 SQLite 作為樹莓派的待送佇列，中央繼續使用 PostgreSQL / TimescaleDB。** SQLite 適用本機嵌入式儲存；目前更迫切的問題是多設備排程、斷網容量、電源與 SD、以及「中央入庫才確認」的交付契約。[SQLite 適用情境](https://sqlite.org/whentouse.html)

建議採購／開發基準為 **8 台逆變器／閘道器、各 10 秒採樣、7 天斷網緩存**，一條 RS485 bus；16 台則以兩條 bus 各 8 台為擴充方案。這些是工程目標，不是現有程式或實機已達成的保證。现有版本只支援一個 device_id、一個 poller。

使用者已指定 M70A-262、RPI-M30A。V1.35 首頁列有 M30A、M70A_260，未明列 M70A_262；**262 的 register map／韌體相容性必須取得台達確認或實機封包證據**，不能以同系列替代。RPI-M30A 仍需銘牌完整後綴與韌體才能鎖定 profile。[台達官方協定](https://solarstorageaccount.blob.core.windows.net/pvi/manual/modbus/DELTA_Three-phase_products_protocol.pdf)

正式需求、資料模型、驗收與採購條件見 [PRD-0021](../prd/PRD-0021-multi-device-edge-reliability.md)；決策見 [ADR-030](../adr/ADR-030-edge-durable-receipts.md)。

## 1. 調研方法與證據分級
本次回答五個問題：
1. 現有程式究竟能接幾台，資料可能在哪裡遺失？
2. 7 天、30 天與更高頻採樣的儲存量是多少？
3. SQLite 在斷電、重啟、併發下是否適合？
4. RS485 輪詢與 4G 補傳，哪個才是限制？
5. 應採購什麼硬體、用什麼測試驗收？

方法：逐檔稽核本機 WSL 權威程式、查閱下列官方文件與指定版本原始碼、以隔離 Docker 測試 SQLite，並交叉審查架構與儲存結論。使用 deep-research 工作流；本環境無可用 Exa/Firecrawl，改用 web 搜尋與官方全文。未以行銷吞吐或 PC benchmark 推估 Pi 保證台數。

證據分級：
- **確認事實**：本次讀取的程式／執行中 runtime、官方文件明文、可重現的研究結果。
- **計算**：給定設備數、頻率、大小與 RTT 的公式結果。
- **設計目標**：尚需在指定 Pi、卡片、4G 與逆變器上驗收的數字。
- **未確認**：M70A-262 協定適用性、M30A 完整型號與韌體、HAT 版型、現場纜線／串口設定。

## 2. 現有系統實際能力與缺口
| 項目 | 本次確認狀態 | 影響 |
|---|---|---|
| 多設備 | config / edge 只有一個設備與 poller；outbox 綁一個 device_id | 不能把現在版本直接配置成 8 台 |
| 暫存 | queue_limit 預設 10,000；最大配置 1,000,000 | 單台 10 秒名義上僅 27.8 小時 |
| 週期 | 完成讀取後再 wait(10) | 實際週期大於 10 秒，需改定時排程 |
| 本機 DB | Python 3.11.15 / SQLite 3.46.1；DELETE / FULL；page 4096 | 目前未啟用 WAL，不可套用 WAL 預設的說法 |
| 容量判斷 | 每次 enqueue 執行 COUNT(*)；有 row cap | 沒有磁碟餘量、最大待送年齡與 schema 升級策略 |
| 交付 | 一筆等待 MQTT PUBACK 後刪除 | 不代表中央資料庫已提交 |
| 中央管線 | 開發 broker persistence=false；Telegraf 1.30.3 未開 persistent_session | broker／ingest／DB 之間仍有遺失窗口 |
| 去重 | 量測表 time/device_id 是普通索引；無 sample_id 唯一鍵 | 重送可能重複，rowid 不能當全域 ID |
| 時鐘 | field 要 OS 同步標記與遞增 UTC | 無 RTC 且離線冷啟動時可能拒絕新採樣 |
| 詳細訊號 | rich snapshot 只在待送佇列／CLI；中央是四欄 | 不等於完整三相、告警、MPPT 都已進歷史庫 |

本機證據：
[config](../../services/delta/delta_device/config.py)、
[edge](../../services/delta/delta_device/edge.py)、
[delivery](../../services/delta/delta_device/delivery.py)、
[publisher](../../services/delta/delta_device/publisher.py)、
[poller](../../services/delta/delta_device/poller.py)、
[ingest](../../services/ingest/telegraf.conf)、
[broker](../../infra/mosquitto/mosquitto.conf)、
[SQL](../../infra/timescaledb/init.sql)。

SQLite 在此是 outbox：收到成功確認後刪除，**不是保留全部現場歷史的資料庫**。若要本地歷史 30 天，需另訂已送資料保留策略。

## 3. 容量：SQLite 不是當前瓶頸
公式：待送筆數 = 設備數 × 86,400 × 斷網天數 ÷ 採樣秒數。一笔代表一台設備的一次完整快照，不是每個欄位各算一筆。

規劃暫以 **2 KiB／筆，含資料與索引平均占用**。這是預算假設，必須把未來 compact record 限制在 1 KiB 並實測確認；目前程式允許 16 KiB snapshot，因此 2 KiB 不是現有任意輸入的保證上限。

| 台數 | 每台週期 | 斷網 | 筆數 | 2 KiB／筆預算 |
|---:|---:|---:|---:|---:|
| 1 | 10 秒 | 7 天 | 60,480 | 0.115 GiB |
| 8 | 10 秒 | 7 天 | 483,840 | 0.923 GiB |
| 16 | 10 秒 | 7 天 | 967,680 | 1.846 GiB |
| 8 | 10 秒 | 30 天 | 2,073,600 | 3.955 GiB |
| 8 | 1 秒 | 7 天 | 4,838,400 | 9.229 GiB |

基準規格：600,000 筆容量、4 GiB outbox 空間預算、至少 8 GiB 持久化 data partition、64 GB 工業／耐寫 microSD。600,000 筆約提供 8.68 天的名義容量；7 天保證還依賴資料大小、空間餘量、持續供電與健康儲存。超限不能悄悄刪除未送資料，必須明示資料缺口。

### 隔離實測
[測試程式](../../scratch/sqlite-research-20260929/benchmark.py)／[原始 JSON](../../scratch/sqlite-research-20260929/results.json)。

環境：WSL2 x86_64、Docker 暫存檔案系統、Python 3.11.15、SQLite 3.46.1；**不是 Pi，也不是 SD 卡**。使用目前 outbox schema，合成一筆 129 B ILP + 391 B JSON；批量填入只量大小。

| 筆數 | DB 實際 bytes | 約 MiB |
|---:|---:|---:|
| 10,000 | 5,881,856 | 5.61 |
| 60,480 | 35,491,840 | 33.85 |
| 483,840 | 283,840,512 | 270.69 |

因此典型 fixture 下 8 台 × 7 天約 **271 MiB**。新增 sample_id、hash、索引、更多欄位會增加大小，採購不能只留 271 MiB。COUNT(*) 在最大測試集 p95 約 29.94 ms，提示應改交易內維護計數或採其他有界策略；不能推論 Pi 延遲。

另跑 250 次 enqueue→select→ACK delete：
- DELETE/FULL p95 5.673 ms。
- DELETE/EXTRA p95 37.490 ms。
- WAL/FULL p95 40.677 ms。

這是單寫入、每次開關 connection、無網路的短測試。WAL close/checkpoint 與檔案系統行為影響結果；**不能据此宣稱 DELETE 普遍比 WAL 快，也不能據此承諾 Pi 吞吐**。

程序崩潰測試在 DELETE/EXTRA 與 WAL/FULL 各留下 100 筆已提交資料、排除未提交插入、integrity_check=ok。僅驗證 process exit；未切斷 OS cache 或實體電源，不算硬斷電驗收。

## 4. SQLite 的可靠性條件
官方支援 WAL/FULL 與 rollback journal 的同步機制；DELETE/EXTRA 增加刪除 journal 後的目錄同步。建議低寫入基準先採 **DELETE + EXTRA、集中序列化寫入、短交易**；這是本案設計取捨，非通用效能定律。若後續讀寫競爭有實測需求，才改 WAL/FULL。[同步設定](https://sqlite.org/pragma.html#pragma_synchronous)

WAL 仍只有一個 writer，且需管理 checkpoint。官方揭露 WAL-reset race：3.7.0–3.51.2 受影響，3.51.3+ 或指定 3.44.6／3.50.7 backport 修復。**本機 3.46.1 目前用 DELETE，不受這個特定 WAL 問題路徑影響；啟用 WAL 前必須核實 runtime／發行版修補**。[WAL 與修正說明](https://sqlite.org/wal.html)

同步承諾依賴儲存裝置與 OS 正確執行 flush。突然掉電可能破壞 SD controller 的其他頁面；不得刪除 crash 後的 journal/WAL，不可把 DB 放在網路共享磁碟。[損壞原因](https://sqlite.org/howtocorrupt.html)

實務要求：
- SQLite 位於本機持久化 ext4 分割區；若 root 用 RAM overlay，outbox 必須排除。UPS 必須可通知服務停止採樣並完成關機。[Pi 檔案系統韌性白皮書](https://pip-assets.raspberrypi.com/categories/685-whitepapers-app-notes/documents/RP-003610-WP/Making-a-more-resilient-file-system)
- 啟動讀回 runtime / journal / synchronous / schema_version；不只看 pip 或 Python 版本。
- 異常關機後檢查 DB；檢查失敗保留檔案、告警、人工處理，禁止自動清空重建。[資料救援限制](https://sqlite.org/recovery.html)
- 活躍資料庫備份用 SQLite backup API，不單獨複製正在寫入的 .db。[Online Backup](https://sqlite.org/backup.html)
- 程序 kill 測試與真實電源中斷分開驗收，獨立 ledger 比對 sample_id。[SQLite crash testing](https://sqlite.org/testing.html#crash_testing)

SD 寫入壽命不能由 271 MiB 直接換算：payload、SQLite journal、filesystem、NAND 寫入量不同。Kingston 工業卡頁面的最高 TBW 隨容量／條件而異；Samsung Endurance 錄影時數也不是 SQLite 隨機寫入壽命。[Kingston 工業 microSD](https://www.kingston.com/en/memory-cards/industrial-grade-microsd-uhs-i-u3)、[Samsung 測試條件](https://www.samsung.com/sg/memory-storage/memory-card/memory-cardpro-endurance-256gb-mb-mj256ka-apc/)

## 5. 幾台設備：先看 RS485 與型號
Modbus 位址數不等於可承諾台數。標準 serial address 1–247；Delta 文件 p6 使用 PCS ID 1–254。規格先用共同子集 1–247，現場 8 台分配 1–8。RS485 32 unit loads 是電氣負載概念，不能等同 32 台所有型號都能以 10 秒完成輪詢。[Modbus Serial 規範](https://modbus.org/docs/Modbus_over_serial_line_V1_02.pdf)、[TI RS485 unit loads](https://www.ti.com/document-viewer/lit/html/SSZTBJ6)

目前一般三次 FC04：40995×1、49152×13、53248×9；8-byte requests 共 24 B，responses 共 61 B，總 85 B。在 19,200 baud / 8N1，純線路時間約 44.3 ms。這不包含靜默間隔、處理延遲、timeout、重試、額外 energy scale 或 temperature 讀取；不能用 44 ms 直接算最大台數。[目前 poller](../../services/delta/delta_device/poller.py)、[Delta protocol p6–7](https://solarstorageaccount.blob.core.windows.net/pvi/manual/modbus/DELTA_Three-phase_products_protocol.pdf)

8 台目標須符合：健康設備完整讀取 p95 ≤ 0.5 秒、bus scan p99 ≤ 8 秒、每台排程間隔 p99 ≤ 12 秒。每 bus 一個 owner，禁止多 process 爭同一 serial port。斷線設備需有整次 poll deadline 與退避，不能每個 register 各等 3 秒把整條 bus 拖住。

型號閘門：M70A-262 與 RPI-M30A 各維護 profile、韌體、參數、獨立 golden vectors；倍率、低字在前、相／線電壓、累計電量單位須對現場顯示交叉驗證。未確認 profile 不套用預設假值。TCP transport 保留；不宣稱兩款本體原生提供 Modbus TCP，必要時另用相容 RTU/TCP gateway。

## 6. 4G 補傳與中央確認比 DB 換型更重要
PUBACK 是 broker 這一跳的確認，不是 PostgreSQL commit；MQTT QoS2 也不等於跨資料庫交易。[OASIS MQTT §4.3.2](https://docs.oasis-open.org/mqtt/mqtt/v3.1.1/os/mqtt-v3.1.1-os.html)

現有 batch_size=100 是每批取 100 列，仍每筆個別等 PUBACK，再等 1 秒。忽略磁碟耗時的理想吞吐：
μ = B / (B × RTT + 1)，B=100。

| RTT 假設 | 上傳筆／秒 | 8 台每 10 秒，7 天 backlog 的追趕時間 |
|---:|---:|---:|
| 0.2 秒 | 4.76 | 約 33.9 小時 |
| 1 秒 | 0.99 | 約 29.5 天 |
| 2 秒 | 0.50 | 小於產生率 0.8，無法追上 |

以上是情境公式，非 SIM7600 測量。應採可控批次與 in-flight window；規格訂 **總入庫 20 筆／秒**，同時新增 0.8 筆／秒，483,840 ÷ (20−0.8) = **7 小時**補完。驗收網路條件列於 PRD，不能以 4G 行銷峰值當保證。

最小可靠鏈：
採集 → SQLite commit（stable sample_id）→ MQTT/TLS → 接收服務驗證 → receipt＋量測同交易 commit → application committed ACK → 刪本地待送列。
相同 ID 重送回覆原成功結果；相同 ID 不同 hash 拒絕。這是 at-least-once 傳輸搭配入庫去重，不泛稱端到端 exactly-once。

Telegraf 1.30.3 persistent_session 可以延後 subscriber ACK，但不能撤回 producer 已收到的 PUBACK；PostgreSQL output 某些永久錯誤會丟棄 sub-batch。故只改一個設定不足以提供逐筆入庫保證。[MQTT consumer 原始碼](https://github.com/influxdata/telegraf/blob/v1.30.3/plugins/inputs/mqtt_consumer/mqtt_consumer.go#L247-L285)、[PostgreSQL output 原始碼](https://github.com/influxdata/telegraf/blob/v1.30.3/plugins/outputs/postgresql/postgresql.go#L261-L307)

Mosquitto persistence 是週期性／關機保存，不是每次 PUBACK 的 DB 持久化承諾。[Mosquitto 配置](https://mosquitto.org/man/mosquitto-conf-5.html)

## 7. 選型比較
| 方案 | 本案判斷 | 何時改變 |
|---|---|---|
| Pi SQLite + 中央 PostgreSQL/Timescale | 建議；本機 durable queue、中央共享歷史各司其職 | 需重估高寫入或多服務強競爭 |
| Pi 也裝 PostgreSQL | 當前不足以證明值得增加服務維運 | 本地多程序／多使用者需長期共享查詢 |
| DuckDB / Parquet | 適合批量分析／歷史匯出，非首選逐筆 outbox | 另加本地分析需求 |
| JSON/CSV 檔案 | 易讀，但須自行處理部分寫入、去重、ACK 刪除、復原 | 只作診斷匯出 |
| 僅依賴 MQTT spool | 難以表達量測取得至中央 commit 的責任 | 仍需明確應用層確認 |

以上為工程判斷，依 [SQLite 適用範圍](https://sqlite.org/whentouse.html)、[DuckDB concurrency](https://duckdb.org/docs/lts/connect/concurrency)。PostgreSQL 也依賴 storage flush；換 DB 不會解決 SD 或電源問題。[PostgreSQL Reliability](https://www.postgresql.org/docs/current/wal-reliability.html)

## 8. 採購建議與下一階段
先買一組驗證套件：**Pi Zero 2 W、確認版型的 SIM7600G-H、隔離 USB–RS485、64 GB 工業／耐寫卡、匹配電源與可通知關機的 UPS、RTC＋電池、機箱／端子／天線／SIM**。8 台不是 USB adapter 要買 8 個；同一相容 RS485 bus 串接站號不同的設備。

Zero 2 W 的 512 MB RAM 為正式實機驗收條件；用 Lite OS＋原生 systemd，圖表／中央 DB 留在 EMS。若已規劃 16 台、兩 bus、USB 裝置較多，Pi 4 Model B 2 GB 更有擴充餘裕；此為配置建議，並非 SQLite 需求。[Zero 2 W](https://www.raspberrypi.com/products/raspberry-pi-zero-2-w/)、[Pi 4 specs](https://www.raspberrypi.com/products/raspberry-pi-4-model-b/specifications/)

SIM7600G-H 是模組識別，尚未確定整板。**Waveshare HAT (B) 已帶 USB Hub**；不要在未確認板型前重複買 Hub。電源應按 Pi＋modem 發射＋RS485＋UPS 的整組負載確認；Zero 系列缺低壓偵測，沒有低壓 log 不是供電合格證據。[HAT (B) Wiki](https://www.waveshare.com/wiki/SIM7600G-H_4G_HAT_%28B%29)、[Pi 電源文件](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#power-supply)

執行順序：
1. 核對兩款銘牌／韌體與台達 register map，取得各一台讀值。
2. 補多設備 scheduler 與 bounded SQLite outbox。
3. 實作中央 committed receipts／去重與 TLS 身份綁定。
4. 指定 Pi/SD 上跑兩型設備、7 天斷網、補傳、硬斷電及磁碟滿驗收。
5. 小規模現場 canary 通過後，才能對外標示「8 台／10 秒／7 天」。

## 9. 研究範圍與尚未完成
本次完成官方來源交叉研究、現況稽核、隔離 SQLite 容量／程序崩潰探針與可驗收規格。未修改採集服務、未更新公開站、未跑真實 Pi／SIM7600／RS485 斷電試驗。上述現場目標的信心為「有計算與設計依據，待硬體驗證」；SQLite 架構適用性信心高，M70A-262 profile 相容性仍未確認。

## 10. 指定機型補充：官方手冊查核
使用者補充型號後，本次另找到並讀取：
- [M70A-262 專用繁中手冊](https://mydeltasolar.deltaww.com/manual/product/inverter/zh-tw/UM_M70A_262.pdf)：PDF共86頁，印刷頁87–172；PDF第42／43頁（印刷128／129）載有RS485接線與菊鏈，末端逆變器的內建120Ω終端設為ON。這證明RS485硬體介面，並未證明V1.35暫存器相容。
- [RPI-M30A 官方英文手冊](https://solarstorageaccount.blob.core.windows.net/pvi/manual/product/inverter/en-us/UM_M30A.pdf)：所讀版本涵蓋M30A_120／121，p37列9600／19200預設／38400、8N1；p47要求不同設備ID。使用者尚未提供M30A後綴。
- [M70A-262 官方產品頁](https://www.deltaww.com/zh-TW/products/Photovoltaic-Inverter/5393)。

兩款手冊的RS485端子皆列1=12V、2=GND、3/5=DATA+、4/6=DATA−；施工仍以實體端子及對應版本手冊為準，**12V不可接Pi GPIO**。內建終端只依bus兩端配置，不在所有逆變器都打開。M70A-262連線章節未取得可核實的baud/parity值，19,200/8N1仍是測試候選，不是該款已確認預設。

官方目錄泛稱M70A的英文手冊實際涵蓋_260等版本，繁中一般連結目前可能指向_263，故本研究使用明確_262手冊，不以其他後綴代替。若現場已有資料收集器作master，須移交bus owner或透過正式gateway整合，不能讓Pi任意成為同bus第二master。

研究限制補充：probe的p95以排序後floor((n−1)×0.95)取值，COUNT僅10次，因此只作粗略延遲線索。中央commit ACK能關閉正常傳輸的遺失窗口，但中央磁碟損毀／還原舊備份仍有獨立災難RPO；PRD明訂WAL／backup與復原握手，不能將本機SQLite durability等同全系統任何事故都零遺失。

## 11. 採樣間隔需求更新（Draft）
依使用者補充，EMS應提供每設備1／5／10／15／30秒，預設10秒；可混用但須經bus與儲存／補傳能力檢查。完整容量矩陣與套用語意見[PRD-0021 §15.2](../prd/PRD-0021-multi-device-edge-reliability.md)。原報告8台10秒7天是基準，不能外推到8台1秒。8台1秒7天=4,838,400筆，2KiB/筆約9.229GiB；audit、journal與保留空間另加。目前僅規格更新，未改現場採集或EMS選單。
