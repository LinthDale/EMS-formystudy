/**
 * LoginPage（PRD-0005 Phase-1 Wave 2）— 本地帳密登入。
 *
 * - a11y：每個欄位有 <label htmlFor>；錯誤訊息 role="alert"（FR-532 / §9.5）。
 * - 經 AuthContext.login → POST /api/auth/login（同源 BFF；session 走 cookie）。
 * - 已登入時導回原目標（location.state.from）或首頁，避免停在登入頁。
 * - bundle 內零金鑰；密碼只在送出當下入記憶體，不持久化（§9.1/§9.2）。
 *
 * Wave 3（不在本批）：OIDC 登入按鈕——待 OIDC BFF agent 接線後再加。
 */
import { useId, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "@/auth/AuthContext";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface FromState {
  readonly from?: { readonly pathname?: string };
}

export function LoginPage() {
  const { t } = useTranslation();
  const auth = useAuth();
  const location = useLocation();
  const usernameId = useId();
  const passwordId = useId();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);

  // 已登入：導回原本想去的頁（守衛塞在 state.from），否則回首頁。
  if (auth.status === "authenticated") {
    const from = (location.state as FromState | null)?.from?.pathname ?? "/";
    return <Navigate to={from} replace />;
  }

  const onSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      await auth.login(username, password);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="mx-auto flex min-h-screen max-w-sm items-center justify-center p-4">
      <Card className="w-full">
        <CardHeader>
          <CardTitle>{t("auth.login.title")}</CardTitle>
          <p className="text-sm text-fg-secondary">{t("auth.login.subtitle")}</p>
        </CardHeader>
        <CardContent>
          <form className="flex flex-col gap-4" onSubmit={onSubmit} noValidate>
            <div className="flex flex-col gap-1">
              <label htmlFor={usernameId} className="text-xs text-fg-muted">
                {t("auth.login.username")}
              </label>
              <input
                id={usernameId}
                name="username"
                type="text"
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                className="rounded-md border border-line bg-surface px-3 py-2 text-sm text-fg"
              />
            </div>

            <div className="flex flex-col gap-1">
              <label htmlFor={passwordId} className="text-xs text-fg-muted">
                {t("auth.login.password")}
              </label>
              <input
                id={passwordId}
                name="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                className="rounded-md border border-line bg-surface px-3 py-2 text-sm text-fg"
              />
            </div>

            {auth.error ? (
              <div
                role="alert"
                className="rounded-md border border-danger/40 bg-surface px-3 py-2 text-sm text-danger"
              >
                {auth.error}
              </div>
            ) : null}

            <Button type="submit" variant="primary" disabled={submitting}>
              {submitting ? t("auth.login.submitting") : t("auth.login.submit")}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
