## IMPORTANT NOTES

> **Think using first principles. Do not always assume I am very clear about what I want and how to get it. Be prudent — start from the raw requirements and the problem itself. If the motivation and goal are unclear, stop and discuss with me. If the goal is clear but the path is not the shortest, tell me and suggest a better approach.**

每次完成重要的計畫後，要更新 `api/openapi.yml`、`doc/operations/容器速查表.md`、`doc/operations/操作手冊.md`（`doc/` 裡的重要文檔）還有 `README.md`。

---

## 架構強制規範

### 1. 嚴格遵循 PRD 架構設計 Guideline

所有架構決策、PRD 撰寫、系統設計、模組切分、API 制定、資料模型、部署策略，**一律遵循**：

- **權威文件**：`doc/PRD-架構設計-Guideline.md`
- 任何架構工作開始前，先讀過該文件第 2、3、4、10 章

### 2. 觸發條件（任一成立即須引用 Guideline）

- 新建模組 / 服務 / 容器
- 新增或變更 API（REST / MQTT topic / Modbus register / OCPP message）
- 新增或變更資料表 / Schema
- 跨服務通訊路徑變更
- 部署拓樸 / 網段邊界調整
- 安全或合規相關變更

### 3. 文件三同步義務（既有規則升級為硬性）

每次重大變更完成，**必須同步更新**：
1. `api/openapi.yml`
2. `doc/operations/容器速查表.md`
3. `doc/operations/操作手冊.md`
4. `README.md`

PR 缺一不予合併。

### 4. PRD 提交前自查

新功能 / 新服務 / 新整合須先寫 PRD，於 PR 描述中勾選 Guideline §10「PRD 品質 Checklist」全部項目；缺項須說明理由。

### 5. 架構變更走 ADR

PRD 鎖定後的架構變更，皆需以 ADR 形式登記於 `doc/adr/`，PR 連結對應 ADR。

### 6. WSL 為單一真相

`/home/emsuser/synaiq/EMS/` 為權威路徑；Windows 端 `C:\Users\User\synaiq\EMS\` 僅為備份，禁止直接編輯。

---

## PRD-First：未來改動必讀流程

> **致未來接手的工程師（含 AI agent）**：本節為**動手前的閱讀清單**。任何改動在開始之前，必先按順序讀過下列文件；違反此流程的 PR 不予合併。

### 14. 改動前必讀順序（強制）

```
1. project_rules.md（本檔）             ← 規範總則
       ↓
2. doc/PRD-架構設計-Guideline.md         ← 架構設計權威
       ↓
3. doc/prd/README.md（PRD 索引）          ← 找出與本次改動相關的 PRD
       ↓
4. 相關 PRD 全文（如 PRD-0001、PRD-0002） ← 理解設計意圖、Goals/Non-Goals、約束
       ↓
5. doc/architecture/{c4-context,c4-container,data-flow}.md  ← 確認改動影響範圍
       ↓
6. doc/adr/（與改動範圍相關的 ADR）       ← 理解既有決策與 Why
       ↓
7. doc/governance/risk-register.md + doc/governance/threat-model.md  ← 確認改動是否觸動既有風險
       ↓
8. 才開始撰寫程式碼 / 修改設定
```

「相關」的判斷：當改動觸發 §2 任一觸發條件時，至少有一份 PRD 與之相關。若無對應 PRD，**先寫 PRD（§15）再動手**。

### 15. 改動類型對應動作

| 改動類型 | 對應動作 |
|---------|---------|
| 新功能 / 新服務 / 新整合 | **先寫新 PRD**（PRD-NNNN），通過 §10 自查再開始實作 |
| 修改既有功能行為（FR 變更）| 在對應 PRD 附加變更紀錄（§15 附錄）+ 開 ADR 紀錄變更原因 |
| 修改架構（資料流 / 部署 / 服務拆併）| **新開 ADR**；若影響 PRD 的 §6 或 §7，更新對應 PRD |
| API / Schema / MQTT topic 變更 | 同步 `api/openapi.yml` + 對應 PRD §7/§8 + ADR-007（若 topic）|
| 修 bug（不改行為）| 不需新 PRD；於 commit message 引用相關 PRD 編號便於追溯 |
| 純 refactor（不改契約）| 不需新 PRD；於 PR 描述列出涵蓋的 PRD 編號確認契約未動 |
| 測試補強 / 文件補齊 | 不需新 PRD；於 PR 描述標明對應 PRD/ADR 編號 |
| 安全 / 合規調整 | 必須更新 `doc/governance/threat-model.md` + `doc/governance/risk-register.md` + 對應 ADR |

### 16. PR Checklist（與 PRD 對應）

PR 描述必須包含下列勾選欄位，缺項即 block：

```
## Related PRD / ADR
- 對應 PRD：[PRD-XXXX]（或「不適用」+ 理由）
- 新增 / 影響 ADR：[ADR-XXX]（或「無」）

