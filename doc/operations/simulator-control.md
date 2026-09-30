# Simulator 統一控制與操作紀錄

> 核對日期：2026-09-29；已對照目前 CLI、控制契約與本機運行設定。

適用：本機 Docker demo 的四台模擬器。權威規格 [PRD-0022](../prd/PRD-0022-simulator-control-audit.md)、[ADR-033](../adr/ADR-033-simulator-control-audit.md)。

## 從目前這台電腦開始

2026-09-29 已核對本機帳號：`demo` 的角色為 `ops`。其他部署請換成該環境的 OPS 帳號。
使用平常登入 EMS 的密碼；密碼不列在文件中。CLI 需要 Python 3.10 以上，使用標準函式庫，不需另裝 Python 套件。
每次 CLI 執行都會登入、完成指令後登出；瀏覽器已登入不會讓 CLI 免輸入密碼。

### 1. 進入 Ubuntu 專案

在 Windows PowerShell 執行：

```powershell
wsl -d Ubuntu --cd /home/dalelin/synaiq/EMS
```

如果已經看到 `dalelin@...:~/synaiq/EMS$`，可直接做下一步。後續 `bash` 區塊都在 Ubuntu 執行。

### 2. 先用完整指令確認登入

```bash
python3 scripts/simulator_control.py --username demo list
```

看到 `EMS password:` 時輸入密碼並按 Enter；輸入時不會顯示字元。
正常回應包含四個 simulator 的清單。這是唯讀查詢，不會建立 simulator command 紀錄。

### 3. 建立 sim 簡寫

`sim` 是 Bash function，專案不會自動安裝這個命令。在目前視窗貼上：

```bash
sim() {
  python3 /home/dalelin/synaiq/EMS/scripts/simulator_control.py --username demo "$@"
}
```

`"$@"` 會原樣轉交後面的參數；絕對路徑讓你離開專案目錄後仍能操作。

```bash
type sim
sim --help
sim list
```

這個 function 只縮短指令，每次操作仍會提示密碼。其他帳號或不同專案路徑須調整 function。

### 4. 讓新開終端機也能使用

先完成上一步，再執行以下指令一次，把 function 定義存入自己的 Bash 設定檔：

```bash
declare -f sim >> ~/.bashrc
```

已儲存過就不必重複追加。新開 Ubuntu Bash 會載入；另一個已開啟的 Ubuntu Bash 視窗可執行：

```bash
source ~/.bashrc
type sim
```

這不是安裝系統套件，也不會把密碼存入 `~/.bashrc`。若看到 `Command 'sim' not found`，先重新執行步驟3；不需安裝終端機推薦的其他同名套件。

## 日常操作範例

以下每條指令請分開執行，確認結果後再進行下一步。
`set` 和 `reconcile` 都必須填 `--reason`；CLI 會自動處理 session、Origin、command UUID 與 instance/revision，不需手動填寫。

### Delta：日間、夜間及告警情境

```bash
sim state delta-sim-001
sim set delta-sim-001 scenario=night --reason "測試夜間停止發電"
```

當結果為 `"status": "succeeded"`，到 EMS Monitor 選擇「太陽能逆變器（delta-sim-001）」並等待新資料；夜間電流與功率為零，累計電量保留。
`state` 顯示控制設定，Monitor 顯示採集到的量測，兩者更新時間不同。

```bash
# 恢復日間
sim set delta-sim-001 scenario=day --reason "測試完成恢復日間"

# 另一次測試：逆變器告警情境
sim set delta-sim-001 scenario=alarm --reason "測試逆變器告警情境"

# 告警情境測試完成後恢復
sim set delta-sim-001 scenario=day --reason "告警情境測試完成"
```

`alarm` 改變 Delta 模擬狀態與量測，不等於觸發 EMS Telegram 示範通知，也不保證警報中心會新增設備告警；現有持久化量測管線只收 V/A/kW/kWh。

### 電表、PLC 與 MQTT 感測器

```bash
# 電表：凍結後恢復（凍結時仍回應通訊）
sim set sim-001 fault_mode=freeze --reason "測試量測值停止變動"
sim set sim-001 fault_mode=none --reason "恢復正常量測"

# PLC：馬達與幫浦，完成後還原示範預設
sim set plc-001 motor_speed=1500 pump_on=true --reason "測試馬達與幫浦"
sim set plc-001 motor_speed=0 pump_on=false valve_open=false --reason "恢復PLC示範預設"

# MQTT感測器：改成每5秒發布，再恢復示範預設2秒
sim set sensor-001 interval_seconds=5 --reason "測試5秒發布"
sim set sensor-001 interval_seconds=2 --reason "恢復原發布間隔"

# MQTT感測器：暫停及恢復發布
sim set sensor-001 enabled=false --reason "測試感測器暫停發布"
sim set sensor-001 enabled=true --reason "恢復感測器發布"
```

若原本不是示範預設，先用 `sim state 設備ID` 記下設定，測試後恢復原值；不要照範例覆蓋其他人的測試設定。

### 查詢紀錄

