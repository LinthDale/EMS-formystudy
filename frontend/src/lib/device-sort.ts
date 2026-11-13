/**
 * 設備排序純函數 — 語義對齊後端 `GET /devices` 排序契約（openapi 1.3.0）：
 * allowlist 欄位、NULLS LAST（不分 asc/desc）、次序鍵 device_id asc。
 * immutable：回傳新陣列，不改變輸入。
 */
import type { DeviceRow, DeviceSortKey, SortOrder } from "@/api/types";

function valueOf(d: DeviceRow, key: DeviceSortKey): string | number | null {
  const v = d[key];
  return v === undefined || v === null ? null : v;
}

export function sortDevices(
  devices: readonly DeviceRow[],
  key: DeviceSortKey,
  order: SortOrder,
): DeviceRow[] {
  const dir = order === "desc" ? -1 : 1;
  return [...devices].sort((a, b) => {
    const av = valueOf(a, key);
    const bv = valueOf(b, key);
    if (av === null && bv === null) return a.device_id.localeCompare(b.device_id);
    if (av === null) return 1; // NULLS LAST，無關方向
    if (bv === null) return -1;
    let cmp: number;
    if (typeof av === "number" && typeof bv === "number") {
      cmp = av - bv;
    } else {
      cmp = String(av).localeCompare(String(bv));
    }
    if (cmp !== 0) return cmp * dir;
    return a.device_id.localeCompare(b.device_id); // 次序鍵
  });
}
