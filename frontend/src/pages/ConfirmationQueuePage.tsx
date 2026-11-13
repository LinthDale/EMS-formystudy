/**
 * ConfirmationQueuePage（FR-510）— 低信心確認佇列。
 *
 * 只列 `status=candidate`（AC-1：非 candidate 不入佇列）；依 ai_confidence 排序
 * （預設 asc：最低信心、最需人工關注者在前）。每列含 ConfidenceMeter + 審閱連結
 * （→ ReviewPage FR-511/512）。空佇列有明確 empty state（AC-1）。
 */
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { useEmsApi } from "@/api/EmsApiContext";
import type { DeviceRow, SortOrder } from "@/api/types";
import { useAsync } from "@/lib/useAsync";
import { reviewPath } from "@/app/routes";
import { AsyncBoundary } from "@/components/ems/AsyncBoundary";
import { ConfidenceMeter } from "@/components/ems/ConfidenceMeter";
import { DeviceStatusPill } from "@/components/ems/DeviceStatusPill";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

export function ConfirmationQueuePage() {
  const { t } = useTranslation();
  const api = useEmsApi();
  const [order, setOrder] = useState<SortOrder>("asc");

  const state = useAsync<DeviceRow[]>(
    () => api.listDevices({ status: "candidate", sort: "ai_confidence", order }),
    [api, order],
  );

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-bold tracking-wide text-fg">{t("queue.title")}</h1>
        <p className="text-sm text-fg-secondary">{t("queue.subtitle")}</p>
      </div>

      <AsyncBoundary state={state}>
        {(candidates) =>
          candidates.length === 0 ? (
            <div className="flex flex-col items-center gap-1 rounded-lg border border-dashed border-line p-8">
              <span className="text-sm text-fg-secondary">{t("queue.empty")}</span>
            </div>
          ) : (
            <div className="flex flex-col gap-3">
              <div className="flex items-center justify-between gap-3">
                <span className="text-xs text-fg-muted">
                  {t("queue.countLabel", { count: candidates.length })}
                </span>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => setOrder((o) => (o === "asc" ? "desc" : "asc"))}
                  title={t("queue.sortHint")}
                  aria-pressed={order === "desc"}
                >
                  {t("confidence.label")} {order === "asc" ? "▲" : "▼"}
                </Button>
              </div>
              <ul className="flex flex-col gap-2">
                {candidates.map((d) => (
                  <li key={d.device_id}>
                    <Card>
                      <CardContent className="flex flex-wrap items-center justify-between gap-4">
                        <div className="flex items-center gap-3">
                          <span className="font-mono text-sm text-fg">
                            {d.device_id}
                          </span>
                          <DeviceStatusPill status={d.status} stale={d.stale} />
                          <span className="text-sm text-fg-secondary">
                            {d.device_type ?? "—"}
                          </span>
                        </div>
                        <div className="flex items-center gap-4">
                          <ConfidenceMeter value={d.ai_confidence} />
                          <Link
                            to={reviewPath(d.device_id)}
                            className="text-sm font-medium text-accent hover:underline"
                          >
                            {t("queue.reviewAction")}
                          </Link>
                        </div>
                      </CardContent>
                    </Card>
                  </li>
                ))}
              </ul>
            </div>
          )
        }
      </AsyncBoundary>
    </div>
  );
}
