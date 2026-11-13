# BMS／EMS Product Program 文件索引

本目錄保存 100 kWh 級 BESS 自研 BMS／EMS 的正式規劃基線。產品需求仍依 `doc/prd/README.md` 分配正式 PRD 編號；本目錄不取代單一功能 PRD。

## 受控文件

| 文件 | 用途 |
|---|---|
| `EMS-BMS-Master-Program-Plan.md` | Reference Product、架構、PRD family、24 個月時程、Gate、選商與經費基線 |
| `../architecture/ems-edge-cloud-platform-architecture.md` | EMS Edge／Cloud、網路、資料、控制與產品化架構審查 |
| `../../output/pdf/ems-100kwh-system-design-specification.md` | EMS 系統設計與實作規格 |
| `../../output/pdf/bms-100kwh-system-design-specification.md` | BMS 系統設計規格 |
| `../../output/pdf/建議採用的產品型號.md` | 候選料號與 RFQ 清單；不是核准採購單 |

## 文件優先序

1. 已核准 PRD／ADR／ICD。
2. `EMS-BMS-Master-Program-Plan.md` 的產品、時程與經費基線。
3. BMS／EMS 系統設計規格。
4. 架構審查、benchmark 與候選清單。
5. `tmp/architecture_prd_agents/` 內交叉審查稿僅作證據與追溯，不作正式設計輸入。

若文件衝突，應建立 issue／ADR，禁止由實作者自行選擇較方便的數值。
