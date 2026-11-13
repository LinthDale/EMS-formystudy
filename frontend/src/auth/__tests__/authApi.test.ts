/**
 * authApi 測試 — 對 LIVE BFF auth 契約（services/bff/bff/routes/auth.py）。
 *
 * 契約（已在 routes/auth.py 核對）：
 * - POST /api/auth/login   {username,password} → 200 {username,role,expires_in} + Set-Cookie
 *                          401 {detail:"invalid credentials"}；503 provider 不可用
 * - POST /api/auth/logout  → 204（需 session）
 * - GET  /api/auth/session → 200 {username,role}；401 無/過期 session（session 內省端點）
 *
 * 全程 same-origin /api + credentials:include（cookie）；無手動 Origin。
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { createAuthApi } from "@/auth/authApi";
import { EmsNeedsLoginError } from "@/api/liveFetcher";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("authApi.login", () => {
  it("POST /api/auth/login 帶 username/password，回傳 {username,role}", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(jsonResponse({ username: "alice", role: "ops", expires_in: 28800 }));
    const auth = createAuthApi();
    const session = await auth.login("alice", "pw");
    expect(session).toEqual({ username: "alice", role: "ops" });
    expect(fetchSpy.mock.calls[0]?.[0]).toBe("/api/auth/login");
    const init = fetchSpy.mock.calls[0]?.[1] as RequestInit;
    expect(init.method).toBe("POST");
    expect(init.credentials).toBe("include");
    expect(init.body).toBe(JSON.stringify({ username: "alice", password: "pw" }));
    const headers = new Headers(init.headers);
    expect(headers.get("Content-Type")).toBe("application/json");
    expect(headers.has("origin")).toBe(false);
  });

  it("401 invalid credentials → 丟 EmsNeedsLoginError（UI 顯示帳密錯誤）", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ detail: "invalid credentials" }, 401),
    );
    const auth = createAuthApi();
    await expect(auth.login("alice", "bad")).rejects.toBeInstanceOf(EmsNeedsLoginError);
  });
});

describe("authApi.logout", () => {
  it("POST /api/auth/logout（204 No Content）解析為 void", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response(null, { status: 204 }));
    const auth = createAuthApi();
    await expect(auth.logout()).resolves.toBeUndefined();
    expect(fetchSpy.mock.calls[0]?.[0]).toBe("/api/auth/logout");
    expect((fetchSpy.mock.calls[0]?.[1] as RequestInit).method).toBe("POST");
  });
});

describe("authApi.currentSession（session 內省端點）", () => {
  it("GET /api/auth/session 200 → 回傳 {username,role}", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(jsonResponse({ username: "bob", role: "readonly" }));
    const auth = createAuthApi();
    await expect(auth.currentSession()).resolves.toEqual({
      username: "bob",
      role: "readonly",
    });
    expect(fetchSpy.mock.calls[0]?.[0]).toBe("/api/auth/session");
  });

  it("401（無/過期 session）→ 回傳 null（解讀為登出，非錯誤）", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ detail: "invalid or expired session" }, 401),
    );
    const auth = createAuthApi();
    await expect(auth.currentSession()).resolves.toBeNull();
  });

  it("未知 role 收斂為 'readonly'（最小權限）", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ username: "x", role: "superadmin" }),
    );
    const auth = createAuthApi();
    const session = await auth.currentSession();
    expect(session?.role).toBe("readonly");
  });
});
