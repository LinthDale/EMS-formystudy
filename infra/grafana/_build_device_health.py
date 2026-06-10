"""One-shot builder for the PRD-0004 FR-406~410 device-service health dashboard.
Run: python3 _build_device_health.py  (writes device-service-health.json next to it).
Kept in-repo as the source for the generated dashboard (hand-editing 400-line JSON is error-prone)."""
import json
import os

DS = {"type": "postgres", "uid": "timescaledb-ems"}


def target(sql, fmt="table"):
    return [{"datasource": DS, "format": fmt, "rawQuery": True, "rawSql": sql, "refId": "A"}]


def stat(pid, title, sql, gp, unit="none", steps=None, mode="thresholds"):
    return {
        "id": pid, "type": "stat", "title": title, "gridPos": gp, "datasource": DS,
        "options": {"colorMode": "background", "graphMode": "none", "justifyMode": "center",
                    "orientation": "auto", "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                    "textMode": "auto"},
        "fieldConfig": {"defaults": {"unit": unit, "color": {"mode": mode},
                                     "thresholds": {"mode": "absolute", "steps": steps or [
                                         {"color": "green", "value": None}]}}, "overrides": []},
        "targets": target(sql),
    }


def piechart(pid, title, sql, gp):
    return {
        "id": pid, "type": "piechart", "title": title, "gridPos": gp, "datasource": DS,
        "options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": True},
                    "pieType": "donut", "legend": {"displayMode": "table", "placement": "right",
                                                   "values": ["value", "percent"]}, "tooltip": {"mode": "single"}},
        "fieldConfig": {"defaults": {"unit": "none", "color": {"mode": "palette-classic"}}, "overrides": []},
        "targets": target(sql),
    }


def gauge(pid, title, sql, gp):
    return {
        "id": pid, "type": "gauge", "title": title, "gridPos": gp, "datasource": DS,
        "options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": True},
                    "orientation": "auto", "showThresholdLabels": False, "showThresholdMarkers": True},
        "fieldConfig": {"defaults": {"unit": "percent", "min": 0, "max": 100, "decimals": 1,
                                     "color": {"mode": "thresholds"},
                                     "thresholds": {"mode": "absolute", "steps": [
                                         {"color": "green", "value": None},
                                         {"color": "yellow", "value": 80},
                                         {"color": "red", "value": 100}]}}, "overrides": []},
        "targets": target(sql),
    }


def timeseries(pid, title, sql, gp, desc=""):
    return {
        "id": pid, "type": "timeseries", "title": title, "gridPos": gp, "datasource": DS,
        "description": desc,
        "options": {"legend": {"displayMode": "list", "placement": "bottom", "calcs": []},
                    "tooltip": {"mode": "multi"}},
        "fieldConfig": {"defaults": {"unit": "short", "custom": {"drawStyle": "bars", "fillOpacity": 60,
                                     "lineWidth": 1, "stacking": {"mode": "normal", "group": "A"}},
                                     "color": {"mode": "palette-classic"}}, "overrides": []},
        "targets": target(sql, "time_series"),
    }


def table(pid, title, sql, gp):
    return {
        "id": pid, "type": "table", "title": title, "gridPos": gp, "datasource": DS,
        "options": {"showHeader": True}, "fieldConfig": {"defaults": {}, "overrides": []},
        "targets": target(sql),
    }


# ---- panels (FR-406~410) ----
panels = [
    # FR-406 待人工確認佇列（candidate count）
    stat(1, "待人工確認佇列 (candidate)",
         "SELECT count(*) AS \"待確認\" FROM public.devices WHERE status = 'candidate'",
         {"x": 0, "y": 0, "w": 6, "h": 6}, unit="none",
         steps=[{"color": "green", "value": None}, {"color": "yellow", "value": 5}, {"color": "red", "value": 20}]),
    # FR-407 裝置狀態分布
    piechart(2, "裝置狀態分布 (FR-407)",
             "SELECT status, count(*) AS n FROM public.devices GROUP BY status ORDER BY status",
             {"x": 6, "y": 0, "w": 9, "h": 6}),
    # FR-409 預算用量 % gauge（per provider，當期）
    gauge(3, "LLM 預算用量 % (當期，per provider)",
          "SELECT provider, round(cost_usd / NULLIF(budget_usd,0) * 100, 1) AS pct "
          "FROM public.llm_budget_ledger WHERE period_start <= now() AND period_end > now() ORDER BY provider",
          {"x": 15, "y": 0, "w": 9, "h": 6}),
    # FR-409 成本明細表
    table(4, "LLM 成本明細 (當期 ledger)",
          "SELECT provider, cost_usd AS \"已花費(USD)\", budget_usd AS \"預算(USD)\", "
          "round(cost_usd / NULLIF(budget_usd,0) * 100, 1) AS \"用量%\" "
          "FROM public.llm_budget_ledger WHERE period_start <= now() AND period_end > now() ORDER BY provider",
          {"x": 0, "y": 6, "w": 12, "h": 8}),
    # FR-408 分類管線負面事件率（audit 有支撐的訊號；latency 無欄位，見 §14 Q6）
    timeseries(5, "分類管線負面事件 / 小時 (FR-408)",
               "SELECT date_trunc('hour', event_time) AS \"time\", "
               "count(*) FILTER (WHERE event_type = 'guardrail_block') AS \"guardrail BLOCK\", "
               "count(*) FILTER (WHERE event_type = 'rate_limit_exceeded') AS \"rate-limit 命中\" "
               "FROM public.device_audit_log "
               "WHERE event_time > now() - interval '7 days' "
               "AND COALESCE(device_id, '') NOT LIKE 'itest-%' "
               "GROUP BY 1 ORDER BY 1",
               {"x": 12, "y": 6, "w": 12, "h": 8},
               desc=("只計 guardrail_block 與 rate_limit_exceeded——這兩者是分類管線的「失敗 / 被擋」訊號。"
                     "其餘 audit 事件（deactivate / demote / freeze_override / ai_feedback_create）屬正常 ops 動作，"
                     "非錯誤，刻意不計入。排除 itest-% 測試裝置。latency 無量測欄位故不納（PRD-0004 §14 Q6）。")),
]

dashboard = {
    "uid": "ems-device-health",
    "title": "EMS Device-Service 健康度 (PRD-0004)",
    "description": ("PRD-0004 FR-406~410。由 infra/grafana/_build_device_health.py 生成——"
                    "請勿手改本 JSON，改 builder 後重跑。註：FR-409 的「月內累積斜率時序」未做——"
                    "llm_budget_ledger 每月每 provider 僅單列當期累計值、無逐時歷史，斜率需 cost 快照表"
                    "（同 FR-408 latency，列 PRD-0004 §14 Open Q）；本 dashboard 交付 gauge + 成本明細表。"),
    "tags": ["ems", "device-service", "prd-0004"],
    "timezone": "browser",
    "schemaVersion": 39,
    "version": 1,
    "refresh": "30s",
    "time": {"from": "now-7d", "to": "now"},
    "templating": {"list": []},
    "annotations": {"list": []},
    "panels": panels,
}

out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "provisioning", "dashboards", "device-service-health.json")
with open(out, "w", encoding="utf-8") as f:
    json.dump(dashboard, f, ensure_ascii=False, indent=2)
    f.write("\n")
print("wrote", out, "| panels:", len(panels))
