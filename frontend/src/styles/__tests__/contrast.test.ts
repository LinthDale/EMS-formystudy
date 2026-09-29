/**
 * 主題色彩對比 — 可執行 WCAG gate（§6.4 / FR-532）。
 * 每個主題的常用 text/background token 組合須過 WCAG 1.4.3 一般文字 4.5:1。
 * 解析 tokens.css 的基準 :root + 各 `:root[data-ems-theme]` 覆寫，算出該主題
 * 的有效 token，再計算對比度（純 hex；relative luminance）。
 */
import { describe, expect, it } from "vitest";
import { baseRootBlock, tokensCss } from "@/test/parse-tokens";
import { DEFAULT_THEME_ID, EMS_THEMES } from "@/styles/themes";

function parseBlock(block: string): Map<string, string> {
  const map = new Map<string, string>();
  const re = /(--ems-[\w-]+)\s*:\s*([^;]+);/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(block)) !== null) map.set(m[1], m[2].trim());
  return map;
}

/** 該主題的有效 token = 基準 :root 疊加該主題覆寫區塊。 */
function themeTokens(id: string): Map<string, string> {
  const merged = parseBlock(baseRootBlock(tokensCss));
  if (id === DEFAULT_THEME_ID) return merged;
  const m = tokensCss.match(
    new RegExp(`:root\\[data-ems-theme="${id}"\\]\\s*\\{([\\s\\S]*?)\\}`),
  );
  if (m) for (const [k, v] of parseBlock(m[1])) merged.set(k, v);
  return merged;
}

function luminance(hex: string): number {
  const n = parseInt(hex.slice(1), 16);
  const ch = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((c) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2];
}

function contrast(a: string, b: string): number {
  const la = luminance(a), lb = luminance(b);
  const hi = Math.max(la, lb), lo = Math.min(la, lb);
  return (hi + 0.05) / (lo + 0.05);
}

const TEXT_TOKENS = [
  "--ems-color-text-primary",
  "--ems-color-text-secondary",
  "--ems-color-text-muted",
];
const BG_TOKENS = [
  "--ems-color-bg",
  "--ems-color-surface",
  "--ems-color-surface-raised",
];
const MIN_NORMAL_TEXT = 4.5;

describe("主題色彩對比 — WCAG 1.4.3 一般文字 ≥ 4.5:1（FR-532）", () => {
  for (const theme of EMS_THEMES) {
    const tok = themeTokens(theme.id);
    for (const txt of TEXT_TOKENS) {
      for (const bg of BG_TOKENS) {
        it(`${theme.id}：${txt} on ${bg} ≥ 4.5:1`, () => {
          const fg = tok.get(txt);
          const back = tok.get(bg);
          expect(fg, `${theme.id} 缺 ${txt}`).toBeTruthy();
          expect(back, `${theme.id} 缺 ${bg}`).toBeTruthy();
          const ratio = contrast(fg as string, back as string);
          expect(
            ratio,
            `${theme.id} ${fg} on ${back} = ${ratio.toFixed(2)}:1（須 ≥ ${MIN_NORMAL_TEXT}）`,
          ).toBeGreaterThanOrEqual(MIN_NORMAL_TEXT);
        });
      }
    }
  }
});
