/**
 * MeasurementCard（FR-520）— 即時量測卡片，依域（electricity / factory）。
 * 域色 / 字體 / 間距一律引用 tokens.css；無值 → em-dash（不顯示 NaN）。
 */
import { useTranslation } from "react-i18next";
import type { MeasurementDomain } from "@/api/types";
import { formatDateTime, formatMeasurementValue } from "@/lib/format";
import { cn } from "@/lib/cn";

const DOMAIN_ACCENT: Record<MeasurementDomain, string> = {
  electricity: "text-domain-electricity",
  factory: "text-domain-factory",
};

const DOMAIN_EDGE: Record<MeasurementDomain, string> = {
  electricity: "border-l-domain-electricity",
  factory: "border-l-domain-factory",
};

export interface MeasurementCardProps {
  domain: MeasurementDomain;
  /** 量測名稱（例：即時功率） */
  label: string;
  value: number | null | undefined;
  unit: string;
  /** 小數位數（預設 1） */
  digits?: number;
  /** 最新量測時間（ISO；顯示「更新於 …」） */
  timestamp?: string | null;
  className?: string;
}

export function MeasurementCard({
  domain,
  label,
  value,
  unit,
  digits = 1,
  timestamp,
  className,
}: MeasurementCardProps) {
  const { t } = useTranslation();

  return (
    <div
      role="group"
      aria-label={label}
      data-domain={domain}
      className={cn(
        "flex flex-col gap-2 rounded-lg border-l-2 bg-surface p-4 shadow-card",
        DOMAIN_EDGE[domain],
        className,
      )}
    >
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-sm font-medium text-fg-secondary">{label}</span>
        <span
          className={cn(
            "text-xs font-medium tracking-wide uppercase",
            DOMAIN_ACCENT[domain],
          )}
        >
          {t(`measurement.domain.${domain}`)}
        </span>
      </div>
      <div className="flex items-baseline gap-1.5">
        <span className="font-mono text-2xl font-semibold tabular-nums text-fg">
          {formatMeasurementValue(value, digits)}
        </span>
        <span className="text-sm text-fg-muted">{unit}</span>
      </div>
      {timestamp ? (
        <span className="text-xs text-fg-muted">
          {t("measurement.updatedAt")} {formatDateTime(timestamp)}
        </span>
      ) : null}
    </div>
  );
}
