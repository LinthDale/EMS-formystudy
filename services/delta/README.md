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
預設10000筆（10秒約27.8小時），上限1000000筆；满時拒絕新樣本並記錄queue_full，保留舊樣本；磁碟滿同樣不視為成功。容量規劃需含檔案與flash磨損。
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
