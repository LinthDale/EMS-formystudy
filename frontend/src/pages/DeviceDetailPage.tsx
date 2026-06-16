/**
 * DeviceDetailPage（FR-501）— 設備詳情 + signals。
 *
 * 基本資料 + 分類來源 / 信心（ConfidenceMeter）+ 狀態（DeviceStatusPill）+ signals
 * 列表（mock listSignals）。candidate 設備提供「前往審閱」連結（FR-510/511）。
 * device_id 由路由參數取得；資料三態經 AsyncBoundary（不白屏 / AC-5）。
 */
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";
import { useEmsApi } from "@/api/EmsApiContext";
import type { DeviceOut, SignalOut } from "@/api/types";
import { useAsync } from "@/lib/useAsync";
import { reviewPath } from "@/app/routes";
import { formatDateTime } from "@/lib/format";
import { AsyncBoundary } from "@/components/ems/AsyncBoundary";
import { DeviceStatusPill } from "@/components/ems/DeviceStatusPill";
import { ConfidenceMeter } from "@/components/ems/ConfidenceMeter";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface DetailData {
  readonly device: DeviceOut;
  readonly signals: readonly SignalOut[];
}

function FieldRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="text-xs text-fg-muted">{label}</dt>
      <dd className="text-sm text-fg">{children}</dd>
    </div>
  );
}

export function DeviceDetailPage() {
  const { t } = useTranslation();
  const api = useEmsApi();
  const { deviceId = "" } = useParams<{ deviceId: string }>();

  const state = useAsync<DetailData>(
    async () => {
      const [device, signals] = await Promise.all([
        api.getDevice(deviceId),
        api.listSignals(deviceId),
      ]);
      return { device, signals };
    },
    [api, deviceId],
  );

  const f = (key: string) => t(`deviceDetail.fields.${key}`);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-bold tracking-wide text-fg">
          {t("deviceDetail.title")}
        </h1>
        <p className="text-sm text-fg-secondary">{t("deviceDetail.subtitle")}</p>
      </div>

      <AsyncBoundary state={state}>
        {({ device, signals }) => (
          <div className="flex flex-col gap-6">
            <Card>
              <CardHeader className="flex-row items-center justify-between">
                <CardTitle>
                  <span className="font-mono">{device.device_id}</span>
                </CardTitle>
                <div className="flex items-center gap-3">
                  <DeviceStatusPill status={device.status} />
                  {device.status === "candidate" ? (
                    <Link
                      to={reviewPath(device.device_id)}
                      className="text-sm font-medium text-accent hover:underline"
                    >
                      {t("deviceDetail.reviewLink")}
                    </Link>
                  ) : null}
                </div>
              </CardHeader>
              <CardContent>
                <dl className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-3">
                  <FieldRow label={f("deviceType")}>
                    {device.device_type ?? "—"}
                  </FieldRow>
                  <FieldRow label={f("protocol")}>{device.protocol ?? "—"}</FieldRow>
                  <FieldRow label={f("vendor")}>{device.vendor ?? "—"}</FieldRow>
                  <FieldRow label={f("model")}>{device.model ?? "—"}</FieldRow>
                  <FieldRow label={f("location")}>{device.location ?? "—"}</FieldRow>
                  <FieldRow label={f("gatewayId")}>{device.gateway_id ?? "—"}</FieldRow>
                  <FieldRow label={f("classifiedBy")}>
                    {device.classified_by ?? "—"}
                  </FieldRow>
                  <FieldRow label={f("aiConfidence")}>
                    <ConfidenceMeter value={device.ai_confidence} />
                  </FieldRow>
                  <FieldRow label={f("lastSeenAt")}>
                    {formatDateTime(device.last_seen_at)}
                  </FieldRow>
                  <FieldRow label={f("createdAt")}>
                    {formatDateTime(device.created_at)}
                  </FieldRow>
                  <FieldRow label={f("confirmedAt")}>
                    {formatDateTime(device.confirmed_at)}
                  </FieldRow>
                </dl>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>{t("deviceDetail.signalsTitle")}</CardTitle>
              </CardHeader>
              <CardContent>
                {signals.length === 0 ? (
                  <span className="text-sm text-fg-secondary">
                    {t("deviceDetail.signalsEmpty")}
                  </span>
                ) : (
                  <table className="w-full border-collapse text-sm">
                    <caption className="sr-only">
                      {t("deviceDetail.signalsTitle")}
                    </caption>
                    <thead>
                      <tr className="border-b border-line-strong text-left text-xs text-fg-secondary">
                        <th scope="col" className="px-3 py-2">
                          {t("deviceDetail.signalHeaders.name")}
                        </th>
                        <th scope="col" className="px-3 py-2">
                          {t("deviceDetail.signalHeaders.unit")}
                        </th>
                        <th scope="col" className="px-3 py-2">
                          {t("deviceDetail.signalHeaders.datatype")}
                        </th>
                        <th scope="col" className="px-3 py-2">
                          {t("deviceDetail.signalHeaders.direction")}
                        </th>
                        <th scope="col" className="px-3 py-2">
                          {t("deviceDetail.signalHeaders.status")}
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {signals.map((s) => (
                        <tr key={s.id} className="border-b border-line">
                          <td className="px-3 py-2 font-mono text-fg">
                            {s.signal_name}
                          </td>
                          <td className="px-3 py-2 text-fg-secondary">
                            {s.unit ?? "—"}
                          </td>
                          <td className="px-3 py-2 text-fg-secondary">
                            {s.datatype ?? "—"}
                          </td>
                          <td className="px-3 py-2 text-fg-secondary">
                            {s.direction ?? "—"}
                          </td>
                          <td className="px-3 py-2 text-fg-secondary">{s.status}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </CardContent>
            </Card>
          </div>
        )}
      </AsyncBoundary>
    </div>
  );
}
