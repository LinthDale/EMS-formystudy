/**
 * RequireAuth（PRD-0005 Phase-1 Wave 2）— 路由守衛。
 *
 * - status=checking：顯示驗證中（status landmark），不洩漏受保護內容、不導向
 *   （避免登入狀態尚未解析就閃一下登入頁）。
 * - status=unauthenticated：導向 /login，並把原目標塞進 location.state.from，
 *   登入成功後可導回。
 * - status=authenticated：渲染 children（通常為 <Outlet />）。
 *
 * 注意（§9.1）：守衛只是 UX；真正權限邊界在 BFF + 後端（每請求驗 session + role）。
 */
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Navigate, useLocation } from "react-router-dom";
import { ROUTES } from "@/app/routes";
import { useAuth } from "./AuthContext";

export interface RequireAuthProps {
  children: ReactNode;
}

export function RequireAuth({ children }: RequireAuthProps) {
  const { t } = useTranslation();
  const auth = useAuth();
  const location = useLocation();

  if (auth.status === "checking") {
    return (
      <div role="status" className="p-6 text-sm text-fg-muted">
        {t("auth.session.checking")}
      </div>
    );
  }

  if (auth.status === "unauthenticated") {
    return (
      <Navigate to={ROUTES.login} replace state={{ from: location }} />
    );
  }

  return <>{children}</>;
}
