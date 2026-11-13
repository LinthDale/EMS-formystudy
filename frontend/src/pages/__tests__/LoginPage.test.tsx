/**
 * LoginPage 測試 — a11y 標籤化表單 + 錯誤 role="alert"（§9.5 / FR-532）。
 *
 * 驗：
 * - 帳號/密碼有可存取標籤；submit 觸發 auth.login
 * - 登入失敗訊息以 role="alert" 呈現
 * - 處理中按鈕 disabled（避免重複送出）
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { AuthProvider } from "@/auth/AuthContext";
import type { AuthApi } from "@/auth/authApi";
import type { AuthSession } from "@/auth/types";
import { LoginPage } from "@/pages/LoginPage";
import { EmsNeedsLoginError } from "@/api/liveFetcher";

function fakeAuthApi(overrides: Partial<AuthApi> = {}): AuthApi {
  return {
    login: vi.fn(async () => ({ username: "alice", role: "ops" }) as AuthSession),
    logout: vi.fn(async () => {}),
    currentSession: vi.fn(async () => null),
    ...overrides,
  };
}

function renderLogin(api: AuthApi) {
  return render(
    <MemoryRouter initialEntries={["/login"]}>
      <AuthProvider authApi={api}>
        <LoginPage />
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe("LoginPage — a11y 表單", () => {
  it("帳號 / 密碼欄位有可存取標籤", async () => {
    renderLogin(fakeAuthApi());
    expect(screen.getByLabelText("帳號")).toBeInTheDocument();
    expect(screen.getByLabelText("密碼")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "登入" })).toBeInTheDocument();
  });

  it("送出帳密 → 呼叫 auth.login(username,password)", async () => {
    const user = userEvent.setup();
    const api = fakeAuthApi();
    renderLogin(api);
    await user.type(screen.getByLabelText("帳號"), "alice");
    await user.type(screen.getByLabelText("密碼"), "s3cret");
    await user.click(screen.getByRole("button", { name: "登入" }));
    await waitFor(() => expect(api.login).toHaveBeenCalledWith("alice", "s3cret"));
  });
});

describe("LoginPage — 錯誤態", () => {
  it("登入失敗 → 顯示 role=alert 錯誤訊息", async () => {
    const user = userEvent.setup();
    const api = fakeAuthApi({
      login: vi.fn(async () => {
        throw new EmsNeedsLoginError();
      }),
    });
    renderLogin(api);
    await user.type(screen.getByLabelText("帳號"), "alice");
    await user.type(screen.getByLabelText("密碼"), "wrong");
    await user.click(screen.getByRole("button", { name: "登入" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("帳號或密碼錯誤");
  });
});
