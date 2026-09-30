# Simulator 統一控制驗收紀錄

日期：2026-09-29；規格：[PRD-0022](../prd/PRD-0022-simulator-control-audit.md)、[ADR-033](../adr/ADR-033-simulator-control-audit.md)。
操作方法：[Simulator 統一控制與操作紀錄](simulator-control.md)。

## 範圍與結果

已於本機 Docker demo 部署 BFF 與四個 EMS runtime wrapper，驗證控制、持久操作紀錄及既有資料採集管線。上游 KC submodule 未修改。

| 檢查 | 結果 | 證據範圍 |
|---|---|---|
| BFF 全套回歸 | 228 passed | 其中新增控制測試 32 項；新控制模組及 routes 合計行覆蓋 94% |
| BFF 分項覆蓋 | audit 100%、routes 92%、manager 89%、contracts 96%、body_limit 92% | 非整個 EMS 覆蓋率 |
| Delta 全套回歸 | 72 passed | scenario 分段積分及當時工作樹中的 1 秒 noise 測試 |
| 電表既有回歸 | 61 passed | API、float registers、模擬公式；main.py 整體覆蓋 66%，不宣稱整體 90% |
| meter / PLC / Delta wrapper | 各 14 passed | 各 7 項共用 agent 測試與 7 項真實 TCP socket 測試 |
| sensor wrapper | 9 passed | 7 項共用 agent 與 2 項 MQTT sensor 行為測試 |
| 共用 agent / sensor 覆蓋 | 90% / 92% | 選定模組行覆蓋 |
| CLI | 3 passed | 包含 HTTP 204 logout，避免成功命令被誤報失敗 |
| 四路資料管線 | 35 passed，約 111 秒 | 電表、PLC、MQTT sensor、Delta 透過既有管線寫入實際 demo DB |
| BFF 重啟 | 30 筆驗收紀錄保留 | 重啟後以測試 OPS 登入查詢；未重送已記錄命令 |
| 最終清理 | 另增 1 筆，共 31 筆 | 還原 PLC 初始設定，仍透過已認證 BFF 留存紀錄 |
| API 契約 | PASS | OpenAPI 2.0.0：無重複 YAML keys、本地 refs 皆可解析、device-service runtime contract 不變、版本與 CHANGELOG gate 通過 |
| 部署設定與差異 | PASS | Compose config --quiet、git diff --check |
| 本機服務 | PASS | BFF /healthz 200；未登入 /api/simulators 401；四 target /state 皆 200 |

BFF 測試涵蓋 OPS/Origin、嚴格欄位/數值、body 限長、UUID 去重與衝突、同台併發、CAS、磁碟失敗、容量上限、啟動鎖與 pending 恢復、派送前後取消、偽造 receipt、對帳、重啟，以及過大/壓縮/慢速 agent response 的串流上限與總逾時。
socket 測試確認合法讀取與受認證設定可影響 raw registers，同時拒絕 FC05/06/15/16/22/23 的直接寫入。

初次管線驗收發現 PLC 原有採集依 register group 產生稀疏列；測試已改按非空量測欄位查詢，不要求每筆工廠資料列都有 temperature。該修正未改量測格式。新增還原 fixture，最後再確認所有 demo 設定。

## 操作紀錄與部署證據

- 正式 DB：`ems-bff:/data/sim-control/audit.sqlite3`，volume `ems_simulator_audit`。最終只讀核對時為 **0 commands**；測試紀錄不混入正式紀錄。
- 工程驗收 DB：獨立 volume `ems_simulator_control_acceptance` 內的 `/data/acceptance.sqlite3`。最終 **31 commands**，`PRAGMA integrity_check` 為 `ok`。
- 工程驗收使用只綁測試容器 loopback :18003 的臨時 BFF、隨機測試密碼與合成帳號；未修改正式 OPS 登入帳號。密碼沒有保存於資料庫或此文件。
- 驗收的 telemetry 會進既有 demo 量測資料庫，並可能觸發既有 demo 告警；「獨立」指操作稽核 DB，不代表量測 DB 隔離。
- 最終設定：meter 預設參數、fault_mode=none；PLC motor_speed=0、pump_on=false、valve_open=false；sensor enabled=true、interval_seconds=2；Delta scenario=day。
- BFF :8003 與兩個 Modbus host port :5020/:5021 綁 127.0.0.1；管理 :9000 無 host mapping；舊 :8001 host mapping 已移除。
- 本機已啟用 BFF_SIM_CONTROL_ENABLED 與 service credential，憑證只存在本機環境設定，不納入 Git。

## Review 與修正

架構 review 採納固定 registry、BFF 集中控制、wrapper 隔離、旁路封鎖、unknown 對帳及 Delta 分段能量結算。
Python review 指出的派送前取消分類及啟動失敗資源釋放已修正，32 項控制測試獨立重跑通過，結論 APPROVE。
安全 review 指出的 response 先緩衝再限量與缺少總 deadline 已修正為串流 16 KiB 上限及每 hop 3 秒總期限，無剩餘必修項目。
一般程式碼 review 指出的 CLI 204 logout 問題先以測試重現再修正，3 項測試通過，結論 APPROVE。

## 重現主要檢查

以下從 WSL 專案根目錄執行；測試 image 須先存在。來源以 readonly mount 提供，不寫入正式容器。

