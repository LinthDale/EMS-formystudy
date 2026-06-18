/**
 * Typed api-client stub（PRD-0005 §9.3 / §13.2）。
 *
 * - 一律指向「同源 BFF」`/api`：瀏覽器不直連 device-service / PostgREST，
 *   X-API-Key 僅存於 BFF 伺服器側（§9.1），bundle 內零金鑰。
 * - P1 不接線（live BFF wiring 屬 Phase 1 後續批次）：預設 fetcher 立即
 *   reject `EmsApiNotWiredError`，避免靜默失敗；UI 開發一律用
 *   `createMockEmsApiClient()`（固定 fixtures）。
 * - 型別全部來自 `gen:api`（openapi-typescript）生成的 schema.ts 別名
 *   （types.ts），禁止手刻 DTO（§13.2）。
 */
import type {
  CorrectionCreate,
  CorrectionOut,
  DeviceCreate,
  DeviceOut,
  DeviceRow,
  DeviceUpdate,
  DigestOut,
  ListDevicesQuery,
  Measurement,
  MeasurementsQuery,
  SignalOut,
} from "./types";
import {
  MOCK_DEVICE_MEASUREMENTS,
  MOCK_DEVICES,
  MOCK_REVIEW_DIGEST,
  MOCK_SIGNALS,
} from "./fixtures";
import { sortDevices } from "@/lib/device-sort";

/** 同源 BFF base path（§9.3：全部讀寫經 BFF，零瀏覽器 CORS 面） */
export const BFF_BASE_PATH = "/api";

/** P1 stub：尚未接線 BFF 時被呼叫的明確錯誤（不靜默） */
export class EmsApiNotWiredError extends Error {
  constructor(path: string) {
    super(
      `[api-client] BFF 尚未接線（P1 stub）：${path} — 請改用 createMockEmsApiClient()，live wiring 於 Phase 1 交付`,
    );
    this.name = "EmsApiNotWiredError";
  }
}

/** 最小 fetcher 介面（之後 Phase 1 以 fetch + session/CSRF 實作注入） */
export type Fetcher = (path: string, init?: RequestInit) => Promise<unknown>;

const notWiredFetcher: Fetcher = (path) =>
  Promise.reject(new EmsApiNotWiredError(path));

/** `GET /devices` query 組裝 — 鍵序固定，對齊 openapi 1.3.0 契約參數 */
export function buildListDevicesPath(query: ListDevicesQuery = {}): string {
  const params = new URLSearchParams();
  if (query.status !== undefined) params.set("status", query.status);
  if (query.stale !== undefined) params.set("stale", String(query.stale));
  if (query.type !== undefined) params.set("type", query.type);
  if (query.limit !== undefined) params.set("limit", String(query.limit));
  if (query.offset !== undefined) params.set("offset", String(query.offset));
  if (query.sort !== undefined) params.set("sort", query.sort);
  if (query.order !== undefined) params.set("order", query.order);
  const qs = params.toString();
  return `${BFF_BASE_PATH}/devices${qs ? `?${qs}` : ""}`;
}

/**
 * 量測 query 組裝 — per-device facade（與 BFF agent 約定的對外契約）：
 *   `GET /api/devices/{id}/measurements?since=&limit=&order=`
 * device_id 走 path（URL-encode）；since/limit/order 為對外 facade 參數，
 * 由 BFF 驗證後轉發至量測唯讀面（§9.3：經 BFF，瀏覽器零直連）。
 * 鍵序固定（since→limit→order），對齊契約測試。
 */
export function buildMeasurementsPath(
  deviceId: string,
  query: MeasurementsQuery = {},
): string {
  const params = new URLSearchParams();
  if (query.since !== undefined) params.set("since", query.since);
  if (query.limit !== undefined) params.set("limit", String(query.limit));
  params.set("order", query.order ?? "desc");  // facade product semantics: asc|desc (ADR-025), BFF maps to PostgREST time.{asc,desc}
  return `${devicePath(deviceId, "/measurements")}?${params.toString()}`;
}

/** device_id 進 path 前一律 URL-encode（防 path injection） */
function devicePath(deviceId: string, suffix = ""): string {
  return `${BFF_BASE_PATH}/devices/${encodeURIComponent(deviceId)}${suffix}`;
}

function postJson(body?: unknown): RequestInit {
  return {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
  };
}

