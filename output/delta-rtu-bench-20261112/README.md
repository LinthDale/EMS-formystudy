# Windows 雙 USB–RS485 實體驗證（無 Pi）— 2026-11-12

本次使用同一台 Windows 電腦的兩個實體串口，以實體雙絞線連接，沒有以 TCP 或 PTY 代替 RS485。測試使用 Delta V1.35 子集 simulator，並非 Delta 真機。

## 連線與結果

- COM3：FTDI BG04PB77，Delta RTU 從站；COM4：FTDI BG04PB7R，正式 Poller 主站。
- 19200 baud、8N1、unit 1、address_base 1、timeout 3 秒、read_temperature=true；1 秒採樣目標。
- Windows Python 3.12.14、pymodbus 3.6.9、pyserial 3.5、paho-mqtt 2.1.0。
- A/B：只改 strict，True 成功 6/20，False 成功 20/20。參見 [strict-ab.json](strict-ab.json)。
- 修正後 day 100、night 5、alarm 5，共 **110/110** 成功。包含完整讀取與數值/情境驗證；參見 [physical-110.json](physical-110.json)。這是有界樣本，不能推論永不丟包。
- 端到端以正式 Poller/Outbox/Publisher/drain 組件實測：online 5 → sender 關閉但持續採集 5 → 重新開啟 SQLite/Publisher 補送 → online 5。pending 為 **0 → 5 → 0**。
- 隔離設備 `delta-rtu-sim-001`：**15/15** 寫入 TimescaleDB；逐筆核對採樣時間及 voltage/current/power_kw/energy_kwh 全部相符，本次零重複。既有 EMS `/api/devices/delta-rtu-sim-001/records` 回傳 HTTP 200、15 筆。參見 [delivery-result.json](delivery-result.json)。
- 此補送測試是受控 sender 斷線及 SQLite 重開，未模擬主機斷電、硬體拔線或 4G 斷網；PUBACK 仍非 DB committed ACK，PRD-0021 的中央對帳並未因此實作。
- 全套 Delta 回歸 **78 passed，coverage 95.20%**。新增測試先 RED（1 fail / 5 pass），修正後 GREEN。

## 修正與邊界

`poller.make_client()` 僅在 win32 使用 strict=False，避免 pymodbus 將極短字元間隔設為 Windows serial read interval timeout，導致 USB 分段資料被提前截斷。仍有總 timeout、長度、unit、CRC 檢查，retries=0；Linux strict=True 不變。單元涵蓋分段有效回應、錯 CRC、錯站號、截斷、無回應及 Linux 行為。未修改寄存器、倍率、API 或 schema，對應 PRD-0020 / ADR-031 的缺陷修復。

本次 Windows 直接載入已修改的原始碼；既有 Docker demo 未重建或重啟。實機 Pi、SIM7600G-H/4G、Delta M70A-262 / RPI-M30A 韌體相容性、現場 TLS/ACL、長時間壓測仍待驗證。

## 重現操作

目前有界測試已結束，COM3/COM4 已釋放；本機預覽 4178 保持開啟。15 筆 bench 記錄保留供查閱，不混入 delta-sim-001。bench 設備是獨立硬體測試身份，沒有加入既有四台 simulator 控制清單。

兩個 Windows PowerShell 視窗皆先執行：

```powershell
Set-Location '\\wsl.localhost\Ubuntu\home\dalelin\synaiq\EMS\services\delta'
$py = 'C:\Users\User\AppData\Local\Temp\ems-delta-bench-20261112-venv\Scripts\python.exe'
```

視窗一啟動從站：

```powershell
& $py -m delta_device simulator --transport rtu --serial-port COM3 --baudrate 19200 --unit-id 1 --scenario day
```

視窗二先單次診斷（不送 MQTT），成功後再啟動持續採集：

```powershell
& $py -m delta_device edge --config ../../output/delta-rtu-bench-20261112/windows-bench.json --once
& $py -m delta_device edge --config ../../output/delta-rtu-bench-20261112/windows-bench.json
```

Ctrl+C 結束各自程序；不要同時啟動兩個使用 COM4 的採集程序。COM 編號以當下裝置管理員為準。此 venv 位於 Temp，遭清除後依服務 README 重新建立並安裝鎖定 requirements。此配置僅 demo，不能用於現場部署。

開啟 http://127.0.0.1:4178/live/Monitor.html ，以既有 OPS 登入，選 `delta-rtu-sim-001`；測試資料在台灣時間 2026-11-12 09:09:04–09:09:18，可用自訂區間查閱。已驗證頁面登入畫面及登入後 records API；此次未完成登入後圖表的瀏覽器視覺驗收。

## 回歸命令

```bash
docker run --rm --network none -e PYTHONDONTWRITEBYTECODE=1 -e COVERAGE_FILE=/tmp/delta.coverage -v /home/dalelin/synaiq/EMS/services/delta:/app:ro -w /app ems-delta-test python -m pytest tests --cov=delta_device --cov-report=term-missing --cov-fail-under=80 -p no:cacheprovider -q
```

## 最後複核

- Code reviewer 與 Python reviewer 均通過，無阻擋問題；兩者未操作 COM 埠或重啟服務。Code reviewer 交叉核對 pinned pymodbus/pyserial source；Python reviewer 獨立隔離回歸 23 passed。
- OpenAPI YAML 解析通過；此次修改檔案的 diff whitespace 檢查通過。全工作樹另有既存 PRD Guideline 第 3–4 行 trailing whitespace，保留其他工作的內容。
- 測試結束未留 delta_device Python 程序；本機預覽 http://127.0.0.1:4178/ 運行。未 commit/push，未部署公開網站。