```bash
sim history --limit 20
sim history --simulator-id delta-sim-001 --limit 5
```

`history` 顯示的是設定命令紀錄，不是量測歷史。CLI 預設20筆、每頁1–100筆；回應有 `next_before` 時，把其數字帶入 `--before` 查較舊的一頁。

### 如何看回應

| 欄位 | 意義 |
|---|---|
| capabilities | 可以調整哪些欄位、值域與型別 |
| settings | 目前控制設定，並非即時量測 |
| available: true | BFF 可讀到 target 的控制狀態；不代表遙測已入庫 |
| blocked: false | 沒有待處理的未知命令阻擋後續控制 |
| instance_id | 本次 simulator process 的身分，重啟會換 |
| revision | 本次 process 的設定版本 |
| request_id | 命令識別碼，可查單筆結果及對帳 |
| status: succeeded | 目標已套用設定且 BFF 已記錄結果 |

## 控制入口與適用範圍

後端：`http://127.0.0.1:8003/api/simulators`；使用 OPS session，寫入需允許的 Origin。[CLI](../../scripts/simulator_control.py) 已處理這些欄位。
完整指令形式為 `python3 scripts/simulator_control.py --username demo <動作> ...`；`sim` 是前面設定的本機簡寫。

CLI 使用本機密碼登入；OIDC-only 部署須透過已登入的 session 呼叫 API。本機用預設數字 loopback，外部入口須 HTTPS 並加入 BFF Origin allowlist。
本次提供後端 API + CLI，公開 Monitor 尚未新增控制面板；此手冊的控制入口以本機為準。
Windows 原生 Python 也可執行腳本，但本手冊的 `sim` function、`declare` 與 `~/.bashrc` 僅適用 Ubuntu Bash。

## 控制能力與語意

| ID | 設定 | 範圍/備註 |
|---|---|---|
| sim-001 | fault_mode | none / zero / freeze；zero 保留既有累計電量 |
| sim-001 | noise_voltage_v / noise_current_a | 0–20 |
| sim-001 | current_base_a / current_swing_a | 0–1000 A |
| sim-001 | power_factor / period_seconds | 0–1 / 1–86400 秒 |
| plc-001 | motor_speed | 0–65535（UINT16 setpoint） |
| plc-001 | pump_on / valve_open | true / false；絕對設定，不提供 toggle |
| sensor-001 | enabled | true 發布、false 暫停；不是停止容器 |
| sensor-001 | interval_seconds | 1 / 2 / 5 / 10 / 15 / 30 秒，2 為舊預設 |
| delta-sim-001 | scenario | day / night / alarm；切換保留本次 process 的累計電量 |

sensor 發布間隔與 Pi 採樣間隔分開；本控制不改 Pi、真機或 edge 通訊設定。CLI 的 `set` 可同時提供多個 key=value。
設定套用成功不等於最新數據已寫入 EMS；要等既有 gateway/ingest flush，再看監控或資料庫。
**模擬設定重啟會回預設**，instance_id 也會換；**操作紀錄重啟保留**。

## 操作紀錄在哪裡
- 正式入口：`GET /api/simulators/operations`，每頁 1–100 筆，依 sequence 倒序。
- 單筆：`GET /api/simulators/operations/{request_id}`。
- 容器檔案：`ems-bff:/data/sim-control/audit.sqlite3`。
- Compose volume：`simulator_audit`；本機 project 實際名稱通常 `ems_simulator_audit`。
- 表：`operations` 為指令意圖，`events` 為結果/對帳事件；只有新增，UPDATE/DELETE trigger 拒絕。
- 每筆命令含 actor、UTC、UUID、模擬器、reason、changes、expected instance/revision、before/after、結果/固定錯誤碼。
- 這是設定命令稽核，不是所有 HTTP 請求的存取紀錄：list/state/history、登入失敗及入口拒絕不會新增 command。對帳取得有效 receipt 或新 instance 證據時才追加事件；查無新證據會回原紀錄。
- actor 取自登入 session；不用 caller 傳入的名字。reason 勿放密碼或個資。
- 記錄上限預設 100000 commands；滿了停止新命令，保留查詢。無自動刪除、無刪除 API；需人工歸檔規劃，不能刪 DB 讓 UUID 重新生效。
- Docker stdout 只是服務診斷，四個 simulator 設 10 MB × 3 rotation；不是正式稽核紀錄。
- 主機管理員的 docker/檔案操作仍在應用邊界外，SQLite 並非密碼學防竄改儲存。

SQLite 使用 DELETE rollback journal + synchronous FULL 與 OS file lock，僅單 active BFF process。不可開多 worker/多副本，也不可將同一 agent endpoint 變成負載平衡後仍沿用目前對帳語意。

## 逾時、重複命令與對帳
每次新的 set 操作由 CLI 產生 UUID，**發送前即印出 request_id**。
相同 UUID + 同一 actor + 相同命令回原紀錄，不重送；內容不同回 409。
請求中有 expected_instance_id 與 expected_revision，防止另一個操作或重啟造成覆蓋。

