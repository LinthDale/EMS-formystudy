/**
 * charts/theme.ts 測試（§6.4 design gate 第 2 項）：
 * ECharts theme 完全由 tokens.css 推導，無 ECharts 預設配色殘留。
 */
import { describe, expect, it, vi } from "vitest";
import {
  EMS_CHARTS_THEME_NAME,
  buildEmsChartsTheme,
  registerEmsChartsTheme,
} from "@/charts/theme";
import { parseTokens, tokenReaderFromCss } from "@/test/parse-tokens";

const read = tokenReaderFromCss();
const tokens = parseTokens();

describe("charts/theme — 由 tokens.css 推導", () => {
  it("調色盤 = tokens.css chart-1..6 的值（同序）", () => {
    const theme = buildEmsChartsTheme(read);
    const expected = [1, 2, 3, 4, 5, 6].map((i) =>
      tokens.get(`--ems-color-chart-${i}`),
    );
    expect(theme.color).toEqual(expected);
  });

  it("軸線 / 文字 / tooltip 顏色皆引用 token 值", () => {
    const theme = buildEmsChartsTheme(read);
    expect(theme.textStyle.color).toBe(tokens.get("--ems-color-text-secondary"));
    expect(theme.valueAxis.axisLabel.color).toBe(tokens.get("--ems-color-chart-axis"));
    expect(theme.valueAxis.splitLine.lineStyle.color).toBe(
      tokens.get("--ems-color-chart-grid"),
    );
    expect(theme.tooltip.backgroundColor).toBe(
      tokens.get("--ems-color-surface-raised"),
    );
  });

  it("不含 ECharts 預設配色（如 #5470c6）", () => {
    const json = JSON.stringify(buildEmsChartsTheme(read)).toLowerCase();
    expect(json).not.toContain("#5470c6");
    expect(json).not.toContain("#91cc75");
  });

  it("token 缺漏時 fail-fast 並指名缺哪個 token", () => {
    const emptyReader = () => "";
    expect(() => buildEmsChartsTheme(emptyReader)).toThrowError(/--ems-color-chart-1/);
  });

  it("registerEmsChartsTheme 以固定名稱 'ems' 註冊（全 app 套用）", () => {
    const fake = { registerTheme: vi.fn() };
    registerEmsChartsTheme(fake, read);
    expect(EMS_CHARTS_THEME_NAME).toBe("ems");
    expect(fake.registerTheme).toHaveBeenCalledWith(
      EMS_CHARTS_THEME_NAME,
      expect.objectContaining({ color: buildEmsChartsTheme(read).color }),
    );
  });
});
