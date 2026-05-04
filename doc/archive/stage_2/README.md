# Stage 2：看得到 — 進度紀錄

> 完成日期：2026-04-23
> 依據：Stage 1 管線通了之後接 Grafana provisioning

---

## 1. 達成狀態

**✅ Stage 2 所有驗收條件通過**

目標：瀏覽器打開儀表板，值持續更新；功率超限自動 Telegram 告警。

---

## 2. 新增架構

```
┌──────────┐  Modbus  ┌──────────┐  MQTT  ┌──────────┐  SQL  ┌─────────────┐
│simulator │──TCP──▶ │ gateway  │───────▶│ ingest   │──────▶│ TimescaleDB │
└──────────┘          └──────────┘         └──────────┘       └──────┬──────┘
                                                                      │ SQL
                                                               ┌──────▼──────┐
                                                               │   Grafana   │──▶ Telegram
                                                               │  :3000      │
                                                               └─────────────┘
```

---

## 3. 新增容器

| 容器 | 鏡像 | Port | 功能 | 自寫？ |
|------|------|------|------|-------|
| ems-grafana | grafana/grafana-oss:11.3.0 | 3000 | 儀表板 + 告警 + Telegram 通知 | ❌ 只 provisioning |

---

## 4. Provisioning 結構

```
infra/grafana/provisioning/
├── datasources/
│   └── timescaledb.yaml          # PostgreSQL 連線（TimescaleDB）
├── dashboards/
│   ├── dashboards.yaml           # provider（讀 JSON 的位置）
│   └── ems-overview.json         # 儀表板定義（6 panels）
└── alerting/
    ├── contact-points.yaml       # Telegram bot token + chat_id
    ├── notification-policies.yaml # 路由：全部 → Telegram
    └── rules.yaml                # 告警規則 power_kw > 100 kW for 30s
```

---

## 5. 儀表板 panels

| # | 類型 | 標題 | 說明 |
|---|------|------|------|
| 1 | Stat | 目前功率 (kW) | 最近 1 分鐘均值，超 100 kW 變紅 |
| 2 | Stat | 電壓 (V) | 最近 1 分鐘均值，200–230 V 綠 |
| 3 | Stat | 電流 (A) | 最近 1 分鐘均值，超 15 A 變紅 |
| 4 | Stat | 累計電量 (kWh) | 最近 1 分鐘最大值 |
| 5 | Timeseries | 功率曲線 (kW) | 24 小時曲線，100 kW 閾值線 |
| 6 | Timeseries | 電壓 / 電流曲線 | 左軸 V、右軸 A，24 小時 |

---

## 6. 告警規則

| 欄位 | 設定 |
|------|------|
| 條件 | 過去 5 分鐘 power_kw 平均 > 100 kW |
| 持續時間 | 30 秒後才觸發（避免瞬間尖峰誤報）|
| 評估週期 | 每 1 分鐘 |
| 通知目標 | Telegram（bot token + chat_id 在 .env）|
| 群組等待 | 10 秒（第一次送出延遲）|
| 重複間隔 | 4 小時（同一告警不連續轟炸）|

---

## 7. 驗收結果

| 步驟 | 指令 | 結果 |
|------|------|------|
| 1. Grafana 活著 | `http://localhost:3000` | 登入畫面出現 ✓ |
| 2. Datasource 通 | `GET /api/datasources/uid/timescaledb-ems/health` | `{"status":"OK"}` ✓ |
| 3. Dashboard 載入 | `GET /api/dashboards/uid/ems-overview` | `panels: 6` ✓ |
| 4. 告警規則存在 | Prometheus API `/rules` | `state: firing` ✓ |
| 5. Telegram 收到 | `POST /config?power_base_kw=120` 觸發 | 收到告警訊息 ✓ |

---

## 8. 修了 5 個 Bug

| # | 問題 | 根因 | 修法 |
|---|------|------|------|
| 1 | Telegram chatid 型別錯誤 | Grafana alerting provisioning 把數字 env var 解成 JSON number | 在 YAML 硬寫 `"7171144544"` 字串；env var 對純數字無效 |
| 2 | Grafana 連不到 TimescaleDB | `docker restart` 繞過 Compose 網路管理，容器不在 `ems_default` | 永遠用 `docker compose up -d`，不用 `docker restart` |
| 3 | Grafana 外網 DNS 失敗 | WSL2 的 Docker 預設 DNS `10.0.0.53` 在此環境不通 | 在 compose 的 grafana 服務加 `dns: [1.1.1.1, 9.9.9.9, 8.8.8.8]`（只影響這個容器）|
| 4 | Telegram message template 語法錯誤 | 根物件是 `ExtendedData`，不能直接用 `.Labels.alertname` | 改成 `{{ range .Alerts }}{{ .Labels.alertname }}{{ end }}` |
| 5 | 告警路由到 email 不到 Telegram | Grafana 11 `alertingSimplifiedRouting=true` 預設走 email | 在 rules.yaml 加 `notification_settings: receiver: Telegram` |

---

## 9. 關鍵設計決策

1. **Grafana 取代 realtime-service + frontend**：計畫原本要自寫 WebSocket + React，Grafana 的 Live + 5 秒刷新已等效，且 0 程式碼
2. **Stage 4 告警提前到 Stage 2**：Grafana Alerting 是 built-in，跟儀表板同時完成
3. **DNS 只設在 grafana container**：最小影響範圍，其他 5 個容器不動
4. **chatid 硬寫在 YAML**：Grafana provisioning 不支援純數字 env var 作為字串，做了文件說明

---

## 10. 如何從零重現

```bash
cd ~/synaiq/EMS

# 確認 .env 有 TELEGRAM_BOT_TOKEN
cat .env

# 啟動全部
docker compose up -d

# 等 ~30 秒
curl http://localhost:3000  # Grafana 登入畫面
# 登入：admin / admin（或 .env 裡的 GRAFANA_PASSWORD）

# 觸發告警測試
curl -X POST 'http://localhost:8001/config?power_base_kw=120'
# 等 30-90 秒 → Telegram 收到告警

# 復原正常功率
curl -X POST 'http://localhost:8001/config?power_base_kw=50&power_swing_kw=30'
```

---

## 11. 下一步（Stage 3 預告）

Stage 3「動得了」：

| 項目 | 做法 | 程式碼量 |
|------|------|---------|
| device-service CRUD | Python FastAPI（設備 metadata 管理） | 需自寫 |
| gateway 動態 reload | `POST /reload` → 重讀設備清單 | 需自寫 |
| 前端設備管理頁 | Grafana 還不夠，可能需要簡單 HTML 或 React | 待決策 |
