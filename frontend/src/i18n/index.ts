/**
 * i18n scaffold（FR-531）— i18next + react-i18next，預設 zh-Hant。
 * 之後若加語系（§14 Q8：中英雙語待定），於 resources 增加即可。
 */
import i18next from "i18next";
import { initReactI18next } from "react-i18next";
import { zhHant } from "./zh-Hant";

export const DEFAULT_LOCALE = "zh-Hant";

void i18next.use(initReactI18next).init({
  lng: DEFAULT_LOCALE,
  fallbackLng: DEFAULT_LOCALE,
  resources: {
    "zh-Hant": { translation: zhHant },
  },
  interpolation: { escapeValue: false }, // React 已 auto-escape（§9.5）
  returnNull: false,
});

export default i18next;
