/**
 * theme-preference（PRD-0005 §6.4：使用者可切換配色主題 — 執行期切換 + 持久化）。
 *
 * 行為（鏡像 lib/font-preference.ts）：
 *   - 切換主題 = 設 documentElement 的 `data-ems-theme` 屬性
 *     （tokens.css 的 `:root[data-ems-theme="<id>"]` 覆寫對應色 token → 全站連動）。
 *     預設 graphite = 移除屬性，回落 tokens.css :root（仍是唯一視覺真相）。
 *   - 偏好持久化於 localStorage；啟動時還原。
 *   - 邊界輸入一律驗證（never trust storage）：未知 / 損壞 id → 退回預設。
 *
 * 不可變原則：本模組不改任何傳入物件，僅操作 DOM 與 storage 副作用。
 *
 * 注意（ECharts 整合）：charts/theme.ts 於註冊時讀 computed --ems-color-* token；
 * 切換主題後 CSS 變了但已註冊的 ECharts theme / 已畫圖表不會自動更新 —— 完整實作
 * 需在主題切換時重讀 token + 重註冊主題 + 圖表 re-render（見 ADR-028，規劃中）。
 */
import {
  DEFAULT_THEME_ID,
  getTheme,
  isSelectableTheme,
  type ThemeEntry,
} from "@/styles/themes";

/** localStorage key（單一常數，避免散落 magic string）。 */
export const THEME_PREF_STORAGE_KEY = "ems.theme";

/** documentElement 上受控的主題屬性。 */
const THEME_ATTR = "data-ems-theme";

/** 把任意輸入收斂成「合法可選主題 id」；不合法回預設。 */
export function resolveThemeId(id: string | null | undefined): string {
  return isSelectableTheme(id) ? id : DEFAULT_THEME_ID;
}

/** 從 localStorage 讀回偏好；缺值 / 損壞 → 預設。 */
export function loadThemePreference(): string {
  try {
    return resolveThemeId(localStorage.getItem(THEME_PREF_STORAGE_KEY));
  } catch {
    // storage 不可用（隱私模式 / SSR）→ 安全退回預設
    return DEFAULT_THEME_ID;
  }
}

function persist(id: string): void {
  try {
    localStorage.setItem(THEME_PREF_STORAGE_KEY, id);
  } catch {
    // storage 寫入失敗不致命：執行期套用仍生效
  }
}

function setThemeAttr(theme: ThemeEntry | undefined): void {
  const root = document.documentElement;
  if (!theme || theme.id === DEFAULT_THEME_ID) {
    // 預設 → 移除屬性，讓 tokens.css :root 為唯一真相
    root.removeAttribute(THEME_ATTR);
    return;
  }
  root.setAttribute(THEME_ATTR, theme.id);
}

/**
 * 套用並持久化主題偏好。
 * @returns 實際生效的主題 id（經驗證收斂）。
 */
export function applyThemePreference(id: string | null | undefined): string {
  const resolved = resolveThemeId(id);
  // 完全未知（非可選）時不持久化垃圾值，但仍回報退回的預設
  const known = isSelectableTheme(id);
  setThemeAttr(getTheme(resolved));
  if (known) persist(resolved);
  return resolved;
}

/** 啟動時還原已持久化偏好（main.tsx 啟動呼叫一次）。 */
export function initThemePreference(): string {
  return applyThemePreference(loadThemePreference());
}
