/**
 * EMS ECharts theme（§6.4 design gate 第 2 項）
 * 一切顏色 / 字體皆由 tokens.css 推導 — 本檔不得出現 magic 色票。
 * 瀏覽器：defaultTokenReader 讀 documentElement 的 computed custom properties；
 * 測試：注入由 tokens.css 解析出的 reader（單一真相可驗證）。
 */
export type TokenReader = (name: string) => string;

export const EMS_CHARTS_THEME_NAME = "ems";

export const defaultTokenReader: TokenReader = (name) =>
  getComputedStyle(document.documentElement).getPropertyValue(name).trim();

function required(read: TokenReader, name: string): string {
  const value = read(name);
  if (!value) {
    throw new Error(
      `[charts/theme] 缺少 design token ${name} — tokens.css 未載入或 token 被移除`,
    );
  }
  return value;
}

export function buildEmsChartsTheme(read: TokenReader = defaultTokenReader) {
  const palette = [1, 2, 3, 4, 5, 6].map((i) =>
    required(read, `--ems-color-chart-${i}`),
  );
  const textPrimary = required(read, "--ems-color-text-primary");
  const textSecondary = required(read, "--ems-color-text-secondary");
  const axis = required(read, "--ems-color-chart-axis");
  const grid = required(read, "--ems-color-chart-grid");
  const surfaceRaised = required(read, "--ems-color-surface-raised");
  const border = required(read, "--ems-color-border");
  const fontSans = required(read, "--ems-font-sans");
  const fontMono = required(read, "--ems-font-mono");

  const axisCommon = {
    axisLine: { lineStyle: { color: grid } },
    axisTick: { lineStyle: { color: grid } },
    axisLabel: { color: axis, fontFamily: fontMono },
    splitLine: { lineStyle: { color: grid } },
  } as const;

  return {
    color: palette,
    backgroundColor: "transparent",
    textStyle: { color: textSecondary, fontFamily: fontSans },
    title: { textStyle: { color: textPrimary, fontFamily: fontSans } },
    legend: { textStyle: { color: textSecondary } },
    tooltip: {
      backgroundColor: surfaceRaised,
      borderColor: border,
      textStyle: { color: textPrimary, fontFamily: fontMono },
    },
    categoryAxis: axisCommon,
    valueAxis: axisCommon,
    timeAxis: axisCommon,
    logAxis: axisCommon,
    line: { symbol: "none", lineStyle: { width: 2 } },
  } as const;
}

/** 全 app 套用：main.tsx 啟動時以 echarts 實例呼叫一次。 */
export function registerEmsChartsTheme(
  echartsLike: { registerTheme: (name: string, theme: object) => void },
  read: TokenReader = defaultTokenReader,
): void {
  echartsLike.registerTheme(EMS_CHARTS_THEME_NAME, buildEmsChartsTheme(read));
}
