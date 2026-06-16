/**
 * useAsync — 最小非同步資料載入 hook（Wave 1；無 TanStack Query，P1 mock 即可）。
 *
 * 回傳 { status, data, error, reload }；組件據此渲染 loading / error / data 三態
 * （NFR「後端故障降級：明確錯誤態，不白屏」/ AC-5）。deps 變更時重新載入；
 * 以 cancelled flag 防止已卸載組件 setState（避免 race）。
 */
import { useCallback, useEffect, useState } from "react";

export type AsyncStatus = "loading" | "success" | "error";

export interface AsyncState<T> {
  readonly status: AsyncStatus;
  readonly data: T | null;
  readonly error: Error | null;
  readonly reload: () => void;
}

export function useAsync<T>(
  loader: () => Promise<T>,
  deps: readonly unknown[],
): AsyncState<T> {
  const [status, setStatus] = useState<AsyncStatus>("loading");
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [nonce, setNonce] = useState(0);

  const reload = useCallback(() => setNonce((n) => n + 1), []);

  useEffect(() => {
    let cancelled = false;
    setStatus("loading");
    setError(null);
    loader()
      .then((result) => {
        if (cancelled) return;
        setData(result);
        setStatus("success");
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err : new Error(String(err)));
        setStatus("error");
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce]);

  return { status, data, error, reload };
}
