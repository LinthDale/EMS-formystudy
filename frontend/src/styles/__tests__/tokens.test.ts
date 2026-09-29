/**
 * 設計 token 契約測試（§6.4 design gate 第 1 項）：
 * tokens.css 存在、涵蓋 色彩/字體/間距/圓角/動效 五類、命名空間單一。
 */
import { describe, expect, it } from "vitest";
import { baseRootBlock, parseTokens, tokensCss } from "@/test/parse-tokens";
import { DEFAULT_THEME_ID, EMS_THEMES } from "@/styles/themes";

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

  it("基準 :root 區塊內 token 不得重複定義（避免雙真相；主題覆寫區塊另計）", () => {
    const names: readonly string[] =
      baseRootBlock(tokensCss).match(/--ems-[\w-]+(?=\s*:)/g) ?? [];
    const dupes = names.filter((n, i) => names.indexOf(n) !== i);
    expect(dupes, `基準區塊重複 token: ${dupes.join(", ")}`).toEqual([]);
  });

  it("主題覆寫區塊只覆寫基準既有 token（不引入新真相、區塊內不自我重複）", () => {
    const baseNames = new Set<string>(
      baseRootBlock(tokensCss).match(/--ems-[\w-]+(?=\s*:)/g) ?? [],
    );
    const themeRe = /:root\[data-ems-theme="[^"]+"\]\s*\{([\s\S]*?)\}/g;
    const problems: string[] = [];
    let m: RegExpExecArray | null;
    while ((m = themeRe.exec(tokensCss)) !== null) {
      const names: readonly string[] = m[1].match(/--ems-[\w-]+(?=\s*:)/g) ?? [];
      names
        .filter((n, i) => names.indexOf(n) !== i)
        .forEach((n) => problems.push(`區塊內重複:${n}`));
      names
        .filter((n) => !baseNames.has(n))
        .forEach((n) => problems.push(`引入新 token:${n}`));
    }
    expect(problems, `主題區塊問題: ${problems.join(", ")}`).toEqual([]);
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

describe("主題 registry ↔ tokens.css 區塊一致性（避免漂移）", () => {
  const REQUIRED_THEME_TOKENS = [
    "--ems-color-bg",
    "--ems-color-surface",
    "--ems-color-surface-raised",
    "--ems-color-border",
    "--ems-color-text-primary",
    "--ems-color-text-secondary",
    "--ems-color-text-muted",
    "--ems-color-accent",
    "--ems-color-status-candidate",
    "--ems-color-status-confirmed",
    "--ems-color-status-retired",
    "--ems-color-domain-electricity",
    "--ems-color-domain-factory",
    "--ems-color-chart-1",
    "--ems-color-chart-axis",
  ] as const;

  function themeBlock(id: string): string | null {
    const m = tokensCss.match(
      new RegExp(`:root\\[data-ems-theme="${id}"\\]\\s*\\{([\\s\\S]*?)\\}`),
    );
    return m ? m[1] : null;
  }

  it("每個非預設 registry 主題都有 CSS 區塊且覆寫必要 semantic tokens", () => {
    const problems: string[] = [];
    for (const t of EMS_THEMES) {
      if (t.id === DEFAULT_THEME_ID) continue; // 預設 = 基準 :root，無屬性區塊
      const block = themeBlock(t.id);
      if (!block) {
        problems.push(`registry "${t.id}" 無對應 CSS 區塊`);
        continue;
      }
      const names = new Set<string>(block.match(/--ems-[\w-]+(?=\s*:)/g) ?? []);
      for (const req of REQUIRED_THEME_TOKENS) {
        if (!names.has(req)) problems.push(`${t.id} 缺必要 token ${req}`);
      }
    }
    expect(problems, problems.join("; ")).toEqual([]);
  });

  it("每個 tokens.css 主題區塊都在 registry（反向，無孤兒）", () => {
    const ids = new Set<string>(EMS_THEMES.map((t) => t.id));
    const cssIds = [
      ...tokensCss.matchAll(/:root\[data-ems-theme="([^"]+)"\]/g),
    ].map((m) => m[1]);
    const orphans = cssIds.filter((id) => !ids.has(id));
    expect(orphans, `CSS 有但 registry 無: ${orphans.join(", ")}`).toEqual([]);
  });
});
