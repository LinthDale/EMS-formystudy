/**
 * font-preference（PRD-0005 §6.4：可調整字體 — 執行期切換 + 持久化）。
 *
 * 行為：
 *   - 切換內文字體 = 覆寫 documentElement 的 inline --ems-font-sans
 *     （tokens.css 不動 → 仍是唯一視覺真相；切回預設時清除 override 回落 tokens.css）。
 *   - 偏好持久化於 localStorage；啟動時還原。
 *   - 邊界輸入一律驗證（never trust storage）：未知 / 損壞 / 非 sans 字體 → 退回預設。
 *
 * 不可變原則：本模組不改任何傳入物件，僅操作 DOM 與 storage 副作用。
 */
import {
  DEFAULT_SANS_FONT_ID,
  getFont,
  sansFonts,
  type FontEntry,
} from "@/styles/fonts";

/** localStorage key（單一常數，避免散落 magic string）。 */
export const FONT_PREF_STORAGE_KEY = "ems.font.sans";

/** 受控的 CSS custom property —— 與 tokens.css / globals.css 同名。 */
const SANS_VAR = "--ems-font-sans";

/** 可切換的 sans 字體 id 白名單（由註冊表 driven）。 */
function isSelectableSans(id: string | null | undefined): id is string {
  if (!id) return false;
  return sansFonts().some((f) => f.id === id);
}

/**
 * 把任意輸入收斂成「合法可選 sans 字體 id」；不合法回預設。
 * mono / display-only 非 sans / 未知 id 一律退回 DEFAULT_SANS_FONT_ID。
 */
export function resolveSansFontId(id: string | null | undefined): string {
  return isSelectableSans(id) ? id : DEFAULT_SANS_FONT_ID;
}

/** 從 localStorage 讀回偏好；缺值 / 損壞 → 預設。 */
export function loadFontPreference(): string {
  try {
    return resolveSansFontId(localStorage.getItem(FONT_PREF_STORAGE_KEY));
  } catch {
    // storage 不可用（隱私模式 / SSR）→ 安全退回預設
    return DEFAULT_SANS_FONT_ID;
  }
}

function persist(id: string): void {
  try {
    localStorage.setItem(FONT_PREF_STORAGE_KEY, id);
  } catch {
    // storage 寫入失敗不致命：執行期套用仍生效
  }
}

function setSansVar(font: FontEntry | undefined): void {
  const root = document.documentElement;
  if (!font || font.id === DEFAULT_SANS_FONT_ID) {
    // 預設 → 清除 inline override，讓 tokens.css 為唯一真相
    root.style.removeProperty(SANS_VAR);
    return;
  }
  root.style.setProperty(SANS_VAR, font.stack.join(", "));
}

/**
 * 套用並持久化字體偏好。
 * @returns 實際生效的字體 id（經驗證收斂）。
 */
export function applyFontPreference(id: string | null | undefined): string {
  const resolved = resolveSansFontId(id);
  // 完全未知（非可選）時不持久化垃圾值，但仍回報退回的預設
  const known = isSelectableSans(id);
  setSansVar(getFont(resolved));
  if (known) persist(resolved);
  return resolved;
}

/** 啟動時還原已持久化偏好（main.tsx 啟動呼叫一次）。 */
export function initFontPreference(): string {
  return applyFontPreference(loadFontPreference());
}
