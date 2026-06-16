/**
 * AsyncBoundary — 統一渲染 useAsync 的 loading / error / success 三態
 * （NFR「不白屏」/ AC-5：明確錯誤態 + 可重試）。
 */
import { useTranslation } from "react-i18next";
import type { ReactNode } from "react";
import type { AsyncState } from "@/lib/useAsync";
import { Button } from "@/components/ui/button";

export interface AsyncBoundaryProps<T> {
  state: AsyncState<T>;
  /** data 就緒（且非 null）時渲染 */
  children: (data: T) => ReactNode;
  loadingLabel?: string;
}

export function AsyncBoundary<T>({
  state,
  children,
  loadingLabel,
}: AsyncBoundaryProps<T>) {
  const { t } = useTranslation();

  if (state.status === "loading") {
    return (
      <div role="status" className="p-6 text-sm text-fg-muted">
        {loadingLabel ?? t("common.loading")}
      </div>
    );
  }

  if (state.status === "error" || state.data === null) {
    return (
      <div
        role="alert"
        className="flex flex-col items-start gap-3 rounded-lg border border-danger/40 bg-surface p-6"
      >
        <span className="text-sm text-danger">
          {t("common.error")}
          {state.error ? `：${state.error.message}` : ""}
        </span>
        <Button size="sm" variant="secondary" onClick={state.reload}>
          {t("common.retry")}
        </Button>
      </div>
    );
  }

  return <>{children(state.data)}</>;
}
