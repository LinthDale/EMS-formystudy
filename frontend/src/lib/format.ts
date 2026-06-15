/**
 * 純函數格式化工具（immutable、無副作用；FR-531 zh-Hant 呈現）。
 */

/** 量測值格式化：null/undefined → em-dash；數字依 digits 取小數位。 */
export function formatMeasurementValue(
  value: number | null | undefined,
  digits = 1,
): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toFixed(digits);
}

/** ISO 時間 → zh-Hant 在地化呈現；無效輸入回 em-dash（不丟例外，邊界容錯）。 */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return new Intl.DateTimeFormat("zh-Hant", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(d);
}

/** 0–1 信心值 → 百分比字串（四捨五入到整數%）。 */
export function formatPercent01(value: number): string {
  return `${Math.round(value * 100)}%`;
}