/** EMS API client 介面（P1 完整 surface；mock 與 stub 共用） */
export interface EmsApiClient {
  listDevices(query?: ListDevicesQuery): Promise<DeviceRow[]>;
  getDevice(deviceId: string): Promise<DeviceOut>;
  createDevice(body: DeviceCreate): Promise<DeviceOut>;
  updateDevice(deviceId: string, body: DeviceUpdate): Promise<DeviceOut>;
  listSignals(deviceId: string): Promise<SignalOut[]>;
  getHumanReview(deviceId: string): Promise<DigestOut>;
  confirmDevice(deviceId: string): Promise<DeviceOut>;
  overrideDevice(deviceId: string, body: unknown): Promise<DeviceOut>;
  rejectDevice(deviceId: string): Promise<DeviceOut>;
  createCorrection(deviceId: string, body: CorrectionCreate): Promise<CorrectionOut>;
  /** per-device facade（§9.3）：`GET /api/devices/{id}/measurements?since=&limit=&order=` */
  listDeviceMeasurements(
    deviceId: string,
    query?: MeasurementsQuery,
  ): Promise<Measurement[]>;
}

/**
 * 真實 client（P1 stub）：所有方法經注入的 fetcher 打同源 BFF。
 * 未注入 fetcher（預設）→ 一律 EmsApiNotWiredError。
 */
export function createEmsApiClient(fetcher: Fetcher = notWiredFetcher): EmsApiClient {
  return {
    listDevices: (query) =>
      fetcher(buildListDevicesPath(query), undefined) as Promise<DeviceRow[]>,
    getDevice: (deviceId) =>
      fetcher(devicePath(deviceId), undefined) as Promise<DeviceOut>,
    createDevice: (body) =>
      fetcher(`${BFF_BASE_PATH}/devices`, postJson(body)) as Promise<DeviceOut>,
    updateDevice: (deviceId, body) =>
      fetcher(devicePath(deviceId), {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }) as Promise<DeviceOut>,
    listSignals: (deviceId) =>
      fetcher(devicePath(deviceId, "/signals"), undefined) as Promise<SignalOut[]>,
    getHumanReview: (deviceId) =>
      fetcher(devicePath(deviceId, "/human-review"), undefined) as Promise<DigestOut>,
    confirmDevice: (deviceId) =>
      fetcher(devicePath(deviceId, "/confirm"), postJson()) as Promise<DeviceOut>,
    overrideDevice: (deviceId, body) =>
      fetcher(devicePath(deviceId, "/override"), postJson(body)) as Promise<DeviceOut>,
    rejectDevice: (deviceId) =>
      fetcher(devicePath(deviceId, "/reject"), postJson()) as Promise<DeviceOut>,
    createCorrection: (deviceId, body) =>
      fetcher(devicePath(deviceId, "/corrections"), postJson(body)) as Promise<CorrectionOut>,
    listDeviceMeasurements: (deviceId, query) =>
      fetcher(buildMeasurementsPath(deviceId, query), undefined) as Promise<
        Measurement[]
      >,
  };
}

function clone<T>(value: T): T {
  return structuredClone(value);
}

function applyDeviceQuery(
  devices: readonly DeviceRow[],
  query: ListDevicesQuery,
): DeviceRow[] {
  let rows = devices.filter(
    (d) =>
      (query.status === undefined || d.status === query.status) &&
      (query.type === undefined || d.device_type === query.type) &&
      (query.stale === undefined || Boolean(d.stale) === query.stale),
  );
  if (query.sort !== undefined) {
    rows = sortDevices(rows, query.sort, query.order ?? "asc");
  }
  const offset = query.offset ?? 0;
  const end = query.limit !== undefined ? offset + query.limit : undefined;
  return rows.slice(offset, end);
}

/**
 * 純函數：以新狀態回傳設備的樂觀更新副本（不改變輸入；immutability）。
 * mock 不持久化於 DB（P1 mock 唯一資料源），僅回傳「後端會回的 DeviceOut」形狀，
 * 供 UI 樂觀更新（AC-3）。override 額外帶 classified_by=manual_override + device_type。
 */
export function applyDeviceTransition(
  device: DeviceOut,
  patch: Partial<DeviceOut>,
): DeviceOut {
  return { ...device, ...patch };
}

function findDeviceOrReject(deviceId: string): DeviceOut {
  const found = MOCK_DEVICES.find((d) => d.device_id === deviceId);
  if (!found) throw new Error(`mock: device ${deviceId} 不存在`);
  return clone(found);
}

/**
 * 純函數：以 facade `order` 對量測序列排序（不改變輸入；immutability）。
 * fixtures 以時間遞增儲存；asc 原序、desc 反序（對齊 ADR-025 facade 語義
 * → BFF 轉 PostgREST `time.asc|time.desc`）。
 */
export function orderMeasurements(
  rows: readonly Measurement[],
  order: "asc" | "desc" = "desc",
): Measurement[] {
  const sorted = [...rows].sort((a, b) => a.time.localeCompare(b.time));
  return order === "asc" ? sorted : sorted.reverse();
}

