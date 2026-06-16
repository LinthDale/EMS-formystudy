/**
 * AppShell — 應用外殼 + 主導覽（Wave 1）。
 * banner / nav / main landmark（a11y FR-532）；視覺值一律 tokens.css。
 * 子路由由 <Outlet /> 掛載。
 */
import { useTranslation } from "react-i18next";
import { NavLink, Outlet } from "react-router-dom";
import { ROUTES } from "./routes";
import { cn } from "@/lib/cn";

interface NavItem {
  readonly to: string;
  readonly i18nKey: string;
}

const NAV_ITEMS: readonly NavItem[] = [
  { to: ROUTES.devices, i18nKey: "nav.devices" },
  { to: ROUTES.queue, i18nKey: "nav.queue" },
  { to: ROUTES.gallery, i18nKey: "nav.gallery" },
];

export function AppShell() {
  const { t } = useTranslation();

  return (
    <div className="min-h-screen bg-canvas text-fg">
      <header
        role="banner"
        className="sticky top-0 z-10 border-b border-line bg-surface/90 backdrop-blur"
      >
        <div className="mx-auto flex max-w-6xl flex-col gap-2 px-4 py-3 sm:px-6">
          <div className="flex items-baseline gap-3">
            <span className="text-base font-bold tracking-wide text-fg">
              {t("common.appName")}
            </span>
            <span className="text-xs text-fg-muted">{t("common.appTagline")}</span>
          </div>
          <nav aria-label={t("nav.primary")} className="flex flex-wrap gap-1">
            {NAV_ITEMS.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  cn(
                    "rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
                    "duration-[var(--ems-motion-duration-fast)] ease-standard",
                    isActive
                      ? "bg-surface-raised text-accent"
                      : "text-fg-secondary hover:text-fg hover:bg-surface-raised",
                  )
                }
              >
                {t(item.i18nKey)}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>
      <main role="main" className="mx-auto max-w-6xl px-4 py-6 sm:px-6">
        <Outlet />
      </main>
    </div>
  );
}
