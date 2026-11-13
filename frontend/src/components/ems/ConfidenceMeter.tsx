/**
 * ConfidenceMeter（FR-510）— ai_confidence 0–1 視覺化。
 * 區帶：low < 0.5 ≤ medium < 0.8 ≤ high（tokens.css confidence 色）；
 * null = 未分類；超界 clamp。a11y：role=meter + aria-value*（FR-532）。
 */
import { useTranslation } from "react-i18next";
import { formatPercent01 } from "@/lib/format";
import { cn } from "@/lib/cn";

export type ConfidenceBand = "low" | "medium" | "high";

/** 純函數：0–1 → 信心區帶（邊界：0.5 / 0.8 含上界） */
export function toConfidenceBand(value: number): ConfidenceBand {
  if (value >= 0.8) return "high";
  if (value >= 0.5) return "medium";
  return "low";
}

function clamp01(value: number): number {
  return Math.min(1, Math.max(0, value));
}

const BAND_TEXT: Record<ConfidenceBand, string> = {
  low: "text-confidence-low",
  medium: "text-confidence-medium",
  high: "text-confidence-high",
};

const BAND_BAR: Record<ConfidenceBand, string> = {
  low: "bg-confidence-low",
  medium: "bg-confidence-medium",
  high: "bg-confidence-high",
};

export interface ConfidenceMeterProps {
  /** ai_confidence（0–1）；null/undefined = 未分類 */
  value: number | null | undefined;
  className?: string;
}

export function ConfidenceMeter({ value, className }: ConfidenceMeterProps) {
  const { t } = useTranslation();

  if (value === null || value === undefined || Number.isNaN(value)) {
    return (
      <span className={cn("text-xs text-fg-muted", className)}>
        {t("confidence.unclassified")}
      </span>
    );
  }

  const clamped = clamp01(value);
  const band = toConfidenceBand(clamped);
  const percentText = formatPercent01(clamped);

  return (
    <span
      role="meter"
      aria-label={t("confidence.label")}
      aria-valuemin={0}
      aria-valuemax={1}
      aria-valuenow={clamped}
      aria-valuetext={percentText}
      data-band={band}
      className={cn("inline-flex items-center gap-2", className)}
    >
      <span
        aria-hidden="true"
        className="h-1 w-16 overflow-hidden rounded-full bg-surface-sunken"
      >
        <span
          className={cn(
            "block h-full rounded-full transition-[width] duration-[var(--ems-motion-duration-base)] ease-standard",
            BAND_BAR[band],
          )}
          style={{ width: `${clamped * 100}%` }}
        />
      </span>
      <span className={cn("font-mono text-xs tabular-nums", BAND_TEXT[band])}>
        {percentText}
      </span>
    </span>
  );
}
