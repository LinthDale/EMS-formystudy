/**
 * SignalSparkline（FR-501/520）— signal 迷你趨勢（純 SVG，零圖表庫負擔）。
 * 線色一律引用 design token（var(--ems-…)），無硬編色票。
 */
import { useTranslation } from "react-i18next";
import type { MeasurementDomain } from "@/api/types";
import { cn } from "@/lib/cn";

/**
 * 純函數：數值序列 → SVG polyline points 字串。
 * - x：等距分布於 [padding, width-padding]
 * - y：線性映射（最大值在頂、最小值在底）；常數序列 → 水平中線（不除以零）
 * - 不改變輸入陣列（immutability）
 */
export function buildSparklinePoints(
  values: readonly number[],
  width: number,
  height: number,
  padding: number,
): string {
  const innerW = width - padding * 2;
  const innerH = height - padding * 2;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min;
  const denom = values.length > 1 ? values.length - 1 : 1;

  return values
    .map((v, i) => {
      const x = padding + (i / denom) * innerW;
      const norm = range === 0 ? 0.5 : (v - min) / range;
      const y = padding + (1 - norm) * innerH;
      return `${x},${y}`;
    })
    .join(" ");
}

export interface SignalSparklineProps {
  /** signal 名稱（aria-label：「{name} 趨勢」） */
  name: string;
  values: readonly number[];
  /** 量測域 → 線色 token；未指定用品牌 accent */
  domain?: MeasurementDomain;
  width?: number;
  height?: number;
  className?: string;
}

export function SignalSparkline({
  name,
  values,
  domain,
  width = 120,
  height = 32,
  className,
}: SignalSparklineProps) {
  const { t } = useTranslation();

  if (values.length < 2) {
    return (
      <span className={cn("text-xs text-fg-muted", className)}>
        {t("signal.insufficientData")}
      </span>
    );
  }

  const stroke = domain
    ? `var(--ems-color-domain-${domain})`
    : "var(--ems-color-accent)";

  return (
    <svg
      role="img"
      aria-label={t("signal.sparklineLabel", { name })}
      viewBox={`0 0 ${width} ${height}`}
      width={width}
      height={height}
      className={cn("overflow-visible", className)}
    >
      <polyline
        points={buildSparklinePoints(values, width, height, 2)}
        fill="none"
        stroke={stroke}
        strokeWidth="1.5"
        strokeLinejoin="round"
        strokeLinecap="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}
