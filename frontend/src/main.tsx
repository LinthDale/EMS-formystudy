import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@/styles/globals.css";
import "@/i18n";
import { App } from "@/App";
import { initFontPreference } from "@/lib/font-preference";
import { initThemePreference } from "@/lib/theme-preference";

// 啟動時還原使用者持久化的字體與主題偏好（§6.4）。主題在 render 前同步套用屬性，避免 FOUC。
initThemePreference();
initFontPreference();

const rootEl = document.getElementById("root");
if (!rootEl) {
  throw new Error("#root 不存在 — index.html 損毀");
}

createRoot(rootEl).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
