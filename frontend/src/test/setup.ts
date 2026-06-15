import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";
import "@/i18n"; // 初始化 i18next（zh-Hant），元件 useTranslation 才有預設 instance

afterEach(() => {
  cleanup();
});
