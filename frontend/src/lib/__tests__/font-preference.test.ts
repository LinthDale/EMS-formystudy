/**
 * font-preference 測試（PRD-0005 §6.4：可調整 typography — 執行期切換 + 持久化）。
 * - applyFontPreference 改寫 documentElement 的 --ems-font-sans（不動 tokens.css）。
 * - 切換寫入 / 讀取 localStorage。
 * - 未知 / 損壞的 stored id 退回預設（input validation：never trust storage）。
 * - 套用後 charts/theme.ts 仍能由同一份 reader 推導（token-driven 不脫鉤）。
 */
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  FONT_PREF_STORAGE_KEY,
  applyFontPreference,
  loadFontPreference,
  resolveSansFontId,
  initFontPreference,
} from "@/lib/font-preference";
import { DEFAULT_SANS_FONT_ID, getFont } from "@/styles/fonts";

function clearVar() {
  document.documentElement.style.removeProperty("--ems-font-sans");
}

beforeEach(() => {
  localStorage.clear();
  clearVar();
});
afterEach(() => {
  localStorage.clear();
  clearVar();
});

describe("font-preference — 執行期套用 --ems-font-sans", () => {
  it("applyFontPreference 把選定字體的堆疊寫到 documentElement", () => {
    const target = "space-grotesk";
    applyFontPreference(target);
    const applied = document.documentElement.style.getPropertyValue("--ems-font-sans");
    const stack = getFont(target)!.stack.join(", ");
    expect(applied).toBe(stack);
  });

  it("套用後堆疊仍含 Noto Sans TC（CJK fallback 不丟）", () => {
    applyFontPreference("space-grotesk");
    const applied = document.documentElement.style.getPropertyValue("--ems-font-sans");
    expect(applied).toContain("Noto Sans TC");
  });

  it("未知 id 不套用、不丟例外（input validation）", () => {
    applyFontPreference("不存在");
    expect(
      document.documentElement.style.getPropertyValue("--ems-font-sans"),
    ).toBe("");
  });

  it("套用預設字體 = 清除 inline override（回落 tokens.css 真相）", () => {
    applyFontPreference("space-grotesk");
    applyFontPreference(DEFAULT_SANS_FONT_ID);
    // 預設時不應殘留 inline override，讓 tokens.css 為唯一真相
    expect(
      document.documentElement.style.getPropertyValue("--ems-font-sans"),
    ).toBe("");
  });
});

describe("font-preference — 持久化（localStorage）", () => {
  it("applyFontPreference 持久化選擇", () => {
    applyFontPreference("space-grotesk");
    expect(localStorage.getItem(FONT_PREF_STORAGE_KEY)).toBe("space-grotesk");
  });

  it("loadFontPreference 讀回已存的合法 id", () => {
    localStorage.setItem(FONT_PREF_STORAGE_KEY, "space-grotesk");
    expect(loadFontPreference()).toBe("space-grotesk");
  });

  it("loadFontPreference 對未存 / 損壞值退回預設", () => {
    expect(loadFontPreference()).toBe(DEFAULT_SANS_FONT_ID);
    localStorage.setItem(FONT_PREF_STORAGE_KEY, "garbage-not-a-font");
    expect(loadFontPreference()).toBe(DEFAULT_SANS_FONT_ID);
  });

  it("resolveSansFontId 僅放行可選的 sans 字體（拒絕 mono/未知）", () => {
    expect(resolveSansFontId("space-grotesk")).toBe("space-grotesk");
    expect(resolveSansFontId("jetbrains-mono")).toBe(DEFAULT_SANS_FONT_ID);
    expect(resolveSansFontId(null)).toBe(DEFAULT_SANS_FONT_ID);
  });
});

describe("font-preference — 啟動時還原", () => {
  it("initFontPreference 套用已持久化的選擇", () => {
    localStorage.setItem(FONT_PREF_STORAGE_KEY, "space-grotesk");
    initFontPreference();
    expect(
      document.documentElement.style.getPropertyValue("--ems-font-sans"),
    ).toBe(getFont("space-grotesk")!.stack.join(", "));
  });

  it("initFontPreference 無持久化時不留 inline override（用 tokens.css 預設）", () => {
    initFontPreference();
    expect(
      document.documentElement.style.getPropertyValue("--ems-font-sans"),
    ).toBe("");
  });
});
