/**
 * 測試輔助：以 createMemoryRouter（指定起始路徑）+ EmsApiProvider + AuthProvider
 * 渲染應用路由。
 *
 * 預設注入：mock EmsApiClient（資料） + 已驗證的 mock AuthApi（OPS role），
 * 使受 RequireAuth 守衛的頁面在測試中即為「已登入」狀態（保持 Wave 1 既有
 * 頁面測試全綠，無需逐一登入）。auth 流程本身的測試另以專屬 helper 注入
 * 不同 AuthApi（見 src/auth/__tests__）。
 */
import { render } from "@testing-library/react";
import { RouterProvider, createMemoryRouter } from "react-router-dom";
import { EmsApiProvider } from "@/api/EmsApiContext";
import type { EmsApiClient } from "@/api/client";
import { AuthProvider } from "@/auth/AuthContext";
import type { AuthApi } from "@/auth/authApi";
import type { AuthSession, Role } from "@/auth/types";
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

/** 已驗證的 mock AuthApi（預設 OPS）— 守衛立即放行，頁面測試無需登入。 */
export function authedMockApi(role: Role = "ops", username = "test-ops"): AuthApi {
  const session: AuthSession = { username, role };
  return {
    login: async () => session,
    logout: async () => {},
    currentSession: async () => session,
  };
}

export interface RenderRouteOptions {
  /** 起始路徑（例：/queue/mqtt-7f3a） */
  path: string;
  /** 注入的 EmsApiClient（省略時用 mock） */
  client?: EmsApiClient;
  /** 注入的 AuthApi（省略時用已驗證 OPS mock） */
  authApi?: AuthApi;
}

export function renderRoute({ path, client, authApi }: RenderRouteOptions) {
  ensureTokens();
  const router = createMemoryRouter(appRoutes, { initialEntries: [path] });
  return render(
    <AuthProvider authApi={authApi ?? authedMockApi()}>
      <EmsApiProvider client={client}>
        <RouterProvider router={router} />
      </EmsApiProvider>
    </AuthProvider>,
  );
}
