/**
 * DeviceTable（FR-500）— 設備清單：排序 + 「載入更多」分頁。
 *
 * §8.1.1：後端 `GET /devices` 回 bare array（limit/offset、無 total envelope）
 * → P1 採 infinite-scroll（載入更多）模式，不做總頁數分頁器。
 * 排序語義對齊後端 allowlist：NULLS LAST（不分方向）、次序鍵 device_id。
 * a11y（FR-532）：caption、columnheader aria-sort、排序鈕為真 button。
 */
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import type { DeviceRow, DeviceSortKey, SortOrder } from "@/api/types";
import { sortDevices } from "@/lib/device-sort";
import { formatDateTime } from "@/lib/format";
import { DeviceStatusPill } from "./DeviceStatusPill";
import { ConfidenceMeter } from "./ConfidenceMeter";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";

const DEFAULT_PAGE_SIZE = 25;

interface SortState {
  readonly key: DeviceSortKey;
  readonly order: SortOrder;
}

interface Column {
  readonly key: DeviceSortKey;
  readonly i18nKey: string;
  readonly numeric?: boolean;
}

const COLUMNS: readonly Column[] = [
  { key: "device_id", i18nKey: "deviceTable.headers.deviceId" },
  { key: "device_type", i18nKey: "deviceTable.headers.deviceType" },
  { key: "status", i18nKey: "deviceTable.headers.status" },
  { key: "ai_confidence", i18nKey: "deviceTable.headers.aiConfidence", numeric: true },
  { key: "last_seen_at", i18nKey: "deviceTable.headers.lastSeenAt" },
];

function nextSort(current: SortState | null, key: DeviceSortKey): SortState {
  if (current?.key === key) {
    return { key, order: current.order === "asc" ? "desc" : "asc" };
  }
  return { key, order: "asc" };
}

function ariaSort(sort: SortState | null, key: DeviceSortKey) {
  if (sort?.key !== key) return undefined;
  return sort.order === "asc" ? ("ascending" as const) : ("descending" as const);
}

export interface DeviceTableProps {
  devices: readonly DeviceRow[];
  /** 每批顯示筆數（§8.1.1 載入更多；預設 25） */
  pageSize?: number;
  className?: string;
}

export function DeviceTable({
  devices,
  pageSize = DEFAULT_PAGE_SIZE,
  className,
}: DeviceTableProps) {
  const { t } = useTranslation();
  const [sort, setSort] = useState<SortState | null>(null);
  const [shownCount, setShownCount] = useState(pageSize);

  const sorted = useMemo(
    () => (sort ? sortDevices(devices, sort.key, sort.order) : [...devices]),
    [devices, sort],
  );
  const shown = sorted.slice(0, shownCount);
  const hasMore = shownCount < sorted.length;

  if (devices.length === 0) {
    return (
      <div
        className={cn(
          "flex flex-col items-center gap-1 rounded-lg border border-dashed border-line p-8",
          className,
        )}
      >
        <span className="text-sm text-fg-secondary">{t("deviceTable.empty")}</span>
      </div>
    );
  }

  return (
    <div className={cn("flex flex-col gap-3", className)}>
      <div className="overflow-x-auto rounded-lg shadow-card">
        <table className="w-full border-collapse bg-surface text-sm">
          <caption className="sr-only">{t("deviceTable.caption")}</caption>
          <thead>
            <tr className="border-b border-line-strong bg-surface-raised">
              {COLUMNS.map((col) => (
                <th
                  key={col.key}
                  scope="col"
                  aria-sort={ariaSort(sort, col.key)}
                  className={cn(
                    "px-3 py-2 text-left text-xs font-semibold tracking-wide text-fg-secondary",
                    col.numeric && "text-right",
                  )}
                >
                  <button
                    type="button"
                    onClick={() => setSort((s) => nextSort(s, col.key))}
                    aria-label={t("deviceTable.sortBy", { column: t(col.i18nKey) })}
                    className={cn(
                      "inline-flex items-center gap-1 rounded-sm hover:text-fg",
                      sort?.key === col.key && "text-accent",
                    )}
                  >
                    {t(col.i18nKey)}
                    <span aria-hidden="true" className="font-mono text-[0.6rem]">
                      {sort?.key === col.key ? (sort.order === "asc" ? "▲" : "▼") : "↕"}
                    </span>
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {shown.map((d) => (
              <tr
                key={d.device_id}
                className="border-b border-line transition-colors duration-[var(--ems-motion-duration-fast)] hover:bg-surface-raised"
              >
                <td className="px-3 py-2 font-mono text-fg">{d.device_id}</td>
                <td className="px-3 py-2 text-fg-secondary">
                  {d.device_type ?? "—"}
                </td>
                <td className="px-3 py-2">
                  <DeviceStatusPill status={d.status} stale={d.stale} />
                </td>
                <td className="px-3 py-2 text-right">
                  <ConfidenceMeter value={d.ai_confidence} />
                </td>
                <td className="px-3 py-2 font-mono text-xs text-fg-secondary">
                  {formatDateTime(d.last_seen_at)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex items-center justify-between gap-3">
        <span className="text-xs text-fg-muted">
          {t("deviceTable.shown", { shown: shown.length, total: sorted.length })}
        </span>
        {hasMore ? (
          <Button size="sm" onClick={() => setShownCount((n) => n + pageSize)}>
            {t("common.loadMore")}
          </Button>
        ) : null}
      </div>
    </div>
  );
}
