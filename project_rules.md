## IMPORTANT NOTES

> **Think using first principles. Do not always assume I am very clear about what I want and how to get it. Be prudent — start from the raw requirements and the problem itself. If the motivation and goal are unclear, stop and discuss with me. If the goal is clear but the path is not the shortest, tell me and suggest a better approach.**

每次完成重要的計畫後，要更新 `api/openapi.yml`、`doc/容器速查表.md`、`doc/操作手冊.md`（`doc/` 裡的重要文檔）還有 `README.md`。

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
2. `doc/容器速查表.md`
3. `doc/操作手冊.md`
4. `README.md`

PR 缺一不予合併。

### 4. PRD 提交前自查

新功能 / 新服務 / 新整合須先寫 PRD，於 PR 描述中勾選 Guideline §10「PRD 品質 Checklist」全部項目；缺項須說明理由。

### 5. 架構變更走 ADR

PRD 鎖定後的架構變更，皆需以 ADR 形式登記於 `doc/adr/`，PR 連結對應 ADR。

### 6. WSL 為單一真相

`/home/emsuser/synaiq/EMS/` 為權威路徑；Windows 端 `C:\Users\User\synaiq\EMS\` 僅為備份，禁止直接編輯。

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
