/**
 * EMS 主題註冊表（PRD-0005 §6.4：使用者可切換配色主題）。
 *
 * 設計原則（鏡像 styles/fonts.ts 的單一資料源模式）：
 *   - 單一資料源：要新增一個主題 = 在 EMS_THEMES 加「一筆」+ 在 tokens.css 加
 *     一段 `:root[data-ems-theme="<id>"]` 覆寫區塊；FontSwitcher 對應的
 *     ThemeSwitcher / theme-preference 皆由本表 driven，零元件改動。
 *   - tokens.css 仍是唯一視覺真相：本表只列 id/label，實際色值住 tokens.css；
 *     切換僅在 documentElement 設 `data-ems-theme` 屬性（預設 graphite = 不帶屬性、
 *     回落 tokens.css :root）。
 *   - 動畫庫 / motion 語言由 GSAP 統一提供（見 ADR-027，規劃中），與主題正交。
 */

export interface ThemeEntry {
  /** 穩定 id（localStorage / switcher value / data-ems-theme 屬性值，全域唯一）。 */
  readonly id: string;
  /** i18n 標籤 key（文字集中於 i18n/zh-Hant.ts，元件不硬編中文 — FR-531）。 */
  readonly labelKey: string;
  /** 是否為亮色主題（影響對比/陰影語意；a11y 對比須過 WCAG，FR-532）。 */
  readonly isLight?: boolean;
}

/** 預設主題 —— 對齊 tokens.css :root 基準色（不帶 data-ems-theme 屬性）。 */
export const DEFAULT_THEME_ID = "graphite";

/**
 * 內建主題種子。新增主題只需在此加一筆 + tokens.css 對應覆寫區塊 + i18n labelKey。
 */
export const EMS_THEMES: readonly ThemeEntry[] = [
  { id: "graphite", labelKey: "theme.names.graphite" },
  { id: "amber", labelKey: "theme.names.amber" },
  { id: "teal", labelKey: "theme.names.teal" },
  { id: "light", labelKey: "theme.names.light", isLight: true },
] as const;

const BY_ID: ReadonlyMap<string, ThemeEntry> = new Map(
  EMS_THEMES.map((t) => [t.id, t]),
);

/** 以 id 取得主題；未知 id 回 undefined（呼叫端自行 fallback）。 */
export function getTheme(id: string): ThemeEntry | undefined {
  return BY_ID.get(id);
}

/** id 是否為可選主題（白名單，由註冊表 driven）。 */
export function isSelectableTheme(id: string | null | undefined): id is string {
  if (!id) return false;
  return EMS_THEMES.some((t) => t.id === id);
}
