/**
 * DeviceStatusPill（FR-503）— 設備狀態徽章。
 * 五態：candidate / confirmed / active / retired / unknown（open-ended enum
 * 收斂，§13.2）+ stale 修飾（過時）。顏色一律引用 tokens.css 狀態色。
 */
import { useTranslation } from "react-i18next";
import { toDeviceStatusView, type DeviceStatusView } from "@/api/types";
import { cn } from "@/lib/cn";

const STATUS_CLASS: Record<DeviceStatusView, string> = {
  candidate: "text-status-candidate border-status-candidate",
  confirmed: "text-status-confirmed border-status-confirmed",
  active: "text-status-active border-status-active",
  retired: "text-status-retired border-status-retired",
  unknown: "text-status-unknown border-status-unknown",
};

export interface DeviceStatusPillProps {
  /** 後端 status 原值（open-ended；未知值收斂為 unknown） */
  status: string | null | undefined;
  /** stale 修飾（FR-503；資料源 §8.1 stale 旗標） */
  stale?: boolean;
  className?: string;
}

export function DeviceStatusPill({ status, stale, className }: DeviceStatusPillProps) {
  const { t } = useTranslation();
  const view = toDeviceStatusView(status);
  const label = t(`device.status.${view}`);
  const staleLabel = t("device.status.stale");
  const ariaLabel = stale ? `${label}（${staleLabel}）` : label;

  return (
    <span
      role="status"
      aria-label={ariaLabel}
      data-status={view}
      {...(stale ? { "data-stale": "true" } : {})}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border bg-surface-raised",
        "px-2.5 py-0.5 text-xs font-medium tracking-wide whitespace-nowrap",
        STATUS_CLASS[view],
        className,
      )}
    >
      <span
        aria-hidden="true"
        className="size-1.5 rounded-full bg-current"
        data-part="dot"
      />
      {label}
      {stale ? (
        <span className="border-l border-current/40 pl-1.5 text-status-stale">
          {staleLabel}
        </span>
      ) : null}
    </span>
  );
}
