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
 */
import { RouterProvider, createBrowserRouter } from "react-router-dom";
import { EmsApiProvider } from "@/api/EmsApiContext";
import { createEmsApiClient } from "@/api/client";
import { createLiveFetcher } from "@/api/liveFetcher";
import { AuthProvider } from "@/auth/AuthContext";
import { appRoutes } from "@/app/router";

const router = createBrowserRouter(appRoutes);

// LIVE client（同源 BFF）：注入一次，全 app 共用。
const liveClient = createEmsApiClient(createLiveFetcher());

export function App() {
  return (
    <AuthProvider>
      <EmsApiProvider client={liveClient}>
        <RouterProvider router={router} />
      </EmsApiProvider>
    </AuthProvider>
  );
}
