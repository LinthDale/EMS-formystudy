/**
 * AuthContext（PRD-0005 Phase-1 Wave 2）— 本地登入 + session 狀態。
 *
 * 職責：
 * - mount 時呼叫 BFF session 內省（GET /api/auth/session）解析登入狀態（401 ⇒ 登出）
 * - 暴露 {status, role, username, error, login, logout, refresh}
 * - login/logout 經 LIVE BFF（authApi）；401 ⇒ 帳密錯誤、503 ⇒ 服務不可用
 *
 * role 僅供 UX（隱藏/禁用無權操作）；真正權限邊界在 BFF + 後端（§9.1）。
 * 不在 localStorage/sessionStorage 存任何 session 衍生物（§9.2）——狀態僅存於記憶體，
 * 真相是 HttpOnly cookie + BFF 每請求驗證。
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { createAuthApi, type AuthApi } from "./authApi";
import type { AuthSession, Role } from "./types";
import {
  EmsApiError,
  EmsNeedsLoginError,
  EmsServerError,
} from "@/api/liveFetcher";

export type AuthStatus = "checking" | "authenticated" | "unauthenticated";

export interface AuthContextValue {
  readonly status: AuthStatus;
  readonly role: Role | null;
  readonly username: string | null;
  /** login 失敗的人類可讀訊息（成功/未嘗試時為 null）。 */
  readonly error: string | null;
  /**
   * 成功即進 authenticated；失敗「不 reject」（一律 resolve），失敗訊息透過
   * `error` 表態，回傳 boolean 供呼叫端判斷（避免每個呼叫端都要 try/catch）。
   */
  login(username: string, password: string): Promise<boolean>;
  logout(): Promise<void>;
  /** 重新向 BFF 確認 session（例：收到 401 後）。 */
  refresh(): Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export interface AuthProviderProps {
  /** 注入的 authApi（測試用）；省略時用 live BFF。 */
  authApi?: AuthApi;
  children: ReactNode;
}

export function AuthProvider({ authApi, children }: AuthProviderProps) {
  const { t } = useTranslation();
  const api = useMemo(() => authApi ?? createAuthApi(), [authApi]);

  const [status, setStatus] = useState<AuthStatus>("checking");
  const [session, setSession] = useState<AuthSession | null>(null);
  const [error, setError] = useState<string | null>(null);

  /** login 失敗訊息分流（不外洩後端細節）。 */
  const loginErrorMessage = useCallback(
    (err: unknown): string => {
      if (err instanceof EmsNeedsLoginError) return t("auth.login.invalidCredentials");
      // 503：OIDC mode selected but not integrated / provider 不可用（auth.py）。
      if (err instanceof EmsServerError && err.status === 503) {
        return t("auth.login.unavailable");
      }
      if (err instanceof EmsApiError && err.status === 503) {
        return t("auth.login.unavailable");
      }
      return t("auth.login.genericError");
    },
    [t],
  );

  const resolveSession = useCallback(async () => {
    const next = await api.currentSession();
    setSession(next);
    setStatus(next ? "authenticated" : "unauthenticated");
  }, [api]);

  useEffect(() => {
    let cancelled = false;
    setStatus("checking");
    api
      .currentSession()
      .then((next) => {
        if (cancelled) return;
        setSession(next);
        setStatus(next ? "authenticated" : "unauthenticated");
      })
      .catch(() => {
        if (cancelled) return;
        // session 內省失敗（非 401，例：5xx）：保守視為未登入，使用者可再試登入。
        setSession(null);
        setStatus("unauthenticated");
      });
    return () => {
      cancelled = true;
    };
  }, [api]);

  const login = useCallback(
    async (username: string, password: string): Promise<boolean> => {
      setError(null);
      try {
        const next = await api.login(username, password);
        setSession(next);
        setStatus("authenticated");
        return true;
      } catch (err) {
        setSession(null);
        setStatus("unauthenticated");
        setError(loginErrorMessage(err));
        return false;
      }
    },
    [api, loginErrorMessage],
  );

  const logout = useCallback(async () => {
    setError(null);
    try {
      await api.logout();
    } finally {
      // 即使 logout 請求失敗也清本地狀態（cookie 由 BFF 端負責失效）。
      setSession(null);
      setStatus("unauthenticated");
    }
  }, [api]);

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      role: session?.role ?? null,
      username: session?.username ?? null,
      error,
      login,
      logout,
      refresh: resolveSession,
    }),
    [status, session, error, login, logout, resolveSession],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth 必須在 <AuthProvider> 內使用");
  }
  return ctx;
}
