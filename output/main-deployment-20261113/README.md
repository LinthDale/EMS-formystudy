# main部署證據（2026-11-13）

合併／Delta映像更新／公開入口恢復與短驗證完成；**完整v2 receiver/WAL切換尚未完成**，等待獨立WAL主機及可用SSH入口。無長測重跑。

- [合併與回復版本](state.json)、[部署前17容器](containers-before.json)、[建置映像](built-images.json)。
- [部署前公開504](health-before.json)、[轉送恢復](public-after-relay.json)。
- [Delta部署／queue backup資訊](delta-deployment-preflight.json)、[已更新映像](delta-deployment.json)、[部署overlay](delta-main-image.yml)、[回復overlay](delta-rollback.yml)。
- [CI六項success](ci-success.json)、[公開及本機完整短smoke](postdeploy-smoke.json)、[公開API與DB來源時間/四值一致](public-db-match.json)。
- 初版probe的records422是漏必填since/until，HTTP401是Python未送Secure cookie；已改正探測方式，原始診斷留本機，不將它們當production修復。

[部署紀錄與待辦](../../doc/releases/edge-reliability-main-deployment-20261113.md)。私有queue備份不進Git；原始命令/日誌及後續final遠端核對留權威checkout本目錄。
