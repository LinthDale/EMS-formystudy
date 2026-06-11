# PRD 架構設計 Guideline

> 版本：v1.0  
> 日期：2026-04-28  
> 作者：架構組  
> 適用範圍：所有新功能、模組重構、跨系統整合的 PRD 文件

---

## 0. 文件定位

PRD（Product Requirements Document）並非「需求堆疊清單」，而是 **使團隊在實作前對齊「為什麼要做、做什麼、如何驗收」** 的單一真實來源（Single Source of Truth）。

本 Guideline 規範 PRD 的 **架構章節**，確保：
- 每份 PRD 在進入 TDD 實作前，已完成風險、依賴、邊界的辨識
- 不同作者產出的 PRD 在結構、用詞、深度上具一致性
- PRD 可被 planner / architect / tdd-guide 等 agent 直接消化使用

---

## 1. First-Principles 啟動原則

撰寫 PRD 前，**強制回到原始需求**：

1. **問題陳述（Problem Statement）**：用一段話描述現況痛點，禁止跳過
2. **目標（Goal）**：可量化，例：「將 OCPP 連線重連時間自 30s 降至 5s」
3. **非目標（Non-Goal）**：明確列出本次「不做」的範圍，避免範疇蔓延
4. **約束條件（Constraints）**：法規、合約、硬體、預算、時程

> 若以上 4 項任一無法清楚描述，**停下來與 Stakeholder 確認**，不要先寫架構。

---

## 2. PRD 標準章節結構

每份 PRD 必須包含以下章節，順序固定：

| # | 章節 | 必填 | 用途 |
|---|------|------|------|
| 1 | Overview & Context | ✅ | 業務背景、市場定位、上下游 |
| 2 | Goals / Non-Goals | ✅ | First-principles 拆解 |
| 3 | User Stories & Personas | ✅ | 使用者場景與角色 |
| 4 | Functional Requirements | ✅ | 功能列表（編號管理） |
| 5 | Non-Functional Requirements | ✅ | 效能、可用性、安全、合規 |
| 6 | System Architecture | ✅ | 元件圖、資料流、部署拓樸 |
| 7 | Data Model | ✅ | Schema、ER 圖、關鍵欄位 |
| 8 | API Contract | ✅ | OpenAPI / gRPC / MQTT topic |
| 9 | Security & Privacy | ✅ | Threat model、資料分級 |
| 10 | Observability | ✅ | Log、Metric、Trace、Alert |
| 11 | Risks & Mitigations | ✅ | 已知風險與對策 |
| 12 | Rollout & Migration Plan | ✅ | 上線策略、回滾計畫 |
| 13 | Test Strategy | ✅ | 單元 / 整合 / E2E / 驗收 |
| 14 | Open Questions | ⚠️ | 待釐清問題清單 |
| 15 | Appendix | ⚠️ | 參考資料、決策紀錄 |

---

## 3. 架構章節撰寫規範（重點）

### 3.1 System Architecture

必須包含以下 **三張圖**：

1. **C4 Level 1 — System Context Diagram**：本系統與外部 Actor / System 的關係
2. **C4 Level 2 — Container Diagram**：服務、資料庫、佇列、外部 API 的部署單位
3. **Data Flow Diagram**：關鍵業務流程的資料流向（含同步 / 非同步標記）

**規則**：
- 每個元件須標註：技術選型、部署位置、Owner
- 同步呼叫用實線；非同步（Event / Queue）用虛線
- 跨網段邊界須明確畫出（VPC、DMZ、OT/IT 區隔）

### 3.2 Data Model

- 使用 **DBML** 或 **Mermaid erDiagram** 描述
- 每張表須註明：主鍵、唯一索引、外鍵、保留期、PII 欄位
- 時序資料（Time-series）獨立章節，標明取樣頻率與壓縮策略
- **不可變資料優先**：事件 / 計量資料應採 append-only，避免 in-place update

### 3.3 API Contract

