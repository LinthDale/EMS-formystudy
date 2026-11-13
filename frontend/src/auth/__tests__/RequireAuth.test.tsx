/**
 * RequireAuth 路由守衛測試。
 *
 * 驗：
 * - checking → 顯示驗證中（status），不洩漏受保護內容、不導向
 * - unauthenticated → 導向 /login
 * - authenticated → 渲染受保護內容
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { AuthProvider } from "@/auth/AuthContext";
import { RequireAuth } from "@/auth/RequireAuth";
import type { AuthApi } from "@/auth/authApi";
import type { AuthSession } from "@/auth/types";

function fakeAuthApi(currentSession: () => Promise<AuthSession | null>): AuthApi {
  return {
    login: vi.fn(async () => ({ username: "a", role: "ops" }) as AuthSession),
    logout: vi.fn(async () => {}),
    currentSession: vi.fn(currentSession),
  };
}

function renderGuarded(api: AuthApi) {
  return render(
    <AuthProvider authApi={api}>
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route
            path="/"
            element={
              <RequireAuth>
                <div>protected-content</div>
              </RequireAuth>
            }
          />
          <Route path="/login" element={<div>login-page</div>} />
        </Routes>
      </MemoryRouter>
    </AuthProvider>,
  );
}

describe("RequireAuth", () => {
  it("checking 期間顯示驗證中、不洩漏受保護內容", async () => {
    // 永不 resolve 的 session → 停在 checking
    const api = fakeAuthApi(() => new Promise(() => {}));
    renderGuarded(api);
    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.queryByText("protected-content")).not.toBeInTheDocument();
  });

  it("unauthenticated → 導向 /login", async () => {
    const api = fakeAuthApi(async () => null);
    renderGuarded(api);
    await waitFor(() => expect(screen.getByText("login-page")).toBeInTheDocument());
    expect(screen.queryByText("protected-content")).not.toBeInTheDocument();
  });

  it("authenticated → 渲染受保護內容", async () => {
    const api = fakeAuthApi(async () => ({ username: "a", role: "ops" }));
    renderGuarded(api);
    await waitFor(() =>
      expect(screen.getByText("protected-content")).toBeInTheDocument(),
    );
  });
});
