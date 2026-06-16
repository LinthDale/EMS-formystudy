/**
 * 路由設定（Wave 1）— react-router v7。
 *
 * AppShell 為共用 layout（banner/nav/main）；子路由：
 *   /            → DeviceListPage（首頁＝設備清單，FR-500；無重導步驟）
 *   /devices     → DeviceListPage（FR-500；nav 的標準目標）
 *   /devices/:id → DeviceDetailPage（FR-501）
 *   /queue       → ConfirmationQueuePage（FR-510）
 *   /queue/:id   → ReviewPage（FR-511/512）
 *   /gallery     → GalleryPage（Design System 展示，保留）
 *
 * route 元素獨立匯出 `appRoutes`，供測試用 createMemoryRouter 注入起始路徑。
 */
import { type RouteObject } from "react-router-dom";
import { AppShell } from "./AppShell";
import { ROUTES } from "./routes";
import { DeviceListPage } from "@/pages/DeviceListPage";
import { DeviceDetailPage } from "@/pages/DeviceDetailPage";
import { ConfirmationQueuePage } from "@/pages/ConfirmationQueuePage";
import { ReviewPage } from "@/pages/ReviewPage";
import { GalleryPage } from "@/pages/GalleryPage";

export const appRoutes: RouteObject[] = [
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: <DeviceListPage /> },
      { path: ROUTES.devices, element: <DeviceListPage /> },
      { path: ROUTES.device, element: <DeviceDetailPage /> },
      { path: ROUTES.queue, element: <ConfirmationQueuePage /> },
      { path: ROUTES.review, element: <ReviewPage /> },
      { path: ROUTES.gallery, element: <GalleryPage /> },
    ],
  },
];