| status | 意義 | 下一步 |
|---|---|---|
| pending | 意圖已存，正在執行 | 稍後查單筆；不要另造 UUID 重送 |
| succeeded | agent receipt 證明設定已套用，結果已存檔 | 等遙測更新 |
| failed | 未派送或 target 明確拒絕 | 看 error，修正後用新 UUID |
| outcome_unknown | 派送後逾時/中斷，或 controller 重啟時留有 pending | 先對帳，不自動重送 |

```bash
# 把 REQUEST_UUID 換成前一次輸出的完整 request_id
sim operation REQUEST_UUID
sim reconcile REQUEST_UUID --reason "連線恢復後確認結果"
```

對帳只讀 agent receipt 或目前 instance，不重新套用命令。receipt 必須吻合 UUID、命令 hash、ID、舊 instance、revision、前後設定；查無 receipt 或當前設定碰巧相同都不算成功。
同 instance 查無 receipt 時仍封鎖後續命令。人工確認後重啟**該台 demo simulator**，再 reconcile：
舊 instance 退役、保留 outcome_unknown，`resolved=true` 僅表示可控制新 instance，不表示歷史命令成功。BFF startup 自動將未完成 intent 標記 unknown。
每個 agent 最多保留 4096 receipts，滿時拒絕新命令；安排重啟，接受設定回預設，再讀新 state。

## 部署、關閉及備份
.env 設定（機密不提交 Git）：
- `SIM_CONTROL_TOKEN`：至少 32 字元的隨機 service credential，僅 Compose 注入 BFF/四 wrappers。
- `BFF_SIM_CONTROL_ENABLED=true`。
- BFF 其他登入、Origin、Secure cookie 設定沿用既有設定。
- token 缺失時 agent 遙測繼續、控制 503；BFF 明確啟用但缺合法 token 時拒絕啟動。

```bash
docker compose --profile delta-demo build simulator kc-modbus-sim kc-mqtt-sim delta-simulator bff
docker compose --profile delta-demo up -d --no-deps simulator kc-modbus-sim kc-mqtt-sim delta-simulator bff
```

9000 只在 Docker network 內，無 host mapping。舊 :8001 已撤下，原生 meter POST /config、/inject-fault 回410。
電表/PLC host Modbus改loopback，FC05/06/15/16/22/23 寫入均拒絕；MCP profile 改 read。MCP raw write 亦被 target 阻擋。
runtime wrapper 由 EMS 維護，KC submodule 未修改。

備份請使用 SQLite backup API；不能在持續寫入時僅複製裸 .sqlite3：
```bash
docker compose exec -T bff python -c "import sqlite3; src=sqlite3.connect('/data/sim-control/audit.sqlite3'); dst=sqlite3.connect('/data/sim-control/audit-backup.sqlite3'); src.backup(dst); dst.close(); src.close()"
mkdir -p .local
docker cp ems-bff:/data/sim-control/audit-backup.sqlite3 ./.local/audit-backup.sqlite3
```
備份含帳號與reason，存放於受控路徑，勿提交Git。停機還原需連同整段歷史與UUID一起保留，不能只留最新設定。
關閉控制：設 BFF_SIM_CONTROL_ENABLED=false 後重建 BFF；保留 audit volume 與 hardened targets。**不要 docker compose down -v**。

## 驗證
驗收包含 BFF權限/CSRF、儲存失敗、UUID去重、取消/逾時、response限量/總期限、receipt對帳、重啟恢復；四wrapper實際Modbus/HTTP與sensor JSON；四路資料落DB。
工程整合驗收用不映射host port的臨時BFF、隨機測試帳密與獨立audit volume；不修改正式OPS帳號。測試會改動demo數據，須在測試環境執行並回復設定。
結果與確切命令見 [驗收紀錄](simulator-control-verification.md)。

## 本機登入成功但查詢 401
2026-09-29 已修正 CLI 對本機 Secure cookie 的處理。原症狀是 BFF 登入回200，list/logout回401，並非必然密碼錯誤。
直接使用目前腳本與原本帳密：

```bash
python3 scripts/simulator_control.py --username demo list
```

預設 URL 為 http://127.0.0.1:8003。若自行指定 localhost 且遇到 Session rejected，改用 --url http://127.0.0.1:8003；Secure-cookie 本機例外僅限數字loopback與同port。不要為此關閉 BFF_SESSION_COOKIE_SECURE。
Login failed (HTTP 401) 表示登入被拒絕；Session rejected (HTTP 401) 表示登入後session被拒絕。尚未送出command時會明示 No simulator command was sent；只有真正嘗試派送command後的未確認結果才提示查request_id。

## 11. 新增或管理操作帳號

帳號已存 PostgreSQL；`demo` 仍為 OPS。新增個人帳號、改密碼或停用請看 [帳號管理操作手冊](account-management.md)。
主機管理使用 `docker compose run --rm account-admin ...`；模擬器控制仍以 `python3 scripts/simulator_control.py --username <帳號> ...` 登入 BFF。