/**
 * 純函數：以 DeviceCreate 合成「後端建立後會回的」DeviceOut（樂觀）。
 * 新設備一律進 candidate 狀態（候選 → 待人工確認 / AI 分類），ai_confidence 未知。
 */
export function newDeviceFromCreate(body: DeviceCreate): DeviceOut {
  const now = new Date().toISOString();
  return {
    device_id: body.device_id,
    device_type: body.device_type ?? null,
    status: "candidate",
    protocol: body.protocol ?? null,
    vendor: body.vendor ?? null,
    model: body.model ?? null,
    location: body.location ?? null,
    gateway_id: body.gateway_id ?? null,
    classified_by: null,
    ai_confidence: null,
    created_at: now,
    updated_at: now,
    last_seen_at: null,
    confirmed_at: null,
  };
}

/**
 * Mock client（P1 唯一資料源）：固定 fixtures、零網路；
 * 語義對齊後端契約（filter / allowlist 排序 NULLS LAST / bare-array 分頁）。
 * 每次回傳深拷貝 — 呼叫端變更不汙染 fixtures（immutability）。
 * mutating 動作（create/update/confirm/override/reject/correction）以樂觀方式
 * 回傳「後端會回的」新副本（mock 不寫回 fixtures；持久化於 live BFF 接線後交付 — §8.2）。
 */
export function createMockEmsApiClient(): EmsApiClient {
  // 樂觀 correction id：同一 client 實例內單調遞增，避免多筆 correction 撞 React key。
  let nextCorrectionId = 1;
  const resolveDevice = (deviceId: string, patch: Partial<DeviceOut>) => {
    try {
      return Promise.resolve(applyDeviceTransition(findDeviceOrReject(deviceId), patch));
    } catch (err) {
      return Promise.reject(err as Error);
    }
  };
  return {
    listDevices: (query = {}) => Promise.resolve(applyDeviceQuery(MOCK_DEVICES, query).map(clone)),
    getDevice: (deviceId) => {
      try {
        return Promise.resolve(findDeviceOrReject(deviceId));
      } catch (err) {
        return Promise.reject(err as Error);
      }
    },
    createDevice: (body) => Promise.resolve(newDeviceFromCreate(body)),
    // 只投影 DeviceUpdate 的契約欄位（不用 `as Partial<DeviceOut>` 寬鬆 cast）—
    // 避免 mock 吞下 live BFF 會拒絕的欄位（status/classified_by…），保 mock↔live 契約對稱。
    // 未給的欄位不投影（PATCH 語意：undefined=不動；顯式 null=清空）。
    updateDevice: (deviceId, body) =>
      resolveDevice(deviceId, {
        ...(body.device_type !== undefined ? { device_type: body.device_type } : {}),
        ...(body.protocol !== undefined ? { protocol: body.protocol } : {}),
        ...(body.vendor !== undefined ? { vendor: body.vendor } : {}),
        ...(body.model !== undefined ? { model: body.model } : {}),
        ...(body.location !== undefined ? { location: body.location } : {}),
        ...(body.gateway_id !== undefined ? { gateway_id: body.gateway_id } : {}),
        updated_at: new Date().toISOString(),
      }),
    listSignals: (deviceId) =>
      Promise.resolve(MOCK_SIGNALS.filter((s) => s.device_id === deviceId).map(clone)),
    getHumanReview: (deviceId) =>
      Promise.resolve({ ...clone(MOCK_REVIEW_DIGEST), device_id: deviceId }),
    confirmDevice: (deviceId) =>
      resolveDevice(deviceId, { status: "confirmed" }),
    overrideDevice: (deviceId, body) => {
      const proposed = (body as { device_type?: string } | undefined)?.device_type;
      return resolveDevice(deviceId, {
        status: "confirmed",
        classified_by: "manual_override",
        ...(proposed !== undefined ? { device_type: proposed } : {}),
      });
    },
    rejectDevice: (deviceId) => resolveDevice(deviceId, { status: "retired" }),
    createCorrection: (deviceId, body) =>
      Promise.resolve({
        id: nextCorrectionId++,
        device_id: deviceId,
        verdict: body.verdict,
        corrected_device_type: body.corrected_device_type ?? null,
        corrected_signals: body.corrected_signals ?? null,
        human_explanation: body.human_explanation,
        created_at: new Date().toISOString(),
        created_by_key_id: "mock-key",
        salt_version: "v1",
        prompt_version_at_correction: null,
        applied_count: 0,
        is_active: true,
      } satisfies CorrectionOut),
    listDeviceMeasurements: (deviceId, query) =>
      Promise.resolve(
        orderMeasurements(MOCK_DEVICE_MEASUREMENTS[deviceId] ?? [], query?.order).map(clone),
      ),
  };
}
