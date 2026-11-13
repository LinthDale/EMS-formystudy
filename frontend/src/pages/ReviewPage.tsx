/**
 * ReviewPage（FR-511/512）— 審閱 digest + 確認 / 覆寫 / 拒絕動作。
 *
 * - digest 由 ReviewDigestPanel 純文字渲染（§9.5 已內建 XSS 防護）。
 * - 動作經 mock client（confirm / override / reject）；以後端回應為準更新結果訊息
 *   （AC-3 樂觀更新；失敗顯示明確錯誤 + 可重試 AC-5）。動作進行中禁用按鈕防重複送出。
 * - override 顯示最小表單（device_type）；signals 完整編輯屬 Wave 2（FR-513）。
 */
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import { useEmsApi } from "@/api/EmsApiContext";
import type { DigestOut } from "@/api/types";
import { useAsync } from "@/lib/useAsync";
import { AsyncBoundary } from "@/components/ems/AsyncBoundary";
import { ReviewDigestPanel } from "@/components/ems/ReviewDigestPanel";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

type ResultState =
  | { readonly kind: "idle" }
  | { readonly kind: "ok"; readonly text: string }
  | { readonly kind: "error" };

export function ReviewPage() {
  const { t } = useTranslation();
  const api = useEmsApi();
  const { deviceId = "" } = useParams<{ deviceId: string }>();

  const state = useAsync<DigestOut>(() => api.getHumanReview(deviceId), [api, deviceId]);

  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ResultState>({ kind: "idle" });
  const [overrideOpen, setOverrideOpen] = useState(false);
  const [overrideType, setOverrideType] = useState("");

  async function run(action: () => Promise<{ status: string; device_type?: string | null }>, toText: (d: { status: string; device_type?: string | null }) => string) {
    setBusy(true);
    setResult({ kind: "idle" });
    try {
      const updated = await action();
      setResult({ kind: "ok", text: toText(updated) });
    } catch {
      setResult({ kind: "error" });
    } finally {
      setBusy(false);
    }
  }

  const onConfirm = () =>
    run(
      () => api.confirmDevice(deviceId),
      (d) => t("review.result.confirmed", { id: deviceId, status: d.status }),
    );

  const onReject = () =>
    run(
      () => api.rejectDevice(deviceId),
      (d) => t("review.result.rejected", { id: deviceId, status: d.status }),
    );

  const onOverrideSubmit = () =>
    run(
      () => api.overrideDevice(deviceId, { device_type: overrideType, signals: [] }),
      (d) =>
        t("review.result.overridden", {
          id: deviceId,
          type: d.device_type ?? overrideType,
          status: d.status,
        }),
    );

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-bold tracking-wide text-fg">
          {t("review.pageTitle")}
        </h1>
        <p className="text-sm text-fg-secondary">{t("review.pageSubtitle")}</p>
      </div>

      <AsyncBoundary state={state}>
        {(digest) => (
          <div className="flex flex-col gap-6">
            <ReviewDigestPanel review={digest} />

            <Card className="max-w-xl">
              <CardHeader>
                <CardTitle>{t("review.pageTitle")}</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-4">
                <div className="flex flex-wrap gap-3">
                  <Button variant="primary" disabled={busy} onClick={onConfirm}>
                    {t("review.actions.confirm")}
                  </Button>
                  <Button
                    variant="secondary"
                    disabled={busy}
                    onClick={() => setOverrideOpen((o) => !o)}
                  >
                    {t("review.actions.override")}
                  </Button>
                  <Button variant="danger" disabled={busy} onClick={onReject}>
                    {t("review.actions.reject")}
                  </Button>
                </div>

                {overrideOpen ? (
                  <div className="flex flex-col gap-2 rounded-md border border-line p-3">
                    <label className="flex flex-col gap-1 text-xs text-fg-muted">
                      {t("review.override.typeLabel")}
                      <input
                        type="text"
                        value={overrideType}
                        onChange={(e) => setOverrideType(e.target.value)}
                        placeholder={t("review.override.typePlaceholder")}
                        aria-label={t("review.override.typeLabel")}
                        className="rounded-md border border-line bg-surface px-2 py-1.5 text-sm text-fg"
                      />
                    </label>
                    <div>
                      <Button
                        size="sm"
                        variant="primary"
                        disabled={busy || overrideType.trim() === ""}
                        onClick={onOverrideSubmit}
                      >
                        {t("review.override.submit")}
                      </Button>
                    </div>
                  </div>
                ) : null}

                {busy ? (
                  <span role="status" className="text-sm text-fg-muted">
                    {t("review.busy")}
                  </span>
                ) : null}
                {result.kind === "ok" ? (
                  <span role="status" className="text-sm text-ok">
                    {result.text}
                  </span>
                ) : null}
                {result.kind === "error" ? (
                  <span role="alert" className="text-sm text-danger">
                    {t("review.result.failed")}
                  </span>
                ) : null}
              </CardContent>
            </Card>
          </div>
        )}
      </AsyncBoundary>
    </div>
  );
}
