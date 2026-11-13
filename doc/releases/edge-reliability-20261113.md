# Edge可靠送達版控交付 — 2026-11-13

本輪使用者要求推送及記錄版控。專用分支 `codex/edge-reliability-20261113`；基底 `79427c6e160832d297972b8c651604f4bd0ecf84`。程式快照採 annotated tag `edge-reliability-20261113`；實際commit與遠端查核見後續[版控收據](edge-reliability-20261113-receipt.json)。本輪不合併main/dev、不部署或重啟服務。

## 交付內容

- Delta RTU不確定交易與listener恢復、v2原子outbox／身份／ACK驗證、容量最舊淘汰保最新、最新／最舊成功1:1。
- opt-in中央receiver／migration019–021，receipt及投影原子去重、field強制驗證DB／WAL TLS與同步flush後ACK。
- 備份校驗／外置cluster身分／核定timeline與target；中央資料滿、slot lost與新保護鏈真PITR、同cluster分支反例。
- 程式、設定、測試的bytes與原已驗證來源逐檔一致。共用文件只取本輪相關段落；其他微電網／大甲／網站及清理工作留在原目錄，未混入此分支。

## 驗證與範圍

[最終三項](../../output/no-pi-critical-closure-20261113/README.md)：38通過18.00秒；相鄰616通過／12既有專用skip／36.06秒、coverage91.73%；新增48單測包含在回歸，不加總。獨立code／Python／security／architecture複核通過；slot-before-base空窗已修。

[來源／證據清單](edge-reliability-20261113-evidence.json)列出Git內證據SHA256及本機完整封存位置。**Git僅含精簡文字證據；完整實體備份、WAL、SQLite、來源快照與大型產物保留在權威WSL的output原封存**。各原artifact-sha256.json是完整本機封存manifest，fresh clone不含全部原始檔，不能把它當Git檔案集合直接全量驗證。Git內證據用本交付evidence.json的included_evidence驗證。

OpenAPI調為2.2.1並補CHANGELOG；REST paths/components/servers/tags與基底完全一致，wire2/schema3不變。既有GitHub CI只針對dev/main或PR，本次feature分支推送不宣稱已觸發遠端CI。未重跑長測；原24h中斷仍保留，Pi／ADTEK／實體SD掉電／4G及正式部署另驗。

## 重現入口

[私有驗證工具](../../services/edge-receiver/tools/verify_private.py)、[receiver](../../services/edge-receiver/README.md)、[WAL/PITR操作](../../services/edge-receiver/WAL-PITR.md)。工具需本機Docker、Python、openssl，以及images.json記錄的cached映像；本次已驗證映像ID在各run中。測試worker套件為Python3.11／pytest8.4.2／pytest-cov6.3.0／pymodbus3.6.9／paho-mqtt2.1.0／pyserial3.5／asyncpg0.31.0。正式建置沿各服務Dockerfile與requirements；本次沒有把測試映像匯入Git，也未驗從全新無cache環境bootstrap。

```sh
python3 services/edge-receiver/tools/verify_private.py --suite critical --output /tmp/ems-critical-new-run
python3 services/edge-receiver/tools/verify_private.py --suite baseline --output /tmp/ems-baseline-new-run
```

輸出必須用新目錄；不操作共享stack／COM，測試容器結束清理。只在另有需要重現時執行，不代表本次又重跑長測。