```bash
docker build -t ems-bff-test --target test services/bff
docker build -t ems-sim-test-meter --target test-meter -f services/sim-control/Dockerfile .
docker build -t ems-sim-test-plc --target test-plc -f services/sim-control/Dockerfile .
docker build -t ems-sim-test-sensor --target test-sensor -f services/sim-control/Dockerfile .
docker build -t ems-sim-test-delta --target test-delta -f services/sim-control/Dockerfile .
docker build -t ems-sim-integration -f services/sim-control/Dockerfile.integration .

docker run --rm --network none -e PYTHONDONTWRITEBYTECODE=1 -e COVERAGE_FILE=/tmp/bff.coverage -v "$PWD/services/bff:/app:ro" -w /app ems-bff-test python -m pytest tests -q -p no:cacheprovider --cov=bff.simulator_control --cov=bff.routes.simulators --cov-report=term-missing

docker run --rm --network none -v "$PWD:/repo:ro" -w /repo ems-sim-test-meter python -m pytest tests/unit/test_simulator_api.py tests/unit/test_float_registers.py tests/unit/test_simulation_math.py tests/unit/test_simulator_control_cli.py -q -p no:cacheprovider

docker run --rm --network none -v "$PWD/services/sim-control/tests:/tests:ro" -w /app ems-sim-test-plc python -m pytest /tests/test_agent.py /tests/test_runtime_socket.py -q -p no:cacheprovider
docker run --rm --network none -v "$PWD/services/sim-control/tests:/tests:ro" -w /app ems-sim-test-sensor python -m pytest /tests/test_agent.py /tests/test_sensor.py -q -p no:cacheprovider

docker compose --profile delta-demo config --quiet
git diff --check
python3 scripts/simulator_control.py --help
```

meter、Delta wrapper 的 socket 測試以相應 image 重複 PLC 那一行。Delta 服務回歸使用 services/delta 的 test image，執行該目錄 tests。

四路驗收入口是 [run_simulator_control.py](../../tests/integration/run_simulator_control.py)。
必須在可改動的 demo 環境執行，四個 target、broker、gateway、ingest、DB 與 query 需已啟動。以受控方式提供 `SIM_CONTROL_TOKEN` 與 `EMS_DB_DSN`，不要將 secret 放在命令列；另指定 `EMS_ACCEPTANCE_AUDIT_PATH`。
測試容器需接 `ems_default`，mount 專案到 `/repo:ro`、獨立可寫目錄到 `/data`，設定 `PYTHONPATH=/repo/services/bff`，使用 `ems-sim-integration` 執行上述入口。
入口會啟動臨時 BFF、跑四路測試，再重啟 BFF 核對紀錄。每次驗收使用新的獨立 audit volume；上述 31 筆為本次保留證據。

## 尚未涵蓋

本次未新增公開 Monitor 控制頁；日常操作使用 BFF API / CLI。
未以實體 Pi、RS485 線路或現場 Delta 設備驗收；standalone RTU CLI 不納入這個常駐 TCP demo 控制入口。
尚無設定持久化、多人多副本控制、長期 audit 歸檔流程或密碼學防竄改。設定重啟回預設，操作紀錄持久；unknown 不自動重送。

## 2026-09-29 CLI Secure-cookie 修正補驗
原現場紀錄：login200 → list401 → logout401，BFF session_cookie_secure=True。先新增測試取得18 RED／既有3 GREEN，再修正CLI。
最終分層為20 unit + 1 HTTP integration，全21項通過，CLI行覆蓋87%；數字IPv4/IPv6、同port、跨port、userinfo、非loopback、HTTPS、path、expiry、登入/讀取錯誤與派送後timeout均驗證。
另外啟動真實臨時BFF（Secure=True、隨機合成OPS帳密、獨立暫存audit），以CLI查list/state/history連上四個運行中的target，均成功；logout後測試sessions為0，未下達simulator命令，也未改正式帳密/環境設定。
Python、安全與一般程式碼review通過；HTTP測試依規範移至integration。

```bash
docker run --rm --network none -e PYTHONDONTWRITEBYTECODE=1 -e COVERAGE_FILE=/tmp/cli.coverage -v "$PWD:/repo:ro" -w /repo ems-sim-integration python -m pytest tests/unit/test_simulator_control_cli.py tests/integration/test_simulator_cli_auth.py -q -p no:cacheprovider --cov=scripts --cov-report=term-missing
```


## 2026-09-29 操作手冊可執行性核對
核對範圍為 simulator 控制手冊及 README、EMS操作手冊、容器速查表中的對應操作，不代表其他歷史章節重新驗收。
新增 demo OPS 帳號說明、PowerShell→WSL 步驟、sim Bash function及保存/重載方式、四種模擬器設定與復原、回應欄位與紀錄範圍；修正舊MCP讀寫與standalone部署現況說明。
13個Bash區塊通過語法檢查；21條CLI範例經實際argparse及typed control contract檢查，使用隔離transport，未送出真實設定命令。sim function在專案外可呼叫實際CLI --help，定義存入暫存Bash設定檔後於新shell載入也通過。未更改使用者 ~/.bashrc。
新手冊連結與章節錨點有效。只讀核對本機仍為demo/ops、Secure cookie開啟、BFF控制啟用、四台sim_control wrapper運行且管理9000無host mapping。
