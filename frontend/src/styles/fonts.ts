/**
 * EMS 字體註冊表（PRD-0005 §6.4：「後臺設計可調整字體（可擴充）」）。
 *
 * 設計原則：
 *   - 單一資料源：要新增一款字體 = 在 EMS_FONTS 加「一筆」條目，無需改任何元件。
 *     （FontSwitcher / font-preference 皆由本表 driven）
 *   - 離線自託管：font-face 由 @fontsource/* npm 套件提供（見 styles/fonts.css），
 *     執行期不打任何外部 CDN（呼應專案 local/privacy ethos、§9.5 內容安全）。
 *   - CJK fallback 不可省：UI 為 zh-Hant，Inter 不覆蓋繁體中文字形，
 *     故每個可選的 sans 堆疊一律串接 Noto Sans TC 作 Hant 玻璃字 fallback。
 *   - tokens.css 仍是唯一視覺真相：本表的「預設 sans/mono」對應 tokens.css 內
 *     --ems-font-sans / --ems-font-mono 的首選 family；切換僅在執行期覆寫
 *     documentElement 的 inline custom property，不改 tokens.css。
 */

/** 字體在設計系統中的角色（對應 tokens.css 的三個字體 token）。 */
export type FontRole = "sans" | "mono" | "display";

export interface FontEntry {
  /** 穩定 id（localStorage / switcher value 用，全域唯一）。 */
  readonly id: string;
  /** 人類可讀標籤（UI 顯示；中英並列以利辨識）。 */
  readonly label: string;
  /** 角色：sans 為內文、display 為標題型、mono 為等寬。 */
  readonly role: FontRole;
  /**
   * 完整 font-family 堆疊（含 fallback）。sans / display 必含 CJK fallback。
   * 套用時直接 join(", ") 寫入 --ems-font-sans。
   */
  readonly stack: readonly string[];
  /** 自託管來源套件名（@fontsource/*）。新增字體時據此於 fonts.css 引入。 */
  readonly source: string;
  /** 是否為 CJK（繁中）覆蓋字體。 */
  readonly cjk?: boolean;
}

/** zh-Hant 玻璃字 fallback —— 每個可選 sans 堆疊都必須串接，Inter 不覆蓋繁中。 */
export const CJK_FALLBACK_FAMILY = '"Noto Sans TC"';

/** 系統字 fallback 尾段（沿用 tokens.css 既有疊代退化順序）。 */
const SYSTEM_SANS_TAIL: readonly string[] = [
  CJK_FALLBACK_FAMILY,
  '"PingFang TC"',
  '"Microsoft JhengHei"',
  "system-ui",
  "-apple-system",
  '"Segoe UI"',
  "sans-serif",
];

const SYSTEM_MONO_TAIL: readonly string[] = [
  "ui-monospace",
  "SFMono-Regular",
  "Menlo",
  "Consolas",
  "monospace",
];

/** sans/display 堆疊組裝器 —— 強制串接 CJK + 系統 fallback。 */
const sansStack = (head: string): readonly string[] => [head, ...SYSTEM_SANS_TAIL];

/**
 * 可選字體種子（OSS，自託管）。新增字體只需在此陣列加一筆。
 * 角色分布：sans（Inter 預設 + IBM/品牌）、display、mono、CJK。
 */
export const EMS_FONTS: readonly FontEntry[] = [
  {
    id: "inter",
    label: "Inter（預設）",
    role: "sans",
    stack: sansStack('"Inter"'),
    source: "@fontsource/inter",
  },
  {
    id: "space-grotesk",
    label: "Space Grotesk（幾何／品牌）",
    role: "display",
    stack: sansStack('"Space Grotesk"'),
    source: "@fontsource/space-grotesk",
  },
  {
    id: "noto-sans-tc",
    label: "Noto Sans TC（繁中）",
    role: "sans",
    stack: [CJK_FALLBACK_FAMILY, ...SYSTEM_SANS_TAIL.slice(1)],
    source: "@fontsource/noto-sans-tc",
    cjk: true,
  },
  {
    id: "jetbrains-mono",
    label: "JetBrains Mono（等寬）",
    role: "mono",
    stack: ['"JetBrains Mono"', ...SYSTEM_MONO_TAIL],
    source: "@fontsource/jetbrains-mono",
  },
] as const;

/** 預設 sans —— 對齊 tokens.css --ems-font-sans 首選 family（Inter）。 */
export const DEFAULT_SANS_FONT_ID = "inter";
/** 預設 mono —— 對齊 tokens.css --ems-font-mono 首選 family。 */
export const DEFAULT_MONO_FONT_ID = "jetbrains-mono";

const BY_ID: ReadonlyMap<string, FontEntry> = new Map(
  EMS_FONTS.map((f) => [f.id, f]),
);

/** 以 id 取得字體條目；未知 id 回 undefined（呼叫端自行 fallback）。 */
export function getFont(id: string): FontEntry | undefined {
  return BY_ID.get(id);
}

/**
 * 可作為「內文 sans」切換的字體（role = sans 或 display）。
 * mono 不列入 sans 切換（等寬不適合當內文）。switcher 與 preference 皆以此為準。
 */
export function sansFonts(): readonly FontEntry[] {
  return EMS_FONTS.filter((f) => f.role === "sans" || f.role === "display");
}
