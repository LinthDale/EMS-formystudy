/**
 * 設計 token 契約測試（§6.4 design gate 第 1 項）：
 * tokens.css 存在、涵蓋 色彩/字體/間距/圓角/動效 五類、命名空間單一。
 */
import { describe, expect, it } from "vitest";
import { parseTokens, tokensCss } from "@/test/parse-tokens";

const tokens = parseTokens();

const REQUIRED_TOKENS = [
  // color — surfaces / text / accent
  "--ems-color-bg",
  "--ems-color-surface",
  "--ems-color-border",
  "--ems-color-text-primary",
  "--ems-color-text-secondary",
  "--ems-color-accent",
  // color — 狀態機（FR-503）
  "--ems-color-status-candidate",
  "--ems-color-status-confirmed",
  "--ems-color-status-active",
  "--ems-color-status-retired",
  "--ems-color-status-unknown",
  "--ems-color-status-stale",
  // color — 信心區帶（FR-510）與量測域（FR-520）
  "--ems-color-confidence-low",
  "--ems-color-confidence-medium",
  "--ems-color-confidence-high",
  "--ems-color-domain-electricity",
  "--ems-color-domain-factory",
  // color — 圖表
  "--ems-color-chart-1",
  "--ems-color-chart-6",
  "--ems-color-chart-grid",
  "--ems-color-chart-axis",
  // typography
  "--ems-font-sans",
  "--ems-font-mono",
  "--ems-text-base",
  // spacing
  "--ems-space-1",
  "--ems-space-8",
  // radius
  "--ems-radius-sm",
  "--ems-radius-lg",
  // motion
  "--ems-motion-duration-fast",
  "--ems-motion-duration-base",
  "--ems-motion-duration-slow",
  "--ems-motion-ease-standard",
] as const;

describe("styles/tokens.css — 單一視覺真相契約", () => {
  it.each(REQUIRED_TOKENS)("定義必要 token %s 且非空", (name) => {
    const value = tokens.get(name);
    expect(value, `token ${name} 缺漏`).toBeTruthy();
  });

  it("所有自訂屬性使用單一 --ems- 命名空間", () => {
    const all = tokensCss.match(/--[\w-]+(?=\s*:)/g) ?? [];
    const defined = all.filter((n) => !n.startsWith("--ems-"));
    expect(defined, `非 --ems- 命名空間 token: ${defined.join(", ")}`).toEqual([]);
  });

  it("token 不得重複定義（避免雙真相）", () => {
    const names: readonly string[] = tokensCss.match(/--ems-[\w-]+(?=\s*:)/g) ?? [];
    const dupes = names.filter((n, i) => names.indexOf(n) !== i);
    expect(dupes, `重複 token: ${dupes.join(", ")}`).toEqual([]);
  });

  it("motion duration 一律帶 ms 單位", () => {
    for (const key of [
      "--ems-motion-duration-fast",
      "--ems-motion-duration-base",
      "--ems-motion-duration-slow",
    ]) {
      expect(tokens.get(key), `${key} 應以 ms 結尾`).toMatch(/ms$/);
    }
  });
});