## Pre-flight reading（請勾選已讀）
- [ ] project_rules.md
- [ ] doc/PRD-架構設計-Guideline.md（必要章節）
- [ ] 對應 PRD 全文
- [ ] 對應 ADR
- [ ] doc/governance/risk-register.md（評估是否觸動既有風險）
- [ ] doc/governance/threat-model.md（若涉及對外介面 / 認證 / 資料邊界）

## 文件四同步（§3）
- [ ] api/openapi.yml
- [ ] doc/operations/容器速查表.md
- [ ] doc/operations/操作手冊.md
- [ ] README.md

## 測試（§7-13）
- [ ] Unit / Integration / E2E 對照觸發條件全跑
- [ ] 新邏輯有對應測試
- [ ] 覆蓋率達 §10 下限

## Guideline §10 PRD Quality Checklist
- [ ] Goals / Non-Goals 清楚分離
- [ ] FR 編號可追蹤至測試
- [ ] NFR 量化（連動 doc/governance/nfr.md）
- [ ] 三張架構圖齊備（影響時更新）
- [ ] 風險登記已 review
```

### 17. AI Agent 指引

未來由 AI（Claude / Cursor / Copilot 等）執行改動時：
- 工作開始前，agent 必須**主動讀過 §14 完整清單**，並在 thinking 中列出讀過的檔案
- 若使用者提示與既有 PRD/ADR 衝突，**停下確認**而非自行決策（呼應檔頭 IMPORTANT NOTES 的 first principles 原則）
- agent 寫 PRD / ADR 時，文件結構嚴格遵守 Guideline 對應章節，不自創格式
- agent 撰寫程式碼前，先搜尋既有 PRD 是否已涵蓋；已涵蓋時引用該 PRD 的 FR 編號到 commit / PR

---

## 測試規範

> 以下規則由測試工程師視角制定。**測試不是選配，是交付的一部分。** 沒有對應測試的程式碼視為未完成。

### 7. 測試分層與職責

| 層級 | 位置 | 需要 Docker？ | 職責 |
|------|------|-------------|------|
| **Unit** | `tests/unit/` | 否 | 純函數、物理公式、API 端點合約（ASGI）、config 邏輯 |
| **Integration** | `tests/integration/` | 是 | DB schema/migration、REST API 合約、MQTT pipeline 流向 |
| **E2E** | `tests/integration/test_pipeline_*.py` | 是 | 端到端資料流、Modbus 寫入傳播、fault injection 回收 |

執行指令：
```bash
# Unit（不需 docker）
docker exec -w /app ems-simulator python -m pytest tests/unit -v

