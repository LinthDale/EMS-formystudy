/**
 * 路由路徑常數（單一真相；頁面 / 導覽 / 測試共用，禁止散落字串）。
 */
export const ROUTES = {
  devices: "/devices",
  device: "/devices/:deviceId",
  queue: "/queue",
  review: "/queue/:deviceId",
  gallery: "/gallery",
} as const;

/** 設備詳情路徑（FR-501） */
export function deviceDetailPath(deviceId: string): string {
  return `/devices/${encodeURIComponent(deviceId)}`;
}

/** 審閱路徑（FR-511/512） */
export function reviewPath(deviceId: string): string {
  return `/queue/${encodeURIComponent(deviceId)}`;
}
