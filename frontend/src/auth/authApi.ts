/**
 * authApi（PRD-0005 Phase-1 Wave 2）— LIVE BFF auth 契約 client。
 *
 * 端點（services/bff/bff/routes/auth.py，已核對）：
 * - POST /api/auth/login   {username,password} → 200 {username,role,expires_in}
 * - POST /api/auth/logout  → 204
 * - GET  /api/auth/session → 200 {username,role}（session 內省）；401 ⇒ 登出
 *
 * 全程經同源 live fetcher：credentials:include（session cookie，§9.2）、
 * 無手動 Origin（CSRF 靠 SameSite cookie + BFF Origin allowlist，§9.4）。
 * 復用 liveFetcher 的錯誤映射：login 401 → EmsNeedsLoginError（帳密錯誤）。
 */
import { createLiveFetcher, EmsNeedsLoginError } from "@/api/liveFetcher";
import type { Fetcher } from "@/api/client";
import { toRole, type AuthSession } from "./types";

const AUTH_BASE = "/api/auth";

function jsonPost(body: unknown): RequestInit {
  return {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

/** 從任意 BFF 回應抽出 {username, role}（role 經 toRole 收斂）。 */
function toSession(raw: unknown): AuthSession {
  const obj = (raw ?? {}) as { username?: unknown; role?: unknown };
  return {
    username: typeof obj.username === "string" ? obj.username : "",
    role: toRole(typeof obj.role === "string" ? obj.role : undefined),
  };
}

export interface AuthApi {
  /** POST /api/auth/login；401 ⇒ EmsNeedsLoginError（帳密錯誤）。 */
  login(username: string, password: string): Promise<AuthSession>;
  /** POST /api/auth/logout（204）。 */
  logout(): Promise<void>;
  /** GET /api/auth/session；401 ⇒ null（解讀為登出，非錯誤）。 */
  currentSession(): Promise<AuthSession | null>;
}

/**
 * 建立 authApi。預設用 live fetcher；測試可注入自訂 fetcher。
 */
export function createAuthApi(fetcher: Fetcher = createLiveFetcher()): AuthApi {
  return {
    login: async (username, password) => {
      const raw = await fetcher(`${AUTH_BASE}/login`, jsonPost({ username, password }));
      return toSession(raw);
    },
    logout: async () => {
      await fetcher(`${AUTH_BASE}/logout`, { method: "POST" });
    },
    currentSession: async () => {
      try {
        const raw = await fetcher(`${AUTH_BASE}/session`, undefined);
        return toSession(raw);
      } catch (err) {
        // 401（無/過期 session）是「未登入」的正常表態，不是錯誤。
        if (err instanceof EmsNeedsLoginError) return null;
        throw err;
      }
    },
  };
}
