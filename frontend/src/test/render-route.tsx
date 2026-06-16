/**
 * 測試輔助：以 createMemoryRouter（指定起始路徑）+ EmsApiProvider 渲染應用路由。
 * 預設注入 mock client；測試可改注入自訂 client（驗 mutating 動作）。
 */
import { render } from "@testing-library/react";
import { RouterProvider, createMemoryRouter } from "react-router-dom";
import { EmsApiProvider } from "@/api/EmsApiContext";
import type { EmsApiClient } from "@/api/client";
import { appRoutes } from "@/app/router";
import { parseTokens } from "./parse-tokens";

let tokensApplied = false;

/** 把 tokens.css 值掛上 documentElement（jsdom 不載 CSS）— 只需一次 */
function ensureTokens() {
  if (tokensApplied) return;
  for (const [name, value] of parseTokens()) {
    document.documentElement.style.setProperty(name, value);
  }
  tokensApplied = true;
}

export interface RenderRouteOptions {
  /** 起始路徑（例：/queue/mqtt-7f3a） */
  path: string;
  /** 注入的 EmsApiClient（省略時用 mock） */
  client?: EmsApiClient;
}

export function renderRoute({ path, client }: RenderRouteOptions) {
  ensureTokens();
  const router = createMemoryRouter(appRoutes, { initialEntries: [path] });
  return render(
    <EmsApiProvider client={client}>
      <RouterProvider router={router} />
    </EmsApiProvider>,
  );
}