# Integration（需 docker compose up -d）
python -m pytest tests/integration -v -m integration
```

---

### 8. 觸發條件對照表（任一變更必須執行對應測試層）

| 變更類型 | Unit | Integration | E2E Pipeline | 說明 |
|----------|:----:|:-----------:|:------------:|------|
| 新增 / 修改 `services/simulator/src/` | ✅ 必跑 | — | — | 所有 unit tests 必須全 pass |
| 新增 FastAPI endpoint | ✅ 必跑 | ✅ 必跑 | — | 新 endpoint 必須有對應的 ASGI unit test + REST 合約測試 |
| 新增 / 修改 `services/*/telegraf.conf` | — | ✅ 必跑 | ✅ 必跑 | pipeline E2E 需驗證資料確實寫入 DB |
| 新增 / 修改 `infra/timescaledb/migrations/*.sql` | — | ✅ 必跑 | — | migration 必須有冪等性測試（跑兩次不 crash） |
| 新增 / 修改 `infra/timescaledb/init.sql` | — | ✅ 必跑 | — | `test_db_schema.py` 全項必須通過 |
| 新增 / 修改 `docker-compose.yml` | — | ✅ 必跑 | ✅ 必跑 | 新容器上線後所有 E2E pipeline 必須通過 |
| 新增 / 修改 `config/mcp-devices.yaml` | — | ✅ 必跑 | — | MCP 設備描述變更需對應 integration test |
| Bug fix | ✅ 必跑 | 視情況 | 視情況 | 修 bug 前先寫能重現 bug 的測試（TDD 修 bug） |
| Refactor（不改行為） | ✅ 必跑 | ✅ 必跑 | — | Refactor 後測試必須全 pass；若有 failure 即 regression |

---

### 9. 新功能開發強制流程

```
1. 寫 PRD（§4）
       ↓
2. 寫測試（先跑 RED — 測試失敗）
   - 純邏輯 → tests/unit/
   - 有 DB / HTTP / Modbus → tests/integration/
       ↓
3. 實作到測試全 GREEN
       ↓
4. 確認沒有既有測試變紅（regression check）
       ↓
5. 更新四份文件（§3）
       ↓
6. PR / commit
```

**跳過步驟 2（先實作再補測試）**視為違規，PR 不予合併。

---

### 10. 測試覆蓋率下限

| 範圍 | 最低要求 | 量測指令 |
|------|---------|---------|
| `services/simulator/src/` 純函數 | **90%** | `pytest tests/unit --cov=src --cov-report=term-missing` |
| FastAPI endpoint（行數覆蓋） | **80%** | 同上 |
| Migration SQL（冪等性） | **100%** — 每支 migration 都有對應測試 | 人工確認 |
| Pipeline E2E | **100%** — 每條資料路徑至少一個 E2E 測試 | 人工確認 |

覆蓋率低於下限時，PR 描述中必須說明豁免理由；無理由視為 block。

---

### 11. 測試命名與品質規範

**命名規則**（強制）：
- 測試函數名稱須描述行為，格式：`test_<前提>_<動作>_<預期結果>`
  - 好：`test_fault_zero_reduces_power_to_near_zero`
  - 壞：`test_fault`、`test_1`

**禁止事項**：
- 禁止 `time.sleep()` 超過 20 秒（E2E pipeline 測試除外，上限 60 秒）
- 禁止測試之間共用可變狀態（每個 test 必須可獨立執行）
- 禁止在 unit test 中啟動真實網路 / 檔案 I/O（使用 mock）
- 禁止 `assert True` 或空 assert（無意義測試）
- 禁止 hardcode 容器 IP（使用 service name 或環境變數）

**必要事項**：
- 每個測試必須有清楚的 failure message（`assert x == y, f"got {x}"` 格式）
- 觸碰真實資源的測試（DB、HTTP）必須標記 `@pytest.mark.integration`
- 測試後必須還原狀態（use fixture teardown，不留測試垃圾資料）

---

### 12. 測試失敗處理規範

| 情境 | 必要動作 |
|------|---------|
| Unit test 失敗 | **立即修復**，不得帶著紅燈繼續開發 |
| Integration test 失敗（本機） | 先確認 docker 狀態正常，再 debug 測試或程式 |
| Integration test 失敗（環境問題） | 在 PR 中說明環境問題並附 skip 理由，**不得刪除測試** |
| Flaky test（偶爾失敗） | 標記 `@pytest.mark.xfail(strict=False)` 並立即開 issue 追蹤，30 天內修復 |
| 新功能上線後 E2E 失敗 | 視為 **P0 bug**，立即回滾或修復，不得繼續 merge 其他 PR |

---

### 13. 測試檔案與程式碼同步義務

每次以下檔案有變更，對應測試檔案**必須在同一個 PR / commit 中一起更新**：

| 程式碼變更 | 必須同步更新的測試 |
|-----------|-----------------|
| `services/simulator/src/main.py` | `tests/unit/test_float_registers.py`、`test_simulation_math.py`、`test_simulator_api.py` |
| `services/gateway/telegraf.conf` | `tests/integration/test_pipeline_electricity.py` |
| `services/kc-gateway/telegraf.conf` | `tests/integration/test_pipeline_factory.py` |
| `services/kc-ingest/telegraf.conf` | `tests/integration/test_pipeline_factory.py` |
| `infra/timescaledb/init.sql` | `tests/integration/test_db_schema.py` |
| `infra/timescaledb/migrations/` 新增檔案 | `tests/integration/test_migrations.py` 新增對應 class |
| `config/mcp-devices.yaml` | `tests/integration/test_pipeline_factory.py` MCP 區段 |

測試檔案與程式碼分離 PR 提交視為**不完整交付**，不予合併。

---

### 18. 依賴與安裝需求清單維護

根目錄 `requirements.txt` 是可直接用 pip 安裝的本機 Python 開發 / 測試需求檔：

```bash
python -m pip install -r requirements.txt
```

`requirements-inventory.md` 是本專案的完整執行需求總表，涵蓋：

- 主機端必要工具，例如 Docker Engine、Docker Compose、Git、curl
- Docker image 與本地 build image
- 各 Python service 的 runtime dependencies
- 測試 dependencies
- 可選維運/除錯工具，例如 mosquitto-clients、postgresql-client
- Demo/對外公開工具，例如 cloudflared、Tailscale
- 可選前端 dashboard 開發工具與 npm dependencies

任何 PR / commit 只要新增、移除或升級下列項目，必須同步更新根目錄 `requirements.txt`：

- 本機開發 / 測試需要 pip 安裝的新 Python 套件
- `services/simulator/requirements.txt`
- `tests/requirements-test.txt`

任何 PR / commit 只要新增、移除或升級下列項目，必須同步更新 `requirements-inventory.md`：

- `docker-compose.yml` 中的 image、build service、port/runtime 需求
- `services/*/requirements.txt`
- `external/*/pyproject.toml`
- `tests/requirements-test.txt`
- `package.json` / 前端工具鏈
- 文件或操作手冊要求使用的新 CLI、daemon、雲端工具或外部服務

注意：KC 外部專案維持各自的 `pyproject.toml` 與容器環境，不強行合併進根目錄 `requirements.txt`。目前 EMS simulator 鎖定 `pymodbus==3.6.9`，KC 外部專案使用 `pymodbus>=3.7.0`，合併到同一個 pip 環境會造成版本解析衝突。

### 19. 可調參數集中管理（可調參數表）

所有「可調整 / 運行期可能需要調整」的參數**不可散落為各模組的硬編 magic constant**（例如 LLM `max_tokens`、reservation token 估算、信心門檻、retry 次數、cache 上限、dedupe / rate-limit 視窗、reconnect 延遲、月預算、provider/model pricing 等）。必須：

1. **集中於單一 config 介面**（device-service 為 `config.Settings`，pydantic-settings），且提供**單一有註解的參數檔** [`config/device-service.toml`](config/device-service.toml) 作為人類調參主檔；載入優先序 env > `.env` > toml > 程式 default，spec / 合理值作為 default，**改檔重啟即生效**。機密只放 `.env`。
2. **登錄於可調參數表** [`doc/governance/tunable-parameters.md`](doc/governance/tunable-parameters.md)：每個參數列 名稱 / env var / 預設 / 單位 / 所屬模組 / 對應 FR-ADR / 是否 spec-locked。
3. **區分兩類**：
   - **operational 可調**（timeout、threshold、max_tokens、budget、retries、cache、reconnect、pricing…）→ 走 `Settings`，env 可覆寫。
   - **security / spec-mandated 限制**（payload size、欄位數、樣本上限、reasoning 上限、id regex 等，由 PRD/ADR 鎖定）→ 仍登錄於表中並標 **spec-locked**；放寬須走 ADR，不可隨意 env 調降。
4. 新增 / 修改此類參數時，**同步更新 `tunable-parameters.md`**（納入 §3 文件同步義務精神）。
5. 注意**跨參數耦合**要在表中標明（例：LLM 輸出 `max_tokens` 必須等於 budget reservation 的輸出上限 `RESERVE_OUTPUT_TOKENS`，否則 hard cap 失效）。

> 動機：避免 `max_tokens=1024` 之類數字寫死在程式各處、無調整空間、耦合不可見。集中表化使調參、稽核、跨參數耦合一目了然。