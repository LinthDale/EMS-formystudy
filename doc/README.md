# EMS 文件與程式地圖

此版本聚焦無Pi採集與可靠送達；需求、實作、隔離測試與正式部署分別判讀。

| 任務 | 權威入口 |
|---|---|
| 最新版控與驗證 | [本次交付](releases/edge-reliability-20261113.md) |
| 採集交接與硬體待辦 | [溫度→Pi→EMS](operations/edge-temperature-handoff-20261112.md) |
| RTU／TCP採集 | [PRD-0020](prd/PRD-0020-delta-edge-telemetry.md)、[Delta](../services/delta/README.md) |
| 可靠送達需求與範圍 | [PRD-0021](prd/PRD-0021-multi-device-edge-reliability.md)、[子集三圖](architecture/edge-committed-telemetry.md) |
| 接收端／設定／部署 | [edge-receiver](../services/edge-receiver/README.md)、[opt-in Compose](../compose.edge-receiver.yml) |
| WAL／備份／還原操作 | [唯一操作手冊](../services/edge-receiver/WAL-PITR.md) |
| 決策與參數 | [ADR](adr/README.md)、[參數表](governance/tunable-parameters.md) |
| 開始工作／工作規範 | [AGENTS](../AGENTS.md)、[project_rules](../project_rules.md) |

正式部署、Pi／ADTEK／SD掉電／4G未由本輪驗收。原24h測試中斷，不以短測抵充。
