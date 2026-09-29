# ADR-029：Delta 共用解析、唯讀邊緣採集與四欄相容投影
## Status
Accepted（2026-09-29；local scope） for local implementation (2026-09-29)，PRD-0020；使用者授權新增Delta simulator及parser。
## Context
Delta V1.35需要動態倍率與device-specific字序，純Telegraf固定scale不能完整處理。SIM7600G-H由Pi OS建立IP網路，現場設備可RTU或TCP。現有EMS寬表與BFF只提供electricity/factory，PRD-0006窄表仍Draft。
## Decision
新增獨立services/delta套件，decoder純函數、pymodbus==3.6.9只讀FC04 client、TCP simulator、SQLite outbox、paho-mqtt。Pi原生Python/systemd，Docker僅local demo。這是ADR-003對Delta動態scale之增補，不改既有Telegraf配置。
四欄沿既有ems/devices topic與gateway routing：L1 phase voltage、L1 current、total AC kW、lifetime kWh。詳細數據CLI/outbox保留，不能宣稱完整協定或已存所有signals。無遠端控制。TLS field mode強制驗證且需帳密或client cert；明示demo才可plain。保留來源時間；QoS1只保證到broker ACK，現有DB可能重複/遺失，不宣稱exactly-once。
## Consequences
共享parser降低模擬與現場差異；本機現有UI無須新solar schema。需人工確認機型/韌體及address base；更多訊號儲存/顯示後續由PRD-0006承接。Simulator和parser共用map的風險由獨立PDF vectors與真實socket封包測試制衡。範本不自動暴露任何public broker。實機4G、RTU、broker授權尚待現場驗證。
