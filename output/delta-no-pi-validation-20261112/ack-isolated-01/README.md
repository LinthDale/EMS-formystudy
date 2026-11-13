# 第9關：v1遺失／重複反例已重現，系統驗收FAIL

使用真實、私有 Mosquitto broker、production Publisher／Outbox／drain，以及受控SQLite接收器。不是正式Telegraf／Timescale接收端，也不是v2實作。結果見 [run/result.json](run/result.json)。

| 案例 | 實測 | 判定 |
|---|---|---|
| broker PUBACK、接收器不commit | 接收1、commit0、本地pending0 | 未入庫已清本地，可靠送達FAIL |
| 接收器commit、傳送端本地確認被抑制，再重送 | 首次真PUBACK；首次commit1、pending1；重送後commit2、pending0 | 相同payload重複入庫，FAIL |
| 相同payload投遞兩次 | 接收2、commit2、pending0 | 沒有去重，FAIL |

`reproduction_passed=true`只表示反例成功重現；`system_acceptance_passed=false`才是系統驗收結果。接收器無非預期錯誤。第二案是在真PUBACK之後抑制本地返回確認，不是v2 DB-ACK封包遺失；第一案是受控不commit，不是停止共用DB。

隔離broker採`--network none`、無host port；測試worker只加入該broker的network namespace，工具比對`DELTA_ACK_PROBE_NETNS`與`/proc/self/ns/net`，拒絕未隔離環境。broker來源為本機快取eclipse-mosquitto:2 image sha256:a908c65cc8e67ec9d292ef27c2c0360dbaaee7eb1b935cdd194e67697f15dea1。完成後自有broker已停止，見 [隔離資訊](isolation.json)、[清理結果](cleanup.json)。沒有操作COM或共用EMS服務。

重跑須新建network-none broker、取得其namespace，將本服務唯讀掛入私有worker後執行`python tools/bench_ack.py --output /evidence/new-run`；環境變數必須是該私有namespace。不可直接對共享broker執行。每次用全新輸出目錄。

結論：第9關v1不合格。PRD-0021的持久樣本身分、中央commit receipt、去重與對帳仍待實作後另驗。長測正常送達不能抵銷本反例。正式DB的唯讀index盤點仍無measurement唯一鍵；私有接收器結果不可冒稱正式DB故障實測。
