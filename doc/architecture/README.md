# Architecture Diagrams



> 對齊：`doc/PRD-架構設計-Guideline.md` §3.1（C4 Model）

本目錄收錄 EMS 系統三層架構圖：

| 檔案 | C4 層級 | 用途 |
|------|--------|------|
| [`c4-context.md`](c4-context.md) | Level 1 — System Context | 系統與外部 Actor / System 的關係 |
| [`c4-container.md`](c4-container.md) | Level 2 — Container | 服務、資料庫、佇列、外部 API 的部署單位 |
| [`data-flow.md`](data-flow.md) | Data Flow | 關鍵業務流程的資料流向（含同步 / 非同步標記） |

## 行為 / 控制視圖

| 檔案 | 類型 | 狀態 | 用途 |
|------|------|------|------|
| [`bess-operating-mode-state-machine.md`](bess-operating-mode-state-machine.md) | 狀態機規格 | Draft | BESS 併網 / 離網 / 故障運轉模式狀態機（控制策略討論稿；與 ADR-010 device 生命週期狀態機正交）|

## 方案與容量政策



## 維護規則

- 所有圖採 **Mermaid**（GitHub / VS Code 可直接渲染，無需外部工具）
- 同步呼叫：實線；非同步（MQTT / Queue）：虛線
- 跨網段邊界（OT/IT、Public/Private）以 subgraph 框出
- 任何 `docker-compose.yml`、`services/*`、外部整合的變更，必須同步更新對應圖

### RTU listener生命週期（ADR-040）

[ADR-040](../adr/ADR-040-delta-rtu-listener-recovery.md)在既有模擬器內加入串口監看／同埠重開，沿用同一資料context；不改部署拓樸／資料流，不新增服務或網路端點。物理USB恢復需另驗。

- [ADR-041 RTU不確定交易與有界恢復](../adr/ADR-041-rtu-uncertainty-and-bounded-recovery.md)：既有Delta edge內部狀態，C4拓樸不變；未知上界停採、field先核定及啟動隔離，真機准入仍待驗。

- [v2 committed telemetry 三圖](edge-committed-telemetry.md)：ADR-043／PRD-0021 §15.3，可靠送達子集已私有驗證；opt-in receiver／transaction receipts／四欄投影／session ACK，未切共享 v1 或 Pi 部署。



2026-11-13 [ADR-048](../adr/ADR-048-v2-live-backlog-fairness.md)／[v2子集](edge-committed-telemetry.md)補latest／oldest成功1:1公平送達，拓樸、身份／ACK及schema不變；[真還原／超量／延遲短測](../../output/no-pi-restore-load-20261113/README.md)38定點、419相鄰／12skip私有驗證。不是新核心已實作、PITR或現場SLA，未切共享。

2026-11-13：[ADR-050](../adr/ADR-050-database-tls-and-recovery-identity.md) 補強既有receiver→DB／DB→WAL TLS邊界及維運還原身分；[驗證](../../output/no-pi-wal-security-20261113/README.md)，元件／REST／topic不增。

2026-11-13：[ADR-051](../adr/ADR-051-pinned-recovery-and-slot-reseed.md) 補既有維運還原準入與lost-slot先保留再備份順序，元件／通訊／runtime不變；[38定點驗證](../../output/no-pi-critical-closure-20261113/README.md)。
