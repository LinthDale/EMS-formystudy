# ADR-002：pymodbus 鎖定 3.6.9

## Status
Accepted（2026-04-22）

## Context

simulator 服務需要實作 Modbus TCP slave，初次採用 `pymodbus>=3.6,<4.0` 的彈性區間。實作時遇到：

```
ImportError: cannot import name 'ModbusSlaveContext' from 'pymodbus.datastore'
```

調查發現 pymodbus 在 3.7 → 3.13 之間經歷兩次 API 重大改寫：
- 3.6 系列：使用經典 `ModbusSlaveContext` / `ModbusServerContext` API
- 3.7+：引入 `SimData` / `SimDevice` 新 API，經典 API 部分能力被移除
- 3.13：完成新 API 重寫，舊範例多數無法直接運行

ranges 寫法跨越 breaking change，pip 任意 resolve 到 3.13 即崩潰。

## Decision

`requirements.txt` 把 pymodbus 鎖定為 **`pymodbus==3.6.9`**（最後一個經典 API 完整保留的版本）。

```
pymodbus==3.6.9
```

非核心依賴亦比照辦理：跨 minor version 有風險的套件一律鎖到 patch level，並在升級時走 ADR。

## Consequences

**正面**
- 環境可重現；`docker compose build` 任何時間結果一致
- 範例與現有程式碼相容，省去學新 API 的時間
- 鎖版規則明確，新人不會誤升級

**負面**
- 失去新版的 bug fix 與功能（影響有限：Stage 1 / 2 用不到新 API）
- 若 3.6.9 出現 CVE，必須評估遷移到 3.13+ 新 API 的成本
- 鎖死 patch level 會導致所有間接相依套件被連帶限制

**後續觸發**
- 若 pymodbus 3.6.x 出現 security advisory 或新功能必要，開新 ADR 評估遷移到 SimData API
- 升級前先寫 spike：用新 API 重寫 simulator 一個 endpoint 驗證可行性
