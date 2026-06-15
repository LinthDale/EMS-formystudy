import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@/styles/globals.css";
import "@/i18n";
import { App } from "@/App";

const rootEl = document.getElementById("root");
if (!rootEl) {
  throw new Error("#root 不存在 — index.html 損毀");
}

createRoot(rootEl).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
