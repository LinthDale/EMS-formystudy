/**
 * EmsApiClient React context（Wave 1）。
 *
 * 頁面一律透過 `useEmsApi()` 取得 client；預設注入 `createMockEmsApiClient()`
 * （P1 唯一資料源，§9.3 live BFF wiring 屬 Wave 2）。測試與 Wave 2 可改注入
 * 不同 client（mock vi.fn / live fetcher client）而不改頁面。
 */
import { createContext, useContext, useMemo } from "react";
import type { ReactNode } from "react";
import { createMockEmsApiClient, type EmsApiClient } from "./client";

const EmsApiContext = createContext<EmsApiClient | null>(null);

export interface EmsApiProviderProps {
  /** 注入的 client；省略時用 mock（P1 預設） */
  client?: EmsApiClient;
  children: ReactNode;
}

export function EmsApiProvider({ client, children }: EmsApiProviderProps) {
  // 未注入時，每個 Provider 建一個穩定的 mock client（避免 re-render 重建）
  const value = useMemo(() => client ?? createMockEmsApiClient(), [client]);
  return <EmsApiContext.Provider value={value}>{children}</EmsApiContext.Provider>;
}

export function useEmsApi(): EmsApiClient {
  const client = useContext(EmsApiContext);
  if (!client) {
    throw new Error("useEmsApi 必須在 <EmsApiProvider> 內使用");
  }
  return client;
}