- REST API：以 **OpenAPI 3.1** 撰寫，放於 `api/openapi.yml`（專案實際路徑；早期文件寫的 `doc/API.yaml` 為舊路徑，已不使用）
- 即時通訊（MQTT / WebSocket）：列出 Topic 階層、QoS、Payload schema
- 工控協定（Modbus / OCPP / IEC 61850）：列出 register map / message type
- **每個 API 須標註**：冪等性、重試策略、速率限制、認證方式

### 3.4 Non-Functional Requirements（量化）

避免「高效能」「高可用」這類模糊敘述，改為：

| 維度 | 指標 | 目標值 |
|------|------|--------|
| 延遲 | p99 API latency | < 200ms |
| 吞吐量 | 計量資料寫入 | 10,000 points/sec |
| 可用性 | 月度 SLO | 99.9% |
| RTO | 災難復原時間 | < 15 min |
| RPO | 資料遺失容忍 | < 1 min |

---

## 4. 設計原則 Checklist

### 4.1 不可變性（Immutability）

- [ ] 領域事件採 append-only，不允許修改歷史
- [ ] 設定檔變更走版本化，不直接覆寫
- [ ] DTO / Value Object 採 immutable 設計

### 4.2 模組化與檔案組織

- [ ] 元件依「業務領域」切分，非依「技術層」切分
- [ ] 單一檔案 200–400 行為宜，硬上限 800 行
- [ ] 高內聚、低耦合，介面以 contract 為界

### 4.3 邊界輸入驗證

- [ ] 所有外部輸入（API、檔案、訊息佇列）皆有 schema 驗證
- [ ] 失敗時 fail-fast，回傳明確錯誤代碼
- [ ] 不信任任何外部資料，含上游服務回應

### 4.4 安全性

- [ ] 無硬編碼密鑰；採用 Secret Manager
- [ ] 認證（AuthN）與授權（AuthZ）分離
- [ ] 資料分級：PII / 商業機密 / 公開
- [ ] OWASP Top 10 對照檢查
- [ ] 工控資安（IEC 62443）：OT/IT 分區、白名單

### 4.5 可觀測性

- [ ] 結構化 Log（JSON），含 trace_id
- [ ] 黃金訊號（Latency / Traffic / Errors / Saturation）皆有 Metric
- [ ] 關鍵流程有分散式追蹤
- [ ] 告警有明確 Runbook

---

## 5. 風險登錄表（Risk Register）

每個風險需具備四欄位：

| 風險 | 機率 (L/M/H) | 衝擊 (L/M/H) | 緩解措施 |
|------|--------------|--------------|----------|
| 範例：Modbus TCP 與儲能 BMS 規格不一致 | M | H | 預留 adapter 層，先以 mock device 驗證 |

---

## 6. 上線與回滾策略

### 6.1 部署策略選擇

| 策略 | 適用情境 |
|------|---------|
| Blue-Green | 全量切換，需要快速回滾 |
| Canary | 風險高、流量大、可漸進驗證 |
| Feature Flag | 後端已部署、前端漸進開放 |
| Shadow Traffic | 演算法 / 模型驗證，不影響使用者 |

### 6.2 回滾條件（Rollback Triggers）

PRD 須明確列出**自動回滾**與**人工回滾**的條件門檻，例：
- 錯誤率 > 1% 持續 5 分鐘 → 自動回滾
- p99 latency > 500ms 持續 10 分鐘 → 通知 on-call 評估

---

## 7. 測試策略章節

### 7.1 覆蓋率要求

- 單元測試覆蓋率 ≥ 80%
- 整合測試覆蓋所有外部依賴邊界
- E2E 測試覆蓋所有 P0 使用者流程

### 7.2 TDD 流程聲明

PRD 須聲明採行 RED → GREEN → REFACTOR：

1. **RED**：先寫驗收測試 / 單元測試
2. **GREEN**：以最小程式碼通過
3. **REFACTOR**：在綠燈下重構

### 7.3 測試資料策略

- 不使用正式環境資料；以匿名化 / 合成資料為主
- 時序資料採可重現的 seed
- 第三方依賴採 contract test + mock

---

## 8. PRD 撰寫流程（Workflow）

