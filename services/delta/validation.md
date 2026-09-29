# Delta 本機驗證紀錄 — 2026-09-29

- 新測試：48 passed；delta_device 全模組 line coverage 87.67%，門檻80%。CLI/socket子程序覆蓋未合併，CLI另有實際 smoke。
- 真Modbus TCP：day/night/alarm、讀取FC04、未支援地址exception2、FC03/寫入拒絕。
- 真RTU byte path：Linux PTY、獨立CRC fixture、Base1→PDU與unit3，非實體RS485線路。
- Parser：獨立PDF常數、bit0、動態scale、保留值拒絕、exception2 fallback、zero-scale今日電量特殊、low-word-first、三相。
- Outbox：重開恢復、容量、相符ACK刪除、原payload/時間保留、device identity、0600/0700、停用GC下150操作FD無增長。
- MQTT：Paho2.1 NO_CONN→on_publish、callback早到競態、未ACK/錯MID不刪除、TLS cert+hostname設定。
- Runtime：sender離線時採集持續、重送保留時間；queue_full與pending_rows日誌可觀察。
- 兩Delta容器最終重建後均Up，無publishedhostports；sample_queued與broker_ack持續出現。
- 既有sim-001與delta-sim-001同時持續入庫。沒有改動DBschema或重啟既有services。
- 實際瀏覽器：本機4178登入、選delta-sim-001，狀態「持續接收中」、四指標、70筆原始紀錄、無pageerror。
- UI稀疏2秒bucket主series顯示2px點；每series有non-nullpoint，connectNulls仍false。證據output/delta-verification/ui-result.json及monitor.png。
- CLI --once讀出三相230V/60Hz、state2、35°C及今日/累計電量；只診斷，不發布。
- docker compose config --quiet、git diff --check、OpenAPI PyYAML解析/x-delta-telemetry契約檢查通過。
- 架構、安全與code review通過；review發現的Paho ACK卡住與SQLite未close均修復并回歸驗證。

未驗證：實際Delta機型/韌體、實體RS485、Pi ARM硬體、SIM7600G-H/4G、現場TLSlistener與ACL／接收端device_id綁定、長期flash／資源壓測。
範圍：新本機Delta功能及預覽點位顯示，非完整59頁protocol、非現場production acceptance、非整站資安稽核。


## 2026-09-29 RTU 從站增量

- RED：新增PTY從站／缺串口退出測試在原TCP-only版本出現5項預期失敗；先修正PTY echo設定，確認失敗原因為CLI尚不支援RTU。
- GREEN：隔離 `ems-delta-test` 容器、Python3.11.15、pymodbus3.6.9、無外網；64 tests passed，coverage 95.10%。命令：`python -m pytest tests --cov=delta_device --cov-report=term-missing --cov-fail-under=80 -q -p no:cacheprovider`。
- 新增真實CLI RTU PTY：day/night/alarm、literal230V、FC03/06/16拒絕、非法位址、其他站號及廣播讀寫無回應、badCRC後恢復、CLI互斥參數與缺串口fail-fast。
- 兩PTY bridge：正式Poller→正式RTU CLI→解析器，9600/base0/scale0與38400/base1/scale absent；230V、0kW、1234.56kWh、35°C均符合預期。單元驗證RTU不呼叫TCP啟動且取消時shutdown。
- 既有TCP、protocol、SQLite/outbox、MQTT測試同時通過。Python3.9註記採future annotations，最低版本實際runtime未於本批執行；Windows COM、實體線路與4G仍待驗證。未啟停既有demo/正式服務。

審查完成：architect、security、code review 與 Python reviewer 均無未解決阻擋項。Python reviewer 另於隔離容器獨立執行 RTU simulator/TCP/原RTU共25項測試通過；環境沒有 ruff/mypy/black/pylint，未宣稱執行。
