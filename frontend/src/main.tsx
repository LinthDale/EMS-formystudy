import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@/styles/globals.css";
import "@/i18n";
import { App } from "@/App";
import { initFontPreference } from "@/lib/font-preference";

// 啟動時還原使用者持久化的字體偏好（§6.4 可調整字體）。
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
