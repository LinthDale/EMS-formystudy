/**
 * 字體註冊表契約測試（PRD-0005 §6.4：可調整 + 可擴充 typography）。
 * - 註冊表形狀：每個條目齊備、id 唯一、有預設、可分 sans/mono/display 角色。
 * - 「可擴充」：新增字體 = 加一筆 registry entry（不改元件）→ 以結構驗證。
 * - 「CJK fallback 不可省」：每個 sans 堆疊都必須含 Noto Sans TC（zh-Hant 玻璃字）。
 * - tokens.css 仍為單一真相：sans/mono 預設 token 對應 registry 的 default。
 */
import { describe, expect, it } from "vitest";
import {
  EMS_FONTS,
  CJK_FALLBACK_FAMILY,
  DEFAULT_SANS_FONT_ID,
  DEFAULT_MONO_FONT_ID,
  getFont,
  sansFonts,
  type FontRole,
} from "@/styles/fonts";
import { parseTokens } from "@/test/parse-tokens";

const VALID_ROLES: readonly FontRole[] = ["sans", "mono", "display"];

describe("styles/fonts — 註冊表形狀（可擴充 typography）", () => {
  it("至少種入 4 種開源字體（Inter + display/sans + mono + CJK）", () => {
    expect(EMS_FONTS.length).toBeGreaterThanOrEqual(4);
  });

  it("每個條目欄位齊備且型別正確", () => {
    for (const f of EMS_FONTS) {
      expect(typeof f.id, `id 非字串：${JSON.stringify(f)}`).toBe("string");
      expect(f.id.length, `id 不得為空`).toBeGreaterThan(0);
      expect(f.label.length, `${f.id} label 不得為空`).toBeGreaterThan(0);
      expect(f.stack.length, `${f.id} stack 不得為空`).toBeGreaterThan(0);
      expect(VALID_ROLES, `${f.id} role 非法：${f.role}`).toContain(f.role);
      // 自託管來源（@fontsource）— 離線，無外部 CDN
      expect(f.source, `${f.id} source 應為 @fontsource/*`).toMatch(/^@fontsource\//);
    }
  });

  it("font id 全域唯一（避免切換歧義）", () => {
    const ids = EMS_FONTS.map((f) => f.id);
    const dupes = ids.filter((id, i) => ids.indexOf(id) !== i);
    expect(dupes, `重複 id：${dupes.join(", ")}`).toEqual([]);
  });

  it("getFont 以 id 取得條目，未知 id 回 undefined", () => {
    expect(getFont(DEFAULT_SANS_FONT_ID)?.id).toBe(DEFAULT_SANS_FONT_ID);
    expect(getFont("不存在的字體-id")).toBeUndefined();
  });

  it("種入 Inter（保留）並含可辨識的 display/sans 選項", () => {
    const ids = EMS_FONTS.map((f) => f.id);
    expect(ids).toContain("inter");
    // 一個非 Inter 的 sans/display 選項（品牌辨識度）
    expect(
      EMS_FONTS.some(
        (f) => (f.role === "sans" || f.role === "display") && f.id !== "inter",
      ),
      "缺少 Inter 以外的 sans/display 選項",
    ).toBe(true);
  });

  it("含一款 zh-Hant CJK 字體（Inter 不覆蓋繁中）", () => {
    const hasCjk = EMS_FONTS.some((f) => f.cjk === true);
    expect(hasCjk, "註冊表缺少標記為 cjk 的字體（Noto Sans TC）").toBe(true);
  });

  it("含一款 mono 字體", () => {
    expect(EMS_FONTS.some((f) => f.role === "mono")).toBe(true);
    expect(getFont(DEFAULT_MONO_FONT_ID)?.role).toBe("mono");
  });
});

describe("styles/fonts — CJK fallback（zh-Hant 不可省）", () => {
  it("每個可選 sans 堆疊都串接 Noto Sans TC 作 Hant fallback", () => {
    for (const f of sansFonts()) {
      expect(
        f.stack.includes(CJK_FALLBACK_FAMILY),
        `${f.id} 的 sans 堆疊未包含 CJK fallback「${CJK_FALLBACK_FAMILY}」`,
      ).toBe(true);
    }
  });

  it("CJK fallback family 字串明確為 Noto Sans TC", () => {
    expect(CJK_FALLBACK_FAMILY).toBe('"Noto Sans TC"');
  });
});

describe("styles/fonts — 與 tokens.css 單一真相對齊", () => {
  const tokens = parseTokens();

  it("tokens.css --ems-font-sans 以預設 sans 字體的首選 family 起頭", () => {
    const sansToken = tokens.get("--ems-font-sans") ?? "";
    const head = getFont(DEFAULT_SANS_FONT_ID)?.stack[0] ?? "";
    expect(head.length).toBeGreaterThan(0);
    expect(
      sansToken.startsWith(head),
      `tokens --ems-font-sans 應以「${head}」起頭，實得「${sansToken}」`,
    ).toBe(true);
  });

  it("tokens.css 三個字體 token 皆存在（sans / mono / display）", () => {
    expect(tokens.get("--ems-font-sans")).toBeTruthy();
    expect(tokens.get("--ems-font-mono")).toBeTruthy();
    expect(tokens.get("--ems-font-display")).toBeTruthy();
  });

  it("tokens.css sans 與 display token 皆含 CJK fallback", () => {
    expect(tokens.get("--ems-font-sans")).toContain("Noto Sans TC");
    expect(tokens.get("--ems-font-display")).toContain("Noto Sans TC");
  });
});