```
[Idea] 
  ↓
[1] First-principles：明確 Goal / Non-Goal
  ↓
[2] 研究既有方案（GitHub search → Library docs → Exa）
  ↓
[3] 撰寫 PRD 草稿（依本 Guideline 章節）
  ↓
[4] Architect Review（架構師簽核）
  ↓
[5] Security Review（安全審查）
  ↓
[6] Stakeholder Sign-off（業務 / PM / Tech Lead）
  ↓
[7] 進入 TDD 實作
  ↓
[8] PRD 鎖定版本，後續變更走 ADR
```

---

## 9. 變更管理（ADR）

PRD 鎖定後，任何架構變更走 **Architecture Decision Record**：

```markdown
# ADR-NNN：標題

## Status
Proposed | Accepted | Deprecated | Superseded by ADR-XXX

## Context
為什麼需要這個決策？

## Decision
決定採用什麼方案？

## Consequences
正面 / 負面影響？
```

ADR 放於 `doc/adr/`，與 PRD 雙向連結。

---

## 10. PRD 品質 Checklist（提交前自查）

- [ ] Goals 與 Non-Goals 清楚分離
- [ ] Functional Requirements 全部編號，可追蹤至測試案例
- [ ] Non-Functional Requirements 全部量化
- [ ] 三張架構圖齊備（Context / Container / Data Flow）
- [ ] Data Model 標註 PII 欄位與保留期
- [ ] API Contract 已同步至 `api/openapi.yml`
- [ ] 風險登錄表至少列出 5 項
- [ ] 上線策略與回滾條件明確
- [ ] 測試策略涵蓋三層（Unit / Integration / E2E）
- [ ] Open Questions 已列出未解事項
- [ ] 已通過 architect 與 security-reviewer agent 審查

---

## 11. EMS 專案特化補充

> 適用於商業 / 工業 EMS 專案

### 11.1 必備章節擴充

- **OT/IT 邊界**：明確區分量測層、控制層、應用層
- **通訊協定矩陣**：Modbus TCP/RTU、IEC 61850、OCPP 1.6/2.0.1、SunSpec、BACnet
- **計量資料規格**：取樣頻率、聚合層級（1s/1min/15min/1h/1day）、保留策略
- **法規對應**：台電併聯 / 售電契約 / 儲能調度 / 個資法

### 11.2 EMS 同步義務

每次重大 PRD 完成後，**必須同步更新**（對齊 `project_rules.md §3`）：
1. `api/openapi.yml`（專案實際路徑；舊文件寫的 `doc/API.yaml` 已不使用）
2. `doc/operations/容器速查表.md`（Container Cheat Sheet）
3. `doc/operations/操作手冊.md`（Operations Manual）
4. `README.md`

此為硬性流程要求，PR 缺一不予合併。

---

## 12. 範本（Template）

新建 PRD 請複製以下骨架：

```markdown
# PRD-XXXX：<功能名稱>

## 1. Overview & Context
## 2. Goals / Non-Goals
## 3. User Stories & Personas
## 4. Functional Requirements
   - FR-001:
   - FR-002:
## 5. Non-Functional Requirements
## 6. System Architecture
   - 6.1 Context Diagram
   - 6.2 Container Diagram
   - 6.3 Data Flow
## 7. Data Model
## 8. API Contract
## 9. Security & Privacy
## 10. Observability
## 11. Risks & Mitigations
## 12. Rollout & Migration Plan
## 13. Test Strategy
## 14. Open Questions
## 15. Appendix
```

---

## 附錄 A：參考標準

- C4 Model — https://c4model.com
- OpenAPI 3.1 Specification
- IEC 62443（工控資安）
- ISO/IEC 25010（軟體品質模型）
- Google SRE Book — SLI / SLO / SLA
- ADR — https://adr.github.io

## 附錄 B：相關 Agent 對照

| 階段 | 推薦 Agent |
|------|-----------|
| 規劃 | planner |
| 架構決策 | architect |
| 撰寫測試 | tdd-guide |
| 程式審查 | code-reviewer |
| 安全審查 | security-reviewer |
| 文件同步 | doc-updater |

---

*本 Guideline 為活文件，每季 review 一次。修訂建議請開 PR 修改本檔 `doc/PRD-架構設計-Guideline.md`。*
