/**
 * theme-preference 測試（PRD-0005 §6.4：使用者可切換配色主題 — 執行期切換 + 持久化）。
 * - applyThemePreference 設 documentElement 的 data-ems-theme（不動 tokens.css）。
 * - 預設主題 = 移除屬性（回落 tokens.css :root 真相）。
 * - 切換寫入 / 讀取 localStorage。
 * - 未知 / 損壞的 stored id 退回預設（input validation：never trust storage）。
 */
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  THEME_PREF_STORAGE_KEY,
  applyThemePreference,
  initThemePreference,
  loadThemePreference,
  resolveThemeId,
} from "@/lib/theme-preference";
import { DEFAULT_THEME_ID } from "@/styles/themes";

const ATTR = "data-ems-theme";

function clearAttr() {
  document.documentElement.removeAttribute(ATTR);
}

beforeEach(() => {
  localStorage.clear();
  clearAttr();
});
afterEach(() => {
  localStorage.clear();
  clearAttr();
});

describe("theme-preference — 執行期套用 data-ems-theme", () => {
  it("applyThemePreference 把選定主題寫到 documentElement 屬性", () => {
    applyThemePreference("amber");
    expect(document.documentElement.getAttribute(ATTR)).toBe("amber");
  });

  it("套用預設主題 = 移除屬性（回落 tokens.css :root 真相）", () => {
    applyThemePreference("teal");
    applyThemePreference(DEFAULT_THEME_ID);
    expect(document.documentElement.getAttribute(ATTR)).toBeNull();
  });

  it("未知 id 不套用屬性、不丟例外（input validation）", () => {
    applyThemePreference("不存在的主題");
    expect(document.documentElement.getAttribute(ATTR)).toBeNull();
  });
});

describe("theme-preference — 持久化（localStorage）", () => {
  it("applyThemePreference 持久化選擇", () => {
    applyThemePreference("light");
    expect(localStorage.getItem(THEME_PREF_STORAGE_KEY)).toBe("light");
  });

  it("loadThemePreference 讀回已存的合法 id", () => {
    localStorage.setItem(THEME_PREF_STORAGE_KEY, "teal");
    expect(loadThemePreference()).toBe("teal");
  });

  it("loadThemePreference 對未存 / 損壞值退回預設", () => {
    expect(loadThemePreference()).toBe(DEFAULT_THEME_ID);
    localStorage.setItem(THEME_PREF_STORAGE_KEY, "garbage-not-a-theme");
    expect(loadThemePreference()).toBe(DEFAULT_THEME_ID);
  });

  it("resolveThemeId 僅放行可選主題（拒絕未知 / null）", () => {
    expect(resolveThemeId("amber")).toBe("amber");
    expect(resolveThemeId("garbage")).toBe(DEFAULT_THEME_ID);
    expect(resolveThemeId(null)).toBe(DEFAULT_THEME_ID);
  });
});

describe("theme-preference — 啟動時還原", () => {
  it("initThemePreference 套用已持久化的選擇", () => {
    localStorage.setItem(THEME_PREF_STORAGE_KEY, "amber");
    initThemePreference();
    expect(document.documentElement.getAttribute(ATTR)).toBe("amber");
  });

  it("initThemePreference 無持久化時不留屬性（用 tokens.css 預設）", () => {
    initThemePreference();
    expect(document.documentElement.getAttribute(ATTR)).toBeNull();
  });
});
