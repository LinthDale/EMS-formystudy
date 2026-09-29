/**
 * App — 組合根（Wave 1 + Wave 2 live wiring）。
 *
 * 正式執行（prod/dev runtime）一律走 LIVE 同源 BFF（§9.3）：
 * - EmsApiProvider 注入以 live fetcher 建的 client（credentials:include 帶 session
 *   cookie；金鑰只在 BFF 伺服器側，bundle 零金鑰 — §9.1/§9.2）。
 * - AuthProvider 預設 live authApi（POST /api/auth/login|logout、GET /api/auth/session）。
 *
 * 測試「不」經本檔：測試以 src/test/render-route.tsx 直接掛 appRoutes，
 * 並注入 mock EmsApiClient + 已驗證的 mock AuthApi（live-vs-mock 的單一切換點）。
 *
 * Dev-only mock 旁路（僅 import.meta.env.DEV；prod build 直接 tree-shake）：
 * 無後端時以 mock 資料 + 已驗證 OPS 逛全部頁審視設計 / 主題。
 * 啟用＝dev 下開 `?mock`（持久化 localStorage；`?mock=0` 關閉）。設計審視用，非執行路徑。
 */
import { RouterProvider, createBrowserRouter } from "react-router-dom";
import { EmsApiProvider } from "@/api/EmsApiContext";
import { createEmsApiClient, createMockEmsApiClient } from "@/api/client";
import { createLiveFetcher } from "@/api/liveFetcher";
import { AuthProvider } from "@/auth/AuthContext";
import type { AuthApi } from "@/auth/authApi";
import { appRoutes } from "@/app/router";

const router = createBrowserRouter(appRoutes);

// LIVE client（同源 BFF）：注入一次，全 app 共用。
const liveClient = createEmsApiClient(createLiveFetcher());

const DEV_MOCK_FLAG = "ems.devMock";

/** dev-only：是否啟用 mock 旁路（讀 ?mock 並持久化；prod 永遠 false）。 */
function devMockEnabled(): boolean {
  if (!import.meta.env.DEV) return false;
  try {
    const q = new URLSearchParams(window.location.search);
    if (q.has("mock")) {
      const on = q.get("mock") !== "0";
      localStorage.setItem(DEV_MOCK_FLAG, on ? "1" : "0");
      return on;
    }
    return localStorage.getItem(DEV_MOCK_FLAG) === "1";
  } catch {
    return false;
  }
}

/** dev-only 已驗證 mock AuthApi（OPS）— 守衛立即放行，無需後端。 */
const devMockAuthApi: AuthApi = {
  login: async () => ({ username: "dev-ops", role: "ops" }),
  logout: async () => {},
  currentSession: async () => ({ username: "dev-ops", role: "ops" }),
};

const useDevMock = devMockEnabled();
const appClient = useDevMock ? createMockEmsApiClient() : liveClient;
const appAuthApi: AuthApi | undefined = useDevMock ? devMockAuthApi : undefined;

export function App() {
  return (
    <AuthProvider authApi={appAuthApi}>
      <EmsApiProvider client={appClient}>
        <RouterProvider router={router} />
      </EmsApiProvider>
    </AuthProvider>
  );
}
