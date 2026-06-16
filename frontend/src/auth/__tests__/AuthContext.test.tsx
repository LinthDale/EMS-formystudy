/**
 * AuthContext 測試 — session 解析 + login/logout 狀態流轉。
 *
 * 測試以注入的假 AuthApi 行使 context（不打真網路）；驗：
 * - mount 時呼叫 currentSession 解析狀態（authenticated / unauthenticated）
 * - login 成功 → status=authenticated + 帶 role/username
 * - logout → 回到 unauthenticated
 * - login 401 → 維持 unauthenticated 並透出錯誤
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AuthProvider, useAuth } from "@/auth/AuthContext";
import type { AuthApi } from "@/auth/authApi";
import type { AuthSession } from "@/auth/types";
import { EmsNeedsLoginError } from "@/api/liveFetcher";

function fakeAuthApi(overrides: Partial<AuthApi> = {}): AuthApi {
  return {
    login: vi.fn(async () => ({ username: "alice", role: "ops" }) as AuthSession),
    logout: vi.fn(async () => {}),
    currentSession: vi.fn(async () => null),
    ...overrides,
  };
}

function Probe() {
  const auth = useAuth();
  return (
    <div>
      <span data-testid="status">{auth.status}</span>
      <span data-testid="username">{auth.username ?? "-"}</span>
      <span data-testid="role">{auth.role ?? "-"}</span>
      <span data-testid="error">{auth.error ?? "-"}</span>
      <button onClick={() => void auth.login("alice", "pw")}>do-login</button>
      <button onClick={() => void auth.logout()}>do-logout</button>
    </div>
  );
}

function renderWith(api: AuthApi) {
  return render(
    <AuthProvider authApi={api}>
      <Probe />
    </AuthProvider>,
  );
}

describe("AuthProvider — 初始 session 解析", () => {
  it("無 session（currentSession→null）→ status=unauthenticated", async () => {
    renderWith(fakeAuthApi());
    await waitFor(() =>
      expect(screen.getByTestId("status")).toHaveTextContent("unauthenticated"),
    );
    expect(screen.getByTestId("username")).toHaveTextContent("-");
  });

  it("有 session → status=authenticated 並帶 username/role", async () => {
    renderWith(
      fakeAuthApi({
        currentSession: vi.fn(
          async (): Promise<AuthSession> => ({ username: "bob", role: "ingest" }),
        ),
      }),
    );
    await waitFor(() =>
      expect(screen.getByTestId("status")).toHaveTextContent("authenticated"),
    );
    expect(screen.getByTestId("username")).toHaveTextContent("bob");
    expect(screen.getByTestId("role")).toHaveTextContent("ingest");
  });
});

describe("AuthProvider — login / logout", () => {
  it("login 成功 → authenticated（role 反映於 context）", async () => {
    const user = userEvent.setup();
    renderWith(fakeAuthApi());
    await waitFor(() =>
      expect(screen.getByTestId("status")).toHaveTextContent("unauthenticated"),
    );
    await user.click(screen.getByText("do-login"));
    await waitFor(() =>
      expect(screen.getByTestId("status")).toHaveTextContent("authenticated"),
    );
    expect(screen.getByTestId("role")).toHaveTextContent("ops");
    expect(screen.getByTestId("username")).toHaveTextContent("alice");
  });

  it("logout → 回到 unauthenticated 並清空 username/role", async () => {
    const user = userEvent.setup();
    renderWith(
      fakeAuthApi({
        currentSession: vi.fn(
          async (): Promise<AuthSession> => ({ username: "bob", role: "ops" }),
        ),
      }),
    );
    await waitFor(() =>
      expect(screen.getByTestId("status")).toHaveTextContent("authenticated"),
    );
    await user.click(screen.getByText("do-logout"));
    await waitFor(() =>
      expect(screen.getByTestId("status")).toHaveTextContent("unauthenticated"),
    );
    expect(screen.getByTestId("username")).toHaveTextContent("-");
  });

  it("login 401 → 維持 unauthenticated 並透出錯誤訊息", async () => {
    const user = userEvent.setup();
    renderWith(
      fakeAuthApi({
        login: vi.fn(async () => {
          throw new EmsNeedsLoginError();
        }),
      }),
    );
    await waitFor(() =>
      expect(screen.getByTestId("status")).toHaveTextContent("unauthenticated"),
    );
    await user.click(screen.getByText("do-login"));
    await waitFor(() =>
      expect(screen.getByTestId("error")).not.toHaveTextContent("-"),
    );
    expect(screen.getByTestId("status")).toHaveTextContent("unauthenticated");
  });
});

describe("useAuth — 防呆", () => {
  it("在 Provider 外使用即丟錯", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    expect(() => render(<Probe />)).toThrow();
    spy.mockRestore();
  });
});
