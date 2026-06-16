/**
 * Mock fixtures（P1：所有資料存取尚未接 BFF，§9.3 由另一批次交付）。
 * 固定 seed 資料、零隨機 — 測試與 gallery 截圖可重現（Guideline §7.3）。
 */
import type {
  DeviceRow,
  DigestOut,
  Measurement,
  FactoryMeasurement,
  SignalOut,
} from "./types";

export const MOCK_DEVICES: readonly DeviceRow[] = [
  {
    device_id: "sim-001",
    device_type: "electricity_meter",
    status: "active",
    protocol: "modbus_tcp",
    vendor: "SynaIQ",
    model: "SIM-3P",
    location: "B1 配電室",
    gateway_id: "ems-gateway",
    classified_by: "migration_backfill",
    ai_confidence: null,
    created_at: "2026-04-23T08:00:00Z",
    updated_at: "2026-06-10T01:00:00Z",
    last_seen_at: "2026-06-11T02:59:30Z",
    confirmed_at: "2026-04-23T08:00:00Z",
  },
  {
    device_id: "plc-001",
    device_type: "plc",
    status: "confirmed",
    protocol: "modbus_tcp",
    vendor: "KC",
    model: "KC-PLC-9",
    location: "KC 廠 A 線",
    gateway_id: "kc-gateway",
    classified_by: "human",
    ai_confidence: 0.93,
    created_at: "2026-04-27T09:00:00Z",
    updated_at: "2026-06-09T11:20:00Z",
    last_seen_at: "2026-06-11T02:58:00Z",
    confirmed_at: "2026-04-28T03:10:00Z",
  },
  {
    device_id: "mqtt-7f3a",
    device_type: "temperature_sensor",
    status: "candidate",
    protocol: "mqtt",
    vendor: null,
    model: null,
    location: null,
    gateway_id: "kc-ingest",
    classified_by: "ai",
    ai_confidence: 0.42,
    created_at: "2026-06-10T22:05:00Z",
    updated_at: "2026-06-10T22:05:00Z",
    last_seen_at: "2026-06-11T02:50:00Z",
    confirmed_at: null,
  },
  {
    device_id: "mqtt-9b21",
    device_type: "humidity_sensor",
    status: "candidate",
    protocol: "mqtt",
    vendor: null,
    model: null,
    location: null,
    gateway_id: "kc-ingest",
    classified_by: "ai",
    ai_confidence: 0.66,
    created_at: "2026-06-10T23:40:00Z",
    updated_at: "2026-06-10T23:40:00Z",
    last_seen_at: "2026-06-11T01:12:00Z",
    confirmed_at: null,
  },
  {
    device_id: "legacy-pm-02",
    device_type: "electricity_meter",
    status: "retired",
    protocol: "modbus_rtu",
    vendor: "Acme",
    model: "PM-2",
    location: "舊棟 2F",
    gateway_id: "ems-gateway",
    classified_by: "human",
    ai_confidence: 0.88,
    created_at: "2026-04-23T08:00:00Z",
    updated_at: "2026-05-30T07:00:00Z",
    last_seen_at: "2026-05-29T16:00:00Z",
    confirmed_at: "2026-04-24T02:00:00Z",
    stale: true,
  },
  {
    device_id: "edge-x1",
    device_type: null,
    status: "quarantined", // 模擬後端未來新 enum 值 → UI 須收斂為 unknown（§13.2）
    protocol: "mqtt",
    vendor: null,
    model: null,
    location: null,
    gateway_id: "kc-ingest",
    classified_by: "ai",
    ai_confidence: 0.18,
    created_at: "2026-06-11T00:30:00Z",
    updated_at: "2026-06-11T00:30:00Z",
    last_seen_at: null,
    confirmed_at: null,
  },
] as const;

export const MOCK_SIGNALS: readonly SignalOut[] = [
  { id: 1, device_id: "sim-001", signal_name: "voltage", unit: "V", datatype: "float", direction: "read", status: "active" },
  { id: 2, device_id: "sim-001", signal_name: "current", unit: "A", datatype: "float", direction: "read", status: "active" },
  { id: 3, device_id: "sim-001", signal_name: "power_kw", unit: "kW", datatype: "float", direction: "read", status: "active" },
  { id: 4, device_id: "plc-001", signal_name: "motor_speed", unit: "RPM", datatype: "float", direction: "read", status: "active" },
] as const;

/** digest 為 LLM 產出 + 寫入端可能被 MQTT payload 注入 → 一律純文字渲染（§9.5） */
export const MOCK_REVIEW_DIGEST: DigestOut = {
  device_id: "mqtt-7f3a",
  summary_source: "llm",
  generated_at: "2026-06-10T22:06:11Z",
  provider: "anthropic",
  model: "claude-sonnet-4-5",
  prompt_version: "v7",
  digest: {
    proposed_type: "temperature_sensor",
    confidence: 0.42,
    rationale:
      "Topic 階層含 temp 字樣、payload 數值範圍 18.2–31.6 與室溫一致；但取樣間隔不規則、缺 unit 欄位，信心偏低。",
    proposed_signals: ["temperature", "battery_pct"],
    warnings: ["unit 欄位缺漏", "取樣間隔抖動 > 20%"],
  },
};

/** 近 24 點功率（kW）— 確定性合成日線形（白天高、夜間低） */
export const MOCK_POWER_SERIES_KW: readonly number[] = [
  21.4, 20.8, 20.1, 19.7, 19.9, 22.3, 28.6, 37.2, 45.8, 52.1, 55.4, 57.9,
  58.7, 56.2, 54.8, 53.1, 49.6, 44.0, 38.5, 33.2, 29.7, 26.4, 24.1, 22.6,
] as const;

export const MOCK_ELECTRICITY_LATEST: Measurement = {
  time: "2026-06-11T02:59:30Z",
  device_id: "sim-001",
  voltage: 381.2,
  current: 105.3,
  power_kw: 58.7,
  energy_kwh: 1234.56,
};

export const MOCK_FACTORY_LATEST: FactoryMeasurement = {
  time: "2026-06-11T02:58:00Z",
  device_id: "plc-001",
  device_type: "plc",
  temperature: 25.3,
  humidity: 55.2,
  motor_speed: 1500,
  pump_on: true,
  valve_open: false,
  pressure: 1013,
};

/**
 * Per-device 量測樣本（per-device facade `GET /api/devices/{id}/measurements`）。
 * Wave 1 不渲染量測曲線（FR-520/521 屬 Wave 2），但 mock 先備齊以對齊
 * facade 契約；確定性 seed、零隨機（可重現）。鍵為 device_id。
 */
export const MOCK_DEVICE_MEASUREMENTS: Readonly<Record<string, readonly Measurement[]>> = {
  "sim-001": [
    {
      time: "2026-06-11T02:59:30Z",
      device_id: "sim-001",
      voltage: 381.2,
      current: 105.3,
      power_kw: 58.7,
      energy_kwh: 1234.56,
    },
    {
      time: "2026-06-11T02:58:30Z",
      device_id: "sim-001",
      voltage: 380.4,
      current: 104.1,
      power_kw: 57.9,
      energy_kwh: 1233.58,
    },
  ],
} as const;
