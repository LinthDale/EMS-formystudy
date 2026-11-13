# 無 Pi 補測：實際接收程式故障與核心 IP 丟包

2026-11-12 17:20（Asia/Taipei）。依使用者「繼續」執行 PRD-0020 §13 的隔離驗證。新增測試工具與判定反例，未修改 production、共享設定或 API／schema。此次重點是把原受控 SQLite sink 的反例，推進至實際 Mosquitto → Telegraf → TimescaleDB 接收程式；另補真正核心 IP 丟包，與前輪 TCP stream reset 分開。

## 結果

| 測試 | 實測與判定 | 證據 |
|---|---|---|
| 實際接收基準 | 3／3，時間與四欄內容相符 | [最終結果](receiver-02-final-window/result.json)、[基準明細](receiver-02-final-window/baseline/result.json) |
| 重複投遞 | **1 筆來源投遞兩次，DB 寫入 2 列；可靠送達驗收 FAIL** | [明細](receiver-02-final-window/duplicate/result.json)。真 Publisher／Outbox，第二次保留相同設備、原時間與 payload；本地 pending0。這是已知 v1 缺少中央去重的實際接收端反例 |
| 接收服務停止 | **broker 已確認、本地 pending0，Telegraf 恢復後 DB 仍 0／1；可靠送達驗收 FAIL** | [明細](receiver-02-final-window/receiver-down/result.json)。只停止自建私有 Telegraf；恢復訂閱後至少觀察 10 秒，整輪再跨 6 秒 flush window 重查，仍缺此筆。未停止共享 ems-ingest |
| DB 暫停 | 私有 DB pause 至少 10 秒，10 筆先獲 broker 確認／本地 pending0；unpause 後 **10／10** 內容相符 | [明細](receiver-02-final-window/db-pause/result.json)。只證明此短暫 pause 情境恢復，不代表 DB commit 前本地資料受到 durable receipt 保護 |
| 真正 IP 丟包 | **230／230，缺少／額外／重複／錯值均 0，pending0；核心實際丟 17 個封包** | [核心統計及判定](ip-loss-01/ip-loss-result.json)、[逐筆結果](ip-loss-01/run/result.json)、[qdisc 統計](ip-loss-01/qdisc-after-run.json)。200 筆合成積壓＋30 次正式 TCP 採樣；單向 100±25ms、1% IP loss、512 kbit/s，僅 MQTT TCP 1883 進入 netem；runtime 56.917 秒。接收端仍是前輪私有 SQLite sink，**不是本表上方實際 Telegraf DB 案例或真 4G** |
| 回歸 | **211 passed／12 skipped，production line coverage 96.06%** | [回歸](regression.log)、[JUnit](regression.xml)、[命令及退出碼](regression-result.json)。新增 8 項判定測試；12 個私有時鐘／TLS skip 沿用 [前輪獨立 12/12 實跑](../no-pi-takeover-20261112-1600/README.md)，本輪未重跑 |
| 原長測中途核對 | **已完成前 1,740 槽，DB／API 各 1,740，逐筆一致** | [新結果](soak-prefix-02/result.json)、[查詢邊界](soak-prefix-02/boundary.json)。仍是 RUNNING，**不是完整 24h PASS** |

`verification_passed=true` 只表示四個實驗按預期重現且清理成功；同一結果明列 `system_delivery_acceptance_passed=false`。兩個反例不能因工具 exit0 被改寫為系統通過。[最後額外觀察窗](receiver-02-final-window/final-recheck.json)保存四案的最新資料集合。

## 與現行接收端的對應

