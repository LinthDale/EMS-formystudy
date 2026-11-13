# Delta 三相變流器：模擬器、解析器與邊緣採集

依 Delta Protocol Definition **V1.35（2025-11-06）** 實作唯讀第一階段。
2026-09-29 比對[原廠 PDF](https://solarstorageaccount.blob.core.windows.net/pvi/manual/modbus/DELTA_Three-phase_products_protocol.pdf)與使用者附件，版本及 SHA-256 相同，未找到較新版。SHA-256：
`2c608619614bc7d14da64ab4be9528ae3506f13b93de7cba1ff5ffb5b7251bfc`。

## 已提供的資料路徑

`Delta TCP/RTU simulator / 現場 TCP 或 RS-485 RTU → Python parser → SQLite → MQTT QoS1 → 既有 Telegraf → TimescaleDB → EMS Monitor`

| EMS 欄位 | 此 Delta profile 的精確語意 |
|---|---|
| voltage | L1 相電壓 V，非線電壓、非三相平均 |
| current | L1 電流 A，非三相總電流 |
| power_kw | 三相總有功輸出 kW |
| energy_kwh | 累計發電量 kWh |

三相個別 V/A/kW/Hz、今日電量、inverter state、選用內部溫度可在 `--once` JSON 查看，也存於待送 outbox snapshot；**現有 EMS 只入庫和顯示上表四欄**。ACK 刪除後不保留 rich snapshot，不是額外歷史資料庫。

只讀 FC04。Base-1 預設轉 PDU address−1；可配置 0/1。Scale Factor IR40995、bit0 override、各群組倍率、exception 2 fallback、energy low-word-first，以及整個 scale register=0 時的 today energy/IR40962 特例均有獨立測試。逾時、短封包、保留倍率碼會拒絕樣本，不補零。溫度 signed int16 為待實際機型確認的 profile 假設，現場預設不讀。尚未涵蓋所有事件碼、DC 多路、控制及59頁完整功能。

## 本機啟動與查看

在 WSL 正式 repo 根目錄：
```bash
# 現有 mosquitto、ingest、DB、device-service、query、BFF 須已在執行。
# 先註冊固定模擬 ID、L1 語意及信號，避免依賴自動 AI 分類。
docker exec -i ems-device-service python - < services/delta/tools/register_demo.py
docker compose --profile delta-demo up -d --build --no-deps delta-simulator delta-edge
docker compose exec delta-edge python -m delta_device edge --config /app/config/demo.json --once
docker compose logs --tail 20 delta-edge
```

本機 [EMS Monitor](http://127.0.0.1:4178/#Monitor)，登入既有帳號後選 **delta-sim-001**。
下拉選單顯示「太陽能逆變器(delta-sim-001)」；註冊 location 保留「模擬設備 | V/A=L1；kW=三相總功率；kWh=累計發電」。
兩個新增服務不發布主機 Modbus port；simulator 僅在 Compose 網路內聆聽5021。既有服務不會因上述 --no-deps 指令重啟。
本機預覽啟動方式沿用 `output/ems-design-preview-20260923/start-preview.ps1`。

模擬器支持 day/night/alarm，以及 `--scale 0x019C` / `--scale absent` / `--address-base 0`。
獨立啟動（預設只綁 loopback）：
```bash
cd services/delta
python -m delta_device simulator --scenario night --port 5021
```
模擬器重啟會將示範累計電量重設為基準值，不能用於計費或壽命電量測試。

停止與回滾：
```bash
docker compose --profile delta-demo stop delta-edge delta-simulator
```
保留資料庫歷史、registry 與 `ems_delta_edge_data` outbox volume；不要執行整組 down -v。

## Raspberry Pi + SIM7600G-H 部署準備

SIM7600G-H 負責 Linux 的 IP 網路；本採集程式不送 AT 指令、不管理 APN。
已知目標機型 DELTA M70A-262／RPI-M30A，模組為 SIM7600G-H；採購規劃 Zero 2 W＋HAT(B)，到貨版型、韌體與接線待核對。
**不能以本機測試視為實體 RS-485、4G 或现场 TLS 已驗收。**

Pi 使用原生 Python **3.9+**，不要求 ARMv6 Docker image。
安裝於 /opt/delta-edge（複製 delta_device/、requirements.txt）並建立 venv：
```bash
cd /opt/delta-edge
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```
由維運建立 delta-edge 系統帳號、dialout 群組、/etc/delta-edge/config.json、/etc/delta-edge/credentials.env；
credentials.env 權限0600/root；不要放repo或shellhistory。
安裝 `deploy/delta-edge.service` 到 /etc/systemd/system，確認 `systemd-timesyncd` 正常同步後啟動。
本服務讀取 `/run/systemd/timesync/synchronized`；若使用 chrony，須由可信 OS 整合產生等價同步檔，不要手動 touch 假裝完成同步。
未同步、來源時間早於2025或倒退／重複時拒絕採樣並記錄，重送既有樣本不改時間。

- RTU：以 `config/field-rtu.example.json` 為範本，19200/8N1，unit 1..247；serial_port 指向**隔離 RS-485 adapter** 的穩定 /dev/serial/by-id 路徑。SIM7600 的 AT serial port 不是 RS-485。
- TCP：`config/field-tcp.example.json`，替換實際 OT LAN IP/port，不把 Modbus 開到公網。
- Field mode 强制 TLS certificate/hostname 驗證，帳密從 DELTA_MQTT_USERNAME / DELTA_MQTT_PASSWORD 讀入；亦可改 cert_file/key_file 使用 mTLS。私有CA設定ca_file。
- 以不同 device_id 和唯一 MQTT client_id 部署每台 Pi；一個裝置一個專用 spool 目錄與 systemd process。field拒絕含 sim 的ID；不可共用同一outbox跑多程序。
- `--once` 僅讀取診斷，不驗證 MQTT 憑證、NTP 或實際上傳鏈路；正式 run 才套用採樣時鐘與publisher檢查。
- `deploy/mosquitto-field.example.conf` 僅為獨立TLS broker範本，不替換現有demo broker。使用者名稱綁device_id的topic ACL還需**接收端核對payload device_id**。此接收端身份綁定未在這一階段實作，是現場上線前的必要工作。

現場驗收須完成：Delta機型暫存器比對／倍率／位址、Pi/HAT版型與供電、RS-485隔離接線終端、SIM/APN及4G outbound、可達TLS broker/ACL/接收端身份綁定、可信時間、斷線重啟回補及48小時資源觀察。此範本目前不是已驗收現場映像。

## 斷線與資料保證

採集與送出分開執行；SQLite先寫入，再傳QoS1，**對應MID收到PUBACK才刪除該列**。
逾時保留樣本，重啟從SQLite恢復，原ILP位元組與UTC微秒對齊時戳不變。
每個操作明確close SQLite連線，spool檔0600、專用目錄0700。
v1行為：預設10000筆（10秒約27.8小時），上限1000000筆；满時拒絕新樣本並記錄queue_full，保留舊樣本；磁碟滿同樣不視為成功。容量規劃需含檔案與flash磨損。opt-in v2已依ADR-045改成最舊淘汰／最新優先，見本文後段。
日誌含sample_queued/pending_rows、sample_rejected、queue_full、broker_ack、delivery_failed；不輸出密碼或原始連線例外。

**PUBACK只代表broker確認。**既有Telegraf記憶體buffer可能在IT端故障時丟失，DB無唯一鍵可消除重複。不能保證端到端零遺失、exactly-once或計費精度；正式要求更強保證須新增DB committed receipt與去重契約。

## 測試與現有驗證證據

```bash
docker build -f services/delta/Dockerfile.test -t ems-delta-test services/delta
docker run --rm -v "$PWD/services/delta:/app" -w /app ems-delta-test \
  python -m pytest tests --cov=delta_device --cov-report=term-missing --cov-fail-under=80 -q
```
涵蓋PDF獨立literal fixtures、真TCP讀寫拒絕、真RTU PTY byte/CRC（非實體RS485）、例外與短讀、queue重啟/容量/FD、field TLS設定、Paho NO_CONN/early ACK、offline時持續採集及原時戳回送。
`tools/verify-ui.cjs` 以本機既有private login檔執行headless Edge；設定NODE_PATH到已有Playwright的執行環境，或DELTA_TEST_BROWSER指定瀏覽器channel。不輸出密碼，證據在 `output/delta-verification/`。
規格：[PRD-0020](../../doc/prd/PRD-0020-delta-edge-telemetry.md)、[ADR-029](../../doc/adr/ADR-029-delta-edge-telemetry.md)。

## RTU 從站：電腦模擬 Delta，樹莓派採集

本模式不需要真實逆變器。請購單的隔離 USB–RS485 現為 **2 組**，電腦與樹莓派各一組。拓樸：

`PC simulator（從站） → USB–RS485 #1 ↔ RS485 雙絞線 ↔ USB–RS485 #2 → Pi Poller（主站） → parser → SQLite → MQTT → 後台 → EMS`

同一 RS485 總線只有 Pi 主站。不要同時接上另一個正在查詢的主站。電腦端只回應 FC04；不主動串流、不接受遠端寫入。RTU 與 TCP 為單次啟動二擇一，RTU 不開 TCP port，既有 Docker demo 仍使用 TCP。

Windows 直接執行 simulator，可使用裝置管理員中的 COM 編號，無需先把 USB 轉接器轉接進 WSL。先安裝 Python 3.11（既有最低版本為3.9），在 PowerShell：

```powershell
Set-Location '\\wsl.localhost\Ubuntu\home\dalelin\synaiq\EMS\services\delta'
py -3.11 -m venv "$env:LOCALAPPDATA\EMS\delta-sim-venv"
$simPython = "$env:LOCALAPPDATA\EMS\delta-sim-venv\Scripts\python.exe"
& $simPython -m pip install -r requirements.txt
& $simPython -m delta_device simulator --transport rtu --serial-port COM5 --baudrate 19200 --unit-id 1 --scenario day
```

COM5 必須換成實際 USB–RS485 的串口。Linux 同樣從 services/delta 執行：

```bash
python -m delta_device simulator --transport rtu --serial-port /dev/serial/by-id/REPLACE_WITH_PC_RS485 --baudrate 19200 --unit-id 1 --scenario day
```

支援 9600／19200／38400 baud，固定 **8N1**，站號1–247（單一模擬站）。預設19200、站號1是模擬設定，不代表已確認 DELTA M70A-262／RPI-M30A 現場設定。保留 `--scenario night|alarm`、`--scale absent|0x019C`、`--address-base 0|1`。只接受本機 COMn 或 /dev/ 路徑；串口不存在、被占用或無權限時應排除錯誤後重新啟動。看到 `simulator_ready transport=rtu` 才開始查詢，Ctrl+C 停止並釋放串口。

到貨後依序驗收：

1. 安裝兩顆 USB–RS485，確認 PC COM、Pi 的 /dev/serial/by-id；勿選 SIM7600 AT port。依轉接器手冊接相同訊號端（例如同款 A+ ↔ A+、B− ↔ B−），訊號參考地依隔離端規格接；不要接5V/12V。兩端終端依內建跳線設定，避免重複並聯。
2. 複製 `config/field-rtu.example.json` 為自己的診斷設定；修改 modbus.serial_port 為 Pi 的轉接器，19200、unit_id=1、address_base=1 與 simulator 一致。
3. Pi 執行 `python -m delta_device edge --config /etc/delta-edge/rtu-lab.json --once`。預期 L1 voltage=230 V、day 三相 power 約8.4–9.6 kW、night=0，state 依情境2/0/4。此指令只驗證採集與解析，不連 MQTT。
4. 單次讀值通過後，再配置隔離測試用的 MQTT 身分與可達 TLS 入口，驗證 Pi SQLite → MQTT → 本機後台 → EMS；最後改用 SIM7600G-H 的4G網路。不要沿用 Compose 專用的 `mosquitto` hostname 或在 field mode 填入 demo ID。測試設備須獨立註冊為模擬用途；既有TCP delta-edge與Pi不可同時用同一device_id送資料。
5. 拔除串口、停掉simulator、斷網／恢復，分別觀察採樣失敗與佇列續送；斷網期間無法採到的值不可當成可補送資料。

此版本仍是 V1.35 唯讀子集；兩款指定 Delta 型號需以其韌體/暫存器文件及真機讀值校驗。Linux PTY 的協定測試已通過，Windows COM 驅動、實體RS485接線與4G均待到貨驗收。現有 MQTT PUBACK 不是 DB committed ACK；新模式不包含 ADR-030 的漏送對帳/去重系統。

詳 [ADR-031](../../doc/adr/ADR-031-delta-rtu-simulator.md)；測試證據見 [validation.md](validation.md)。


## 2026-09-29 Delta demo 一秒採樣與量測誤差（ADR-034）
- `delta-sim-001` 本機 demo 的 `poll_interval=1`，採集用 monotonic 截止時間補償讀取耗時；逾時略過節拍，不補造或密集追趕。
- `DELTA_SIM_NOISE=1` 開啟每秒一致的三相量測誤差：相電壓 σ=1.5V（限 ±4.5V）、相電流 σ=0.15A（限 ±0.45A），功率依三相 V×I 相加。這些為模擬參數，非原廠精度。
- night/alarm 電流與發電功率為零；電量保持基準發電曲線積分，無隨機倒退，情境切換先結算。模擬器重啟仍會回到既有電量基準，新舊資料保留。
- field 範本/預設仍為 10 秒；REST/MQTT/schema、OPS 登入及公開前端版本未變。API 可每秒入庫，畫面刷新/圖表彙整週期獨立。
- 1 秒採樣的 10000 筆 outbox 約 2.8 小時，10 秒約 27.8 小時；PUBACK 非 DB ACK，沒有新增端到端去重/零遺失保證。
- 本次只部署兩個 Delta 服務的既有 standalone runtime，使用 `output/delta-one-second-20260929/compose.yaml`（project=ems，外部既有 network/volume）。主 Compose 正在同步開發 ADR-033 控制介面，僅補上 noise env，沒有將該批尚待驗收的服務一併上線。後續控制介面發布須保留此 env 與 demo 採樣設定。
- 回復：先確認沒有後續部署，再使用同目錄 `demo.before.json` 恢復 demo 設定、`docker compose -p ems -f output/delta-one-second-20260929/compose.before.yaml up -d --no-deps delta-simulator delta-edge`；保留原 queue volume 和 DB 歷史。回復舊 image 會回復原 standalone 程式；不要在 ADR-033 後續上線後盲目套用。


### 一秒 demo 驗證補充（2026-09-29）
新邏輯以 7 項 RED 測試重現缺少 noise/固定節拍能力；GREEN 後完整 Delta 測試共 72 passed、總 line coverage 95.19%，涵蓋 TCP/RTU、協定倍率、情境切換、queue/publisher 及新增噪聲/節拍。
驗收期間另一批 ADR-033 控制介面已上線，本次誤差模型已補入該運行映像，保留控制與認證。`runtime-current.json` 及 simulator.py / edge.py 的運行檔案雜湊已比對一致。
注意：主機 UTC 約每隔一段時間跳快 3.586 秒，容器 monotonic 仍每次前進 1.000 秒；sim-001 與 Delta 都留下同時段缺口。因此驗收列出所有共用缺口、檢查中位間隔為 1 秒，並拒絕 Delta 獨有的缺口；不宣稱 UTC 每秒零缺值，也不補造資料。詳 output/delta-one-second-20260929/clock-probe-result.json。


### 2026-11-12 Windows 實體 RS485 bench（無 Pi）

兩台 USB–RS485 接同一台 Windows PC，COM3 從站／COM4 採集；修正 Windows 短封包後 110/110 成功。獨立 `delta-rtu-sim-001` 的 SQLite 暫存／補送、DB 與 EMS records API 15/15 通過，完整回歸 78 passed、coverage 95.20%。Pi、4G、Delta 真機與長期可靠性仍待驗證；舊紀錄的「Windows COM／實體 RS485 待驗證」僅由本次 bench 範圍更新。重現、證據及限制見 [驗證紀錄](../../output/delta-rtu-bench-20261112/README.md)。


### 無 Pi 逐關執行紀錄（2026-11-12）

實際關卡狀態、帳本工具重現方式及限制見 [逐關驗證紀錄](../../output/delta-no-pi-validation-20261112/README.md)。測試只作用於獨立 delta-rtu-sim-001 與各 run 自有 SQLite，不新增／重啟共用容器；中央 DB committed ACK 仍未實作。

### RTU串口恢復（2026-11-12，ADR-040）

同一RTU模擬器程序成功監聽後，偵測serial handle或Windows poll task失效，關閉舊端點後重開原串口；context保留，首次開啟失敗仍退出。config集中驗證DELTA_SIM_RTU_HEALTH_SECONDS（0.5s）與DELTA_SIM_RTU_RECONNECT_SECONDS（2s），有限0.01..60s。完整回歸127 passed、line coverage95.71%；修正後實體正常採集3/3。這不等於USB恢復通過，詳[ADR-040](../../doc/adr/ADR-040-delta-rtu-listener-recovery.md)與[逐關紀錄](../../output/delta-no-pi-validation-20261112/README.md)。

2026-11-12 12:16更新（ADR-040）：COM3修正後實體拔插usb-com3-04-fixed通過，離線33.328秒，恢復上界9.672秒，原程序持續運行，52筆DB/API逐筆相符、pending0；COM4仍待獨立測試，關卡4只部分完成。實際證據以逐關紀錄為準。

2026-11-12實體故障測試已完成：合法分段、截斷、錯誤CRC、錯站號、無回應各20/20通過；遲到回覆20/20被下一次read接受，交易關聯／新鮮度尚有缺口。此為Poller.read測試，非完整edge污染證據，未送故障值到MQTT。[逐關／封包證據](../../output/delta-no-pi-validation-20261112/frames-01/README.md)。

## ADR-041：RTU錯誤後採集暫停與恢復

不確定交易後正式Poller丟棄整筆並鎖定。未知回覆上界不再送新請求；已核定上界等待後才重建client/framer並清buffer。field RTU必填response_lifetime_seconds（有限0.01..120秒）及response_lifetime_source（非空、至多256字），啟動與--once也先隔離。field-rtu.example.json保留null，未由工程人員核定機型／韌體／USB／驅動上界前會拒絕啟動，不是可直接部署的設定。

既有可信outbox仍由獨立sender補送；SynchronizationUncertain需查profile，不要靠重啟或填猜測值解除。RecoveryPending表示仍在隔離期。台架bench_recovery的1秒只是假設已知的受控fixture，不能複製到M70A-262／RPI-M30A；超界或惡意遲到仍無辨識保證。[決策](../../doc/adr/ADR-041-rtu-uncertainty-and-bounded-recovery.md)；[最新驗證](../../output/delta-no-pi-validation-20261112/README.md)。共用Docker runtime未部署此修正。

[ADR-041完整sample實測](../../output/delta-no-pi-validation-20261112/rtu-recovery-policy/README.md)：unknown鎖定20/20、有界lab隔離恢復20/20；163項隔離回歸通過。它只限定受控時限契約，真機profile仍待核定、原無界late FAIL保留；沒有故障值入庫，也未重建共享runtime。

## 2026-11-12 續驗：DB確認反例與長測

[最新逐關紀錄](../../output/delta-no-pi-validation-20261112/README.md)：第9關以私有真MQTT／production傳送端／受控SQLite重現3案，v1系統驗收FAIL；未操作共享DB，v2中央commit receipt／去重待實作。本機Monitor攔截API的5案新鮮度及圖表／卡片／表格值通過，只屬UI契約。1秒1小時於13:49啟動，通過才進5秒24小時，當前以紀錄內活動status為準；未先報長測通過。保持PC開機及兩顆USB，不再人工拔插。回歸183 passed、production coverage96.06%；無API／schema變更、未部署共享runtime。

## 2026-11-12 時鐘／TLS補驗完成

[補驗紀錄](../../output/delta-no-pi-validation-20261112/field-security-02/README.md)：正式edge加真Modbus TCP／SQLite／私有TLS broker，時鐘2案11階段、TLS10案，共12/12通過；7個憑證／認證拒絕案保留pending，同Publisher1.0274秒重連。只注入測試UTC／節拍及sender permit，不改主機時鐘或COM。首輪9/12失敗保留，工具修正後另驗；完整回歸191 passed／12 skipped，12項隔離案已另實跑，production coverage96.06%。私有容器已清理，無API／schema／production改動、未部署共享runtime。1秒／1小時已PASS、5秒／24小時仍運行；中央receipt／去重、多設備仍待實作，非Pi／4G／真機准入。

## 無 Pi 弱網與積壓驗證工具（2026-11-12）

[bench_backlog.py](tools/bench_backlog.py) 使用正式 edge／TCP Poller／SQLite／Publisher，加入測試用 stream delay／jitter／rate／reset，並核對完整 payload 集合及線上備份前綴。私有 mode 需核對 namespace；local-ems 僅允許保留的 QA 身分，不允許活動 COM 台架 ID。

[判定測試](tests/test_bench_backlog.py)及 [實跑證據](../../output/no-pi-backlog-20261112/README.md)：203 項回歸，10,120／155 筆私有、110 筆真 EMS 跨層對帳。completion 與 unique_delivery 分開；本輪無重複不代表 v1 有中央去重。未改 production 或活動長測來源。

## 實際接收程式故障驗證（2026-11-12）

[bench_ingest.py](tools/bench_ingest.py)／[判定測試](tests/test_bench_ingest.py)以自有 network-none anchor 連接私有 Mosquitto／Telegraf／TimescaleDB，使用相同接收 image／原設定核對及 repo 初始化 schema；只改副本 endpoint，無 host port。`python3 services/delta/tools/bench_ingest.py --output <全新目錄>` 於 repo 根目錄執行，保留每案 sender、DB、凍結來源、映像及清理結果。exit0 表示基準／兩反例／恢復皆按預期驗出，**不是系統可靠送達通過**，須讀 `system_delivery_acceptance_passed`。

[實跑證據](../../output/no-pi-ingest-20261112/README.md)：重送重複入庫與接收停止缺筆仍 FAIL；DB 暫停恢復 10／10。另以私有核心 netem 實際丟 17 封包後 230／230 完整；211 項回歸通過。Pi、正式 TLS／ACL、中央 receipt／去重及原 24h 全窗驗收未完成；production 不變。

## v2 committed delivery 修復（2026-11-12）

在新設定明示 `delivery.protocol=2` 啟用 [reliable_store](delta_device/reliable_store.py)／[sender](delta_device/reliable_sender.py)／[wire](delta_device/reliable_wire.py)。[接收端／維護與切換說明](../edge-receiver/README.md)、[field設定範本](config/reliable-field.example.json)；範本 RTU lifetime=null 刻意拒啟動，現場須核定，不能照抄台架值。現有無 delivery 設定仍為 v1，不能把歷史 PUBACK 改稱中央 commit。

新專用 SQLite（2026-11-13已升本地schema3、wire仍2）、未知／舊五欄schema拒開；穩定原 ID/hash，PUBACK不刪，當前已驗 session／batch committed ACK 才記送達並刪payload。另依[ADR-045](../../doc/adr/ADR-045-newest-first-edge-retention.md)，容量滿按capture_seq淘汰最舊資料以保留新讀值，包含未送／quarantine與audit；淘汰不記committed。v1與舊v2拒開schema3；離線 [migrate_delivery](delta_device/migrate_delivery.py)只讀已停止的v1來源，以全新目的檔完整轉換後原子發布，容量不足不發布裁切版，保留對應及clock高水位，不恢復已被v1刪除資料。demo v2只接受明示network-none namespace；field強制mTLS與權威ACL。[驗證與維運](../edge-receiver/README.md)。

[本輪證據](../../output/committed-delivery-fix-20261112/README.md)：259項通過／12跳過、combined coverage90.81%。兩個送達缺口在新v2修復並實跑驗證；沒有切共享v1／原24h，也不宣稱完整多設備、對帳API、Pi／4G或20/s補傳已驗收。

### v2最新／最舊公平傳送（2026-11-13）

[ADR-048](../../doc/adr/ADR-048-v2-live-backlog-fairness.md)修原FIFO使新資料排整批歷史之後：sender先latest，真committed且本地成功解析後latest／oldest1:1交替；timeout／retryable／原列已淘汰ACK不吃輪次。box.pending()預設最舊保持；新選項只換查詢方向，原UUID/hash不變、quarantine不送。重啟從latest、輪次不持久；latest候選非所有新筆固定SLA。[千筆積壓下3新筆與相鄰回歸](../../output/no-pi-restore-load-20261113/README.md)通過（419／12專用skip／91.04%），原1秒edge節奏、wire2／schema3／mTLS及容量淘汰保持，未切共享或跑長測。
