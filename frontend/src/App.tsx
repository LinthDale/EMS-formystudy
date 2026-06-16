/**
 * App — 組合根（Wave 1）。
 * EmsApiProvider（預設 mock client，§9.3 live BFF wiring 屬 Wave 2）包住
 * RouterProvider（react-router v7）。AppShell + 頁面由 appRoutes 掛載。
 */
import { RouterProvider, createBrowserRouter } from "react-router-dom";
import { EmsApiProvider } from "@/api/EmsApiContext";
import { appRoutes } from "@/app/router";

const router = createBrowserRouter(appRoutes);

export function App() {
  return (
    <EmsApiProvider>
      <RouterProvider router={router} />
    </EmsApiProvider>
  );
}
