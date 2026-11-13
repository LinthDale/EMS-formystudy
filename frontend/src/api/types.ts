/**
 * API 型別 — 一律由 `npm run gen:api`（openapi-typescript）從 repo 根
 * `api/openapi.yml` 生成 schema.ts 後在此 re-export 別名。
 * §13.2：「TS client 一律由 openapi.yml 生成，禁止手刻型別」——
 * 本檔只做別名與少量 view-model 擴充，不得手刻後端 DTO。
 */
import type { components } from "./schema";

export type DeviceCreate = components["schemas"]["DeviceCreate"];
export type DeviceUpdate = components["schemas"]["DeviceUpdate"];
export type DeviceOut = components["schemas"]["DeviceOut"];
export type SignalCreate = components["schemas"]["SignalCreate"];
export type SignalOut = components["schemas"]["SignalOut"];
export type OverrideRequest = components["schemas"]["OverrideRequest"];
export type CorrectionCreate = components["schemas"]["CorrectionCreate"];
export type CorrectionOut = components["schemas"]["CorrectionOut"];
export type DigestOut = components["schemas"]["DigestOut"];
export type Measurement = components["schemas"]["Measurement"];
export type FactoryMeasurement = components["schemas"]["FactoryMeasurement"];

/** `GET /devices` 排序欄位 allowlist（openapi 1.3.0；NULLS LAST，次序鍵 device_id） */
export type DeviceSortKey =
  | "device_id"
  | "device_type"
  | "status"
  | "ai_confidence"
  | "created_at"
  | "updated_at"
  | "last_seen_at";

export type SortOrder = "asc" | "desc";

/** `GET /devices` query（§8.1.1：bare array + limit/offset，無 total envelope） */
export interface ListDevicesQuery {
  readonly status?: string;
  readonly stale?: boolean;
  readonly type?: string;
  readonly limit?: number;
  readonly offset?: number;
  readonly sort?: DeviceSortKey;
  readonly order?: SortOrder;
}

/**
 * 量測查詢（per-device facade，經 BFF — §9.3）。
 * 路徑為 `GET /api/devices/{id}/measurements`（device_id 走 path，非 query）；
 * 此 query 僅承載 since / limit / order（與 BFF 約定的對外 facade 參數）。
 */
export interface MeasurementsQuery {
  /** ISO timestamp 下界（含）；轉成 `since=<iso>` query */
  readonly since?: string;
  readonly limit?: number;
  /** 排序方向（facade 產品語意 asc|desc，預設 desc；BFF 轉 PostgREST time.{asc,desc}；ADR-025） */
  readonly order?: "asc" | "desc";
}

/**
 * UI view-model：DeviceOut + stale 旗標。
 * 後端刻意不曝露 stale_marked_at（PRD-0003 白名單）；stale 由 BFF 以
 * `GET /devices?stale=true` 聚合標記（或 P1 mock）。前端不自行推算。
 */
export interface DeviceRow extends DeviceOut {
  readonly stale?: boolean;
}

/** 已知設備狀態（open-ended：未知值一律收斂為 'unknown' — §13.2） */
export const KNOWN_DEVICE_STATUSES = [
  "candidate",
  "confirmed",
  "active",
  "retired",
] as const;

export type DeviceStatusKnown = (typeof KNOWN_DEVICE_STATUSES)[number];
export type DeviceStatusView = DeviceStatusKnown | "unknown";

export function toDeviceStatusView(
  status: string | null | undefined,
): DeviceStatusView {
  return (KNOWN_DEVICE_STATUSES as readonly string[]).includes(status ?? "")
    ? (status as DeviceStatusKnown)
    : "unknown";
}

/** 量測域（FR-520） */
export type MeasurementDomain = "electricity" | "factory";
