/**
 * App shell（P1 SPA skeleton）— 目前單頁：Design System gallery。
 * P1 後續批次將以 router 掛 設備管理 / 信心佇列 頁（FR-500~513）。
 */
import { useTranslation } from "react-i18next";
import { GalleryPage } from "@/pages/GalleryPage";

export function App() {
  const { t } = useTranslation();

  return (
    <div className="min-h-screen bg-canvas text-fg">
      <header
        role="banner"
        className="sticky top-0 z-10 border-b border-line bg-surface/90 backdrop-blur"
      >
        <div className="mx-auto flex max-w-6xl items-baseline gap-3 px-4 py-3 sm:px-6">
          <span className="text-base font-bold tracking-wide text-fg">
            {t("common.appName")}
          </span>
          <span className="text-xs text-fg-muted">{t("common.appTagline")}</span>
        </div>
      </header>
      <main role="main" className="mx-auto max-w-6xl px-4 py-6 sm:px-6">
        <GalleryPage />
      </main>
    </div>
  );
}
