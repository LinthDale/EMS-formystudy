/**
 * 字體 CSS 子集優化契約測試（code review：~180KB 全字集 → 子集化）。
 *
 * 這是「回歸護欄」：確保 styles/fonts.css 維持子集化策略——
 *   1. 全繁中覆蓋不可縮水：Noto Sans TC 的 `chinese-traditional` 子集必須保留
 *      （zh-Hant 是 UI 預設語系；§6.4 CJK fallback「不可省」）。
 *   2. 不得退回「全字集」入口（如 `noto-sans-tc/400.css`）——那會一次拉回上百個
 *      切片 + 用不到的語系，CSS 重新膨脹回 ~180KB。
 *   3. 用不到的語系不得被引入（cyrillic / greek / vietnamese / japanese / korean）——
 *      本 UI 只有英數 + 繁中。
 *   4. 仍離線：fonts.css 不得出現任何外部 URL（@fontsource 自託管）。
 *
 * 註：vitest `css:false` 會把 CSS import 變空字串，故以 node:fs 直接讀檔（同 parse-tokens 模式）。
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const fontsCss: string = readFileSync(
  resolve(process.cwd(), "src/styles/fonts.css"),
  "utf-8",
);

/** 只取 @import 行（忽略註解中提到的字串），避免註解誤判。 */
const importLines: readonly string[] = fontsCss
  .split("\n")
  .map((l) => l.trim())
  .filter((l) => l.startsWith("@import"));

describe("styles/fonts.css — 子集優化契約（全繁中覆蓋 + 砍冗語系）", () => {
  it("保留 Noto Sans TC 的 chinese-traditional 子集（zh-Hant 全覆蓋不可縮水）", () => {
    const tc = importLines.filter(
      (l) => l.includes("noto-sans-tc") && l.includes("chinese-traditional"),
    );
    expect(
      tc.length,
      "fonts.css 缺少 noto-sans-tc/chinese-traditional 子集 → 繁中將無法渲染",
    ).toBeGreaterThanOrEqual(1);
  });

  it("不得使用 Noto 的『全字集』入口（會拉回上百切片 + 冗語系，CSS 重新膨脹）", () => {
    const fullSet = importLines.filter((l) =>
      /noto-sans-tc\/\d{3}\.css/.test(l),
    );
    expect(
      fullSet,
      `偵測到全字集入口（應改用 per-subset）：${fullSet.join(", ")}`,
    ).toEqual([]);
  });

  it("不引入本 UI 用不到的語系子集（cyrillic / greek / vietnamese / japanese / korean）", () => {
    const unwanted = /cyrillic|greek|vietnamese|japanese|korean/i;
    const offenders = importLines.filter((l) => unwanted.test(l));
    expect(
      offenders,
      `引入了用不到的語系子集：${offenders.join(", ")}`,
    ).toEqual([]);
  });

  it("拉丁文 UI 字體（Inter / Space Grotesk / JetBrains Mono）皆採 latin 子集入口", () => {
    for (const family of ["inter", "space-grotesk", "jetbrains-mono"]) {
      const familyImports = importLines.filter((l) => l.includes(family));
      expect(
        familyImports.length,
        `${family} 應有 @import`,
      ).toBeGreaterThan(0);
      for (const line of familyImports) {
        expect(
          /\/latin(-ext)?-\d{3}\.css/.test(line),
          `${family} 入口未採 latin 子集：${line}`,
        ).toBe(true);
      }
    }
  });

  it("fonts.css 全離線：@import 皆指向 @fontsource，無外部 URL", () => {
    for (const line of importLines) {
      expect(line, `非 @fontsource 來源：${line}`).toMatch(
        /@fontsource\//,
      );
    }
    expect(
      /https?:\/\//.test(fontsCss),
      "fonts.css 不得含外部 http(s) URL（離線自託管）",
    ).toBe(false);
  });
});