- [runtime-equivalence.json](runtime-equivalence.json)確認 Telegraf、TimescaleDB 與當時共享 runtime 使用相同 immutable image ID。執行時還要求掛載中的共享 Telegraf 原始設定與 repo 完全相符：[設定核對](receiver-02-final-window/running-ingest-config-check.json)。私有副本只替換 broker／DB endpoint 成 loopback，原設定另存於 source。
- DB 由 repo `infra/timescaledb/init.sql` 初始化，驗證 time、device_id 及四個數值欄。共享表另有 nullable 的 name／slave_id／topic／type；因此這是**核心量測路徑的相同程式／設定驗證，並非整個共享 schema 完全複製**。當時共享量測表 unique index 數量為 0。
- 不使用共享 DB 注入故障，不模擬正式 TLS／ACL。私有 DB trust 只存在 network-none namespace，沒有 host port；不作對外部署。

## 隔離、原失敗與保護檢查

1. `receiver-01` 保留最初四案；獨立複核建議增加整輪最後的 flush window，工具補 6 秒後另開 `receiver-02-final-window`，沒有覆寫第一次證據。每輪自有 5 個容器均依記錄 ID 移除。
2. IP 丟包使用另一個自建 network-none namespace。注入前核對 ownership label、無 host port、namespace 與主機不同且僅 lo；`tc` 僅在此 namespace 修改，透過 dport／sport1883 filter 注入。沒有用 `--privileged`，沒有變更主機 qdisc。[設定](ip-loss-01/netem-setup.json)、[qdisc 清除](ip-loss-01/qdisc-cleanup.json)、[自有 3 容器清理](ip-loss-01/cleanup.json)均保存。
3. 第一次中途對帳 [soak-prefix/result.json](soak-prefix/result.json)原樣保留 FAIL：預期槽 0–1739，但查詢上界由起點 UTC 加 8,700 秒推算，下一槽 1740 的 UTC 比這個名義上界早 2.781ms，導致查詢多出 1 列。[診斷](prefix-boundary-diagnosis.json)把該列連回 slot1740 的 attempt／read_ok／committed。新查詢用**同一個來源快照**，以獨立觀察的下一槽 attempt UTC 作半開邊界，1740／1740 通過；沒有改活動程式、排除窗內異常列或用數量相等取代逐筆核對。此修正限本輪中途查詢；原完整長測 verifier 不變。
4. [完整性檢查](integrity-check.json)：舊靜態 770 檔、前輪 backlog 384 檔、封存與 Windows 活動來源各 17 檔、verifier 依賴 3 檔全部相符。[容器檢查](container-comparison.json)前後 17 個共享容器 ID 相同。原 COM3／COM4 未被本輪使用；[原程序](soak-processes-after.json)、[status 快照](soak-status-after.json)、[事件尾端](soak-tail-after.jsonl)持續更新。
5. [RED](tool-red.txt)先保存工具缺少的失敗，新增判定後 8 項通過；[獨立複核](reviews.md)及 [已複核來源 SHA256](reviewed-source-sha256.json)保存。未更動既有 output、manifest 或其他任務內容。

## 重現與接續

- [bench_ingest.py](../../services/delta/tools/bench_ingest.py)、[8 項判定測試](../../services/delta/tests/test_bench_ingest.py)。在權威 WSL checkout 以 `python3 services/delta/tools/bench_ingest.py --output <全新證據目錄>` 執行；需要現有快取 image、Docker、可讀取 ems-ingest 原設定。只建立自有 private namespace，拒絕覆寫 output，執行後收回自建容器。
- IP 丟包的 [worker 完整命令](ip-loss-01/worker-command.json)、[ownership 與映像](ip-loss-01/setup.json)、[tc 指令](ip-loss-01/netem-setup.json)保存實跑設定。重現必須建立全新自有 namespace，核對歸屬後才注入；不要在主機介面套用這份 qdisc。
- 下一個可靠性工作是 PRD-0021／ADR-030 的中央 committed receipt、穩定樣本身分／去重與缺筆對帳；本輪只驗證缺口，沒有實作它們。原 24h 預計 11/13 14:49:53 採樣結束後，仍須完整對帳。Pi／SD／4G／U701／CS1 全鏈路保持未驗收。
