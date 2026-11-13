/**
 * DeviceListPage（FR-500）— 設備清單頁。
 *
 * status / type 篩選經 BFF `GET /devices?status=&type=`（P1 mock）；排序 + 載入更多
 * 由既有 DeviceTable 負責（§8.1.1 bare-array：infinite-scroll / 載入更多）。
 * device_id 連結至設備詳情（FR-501）。資料三態經 AsyncBoundary（不白屏 / AC-5）。
 */
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { useEmsApi } from "@/api/EmsApiContext";
import { KNOWN_DEVICE_STATUSES, type DeviceRow } from "@/api/types";
import { useAsync } from "@/lib/useAsync";
import { deviceDetailPath } from "@/app/routes";
import { AsyncBoundary } from "@/components/ems/AsyncBoundary";
import { DeviceTable } from "@/components/ems/DeviceTable";

/** 篩選用 device_type 選項（自 fixtures 推導，去重；不硬編） */
function deriveTypes(devices: readonly DeviceRow[]): readonly string[] {
  const set = new Set<string>();
  for (const d of devices) {
    if (d.device_type) set.add(d.device_type);
  }
  return [...set].sort();
}

export function DeviceListPage() {
  const { t } = useTranslation();
  const api = useEmsApi();
  const [status, setStatus] = useState("");
  const [type, setType] = useState("");

  const state = useAsync<DeviceRow[]>(
    () =>
      api.listDevices({
        ...(status ? { status } : {}),
        ...(type ? { type } : {}),
      }),
    [api, status, type],
  );

  // type 選項取自「全部設備」（不受目前篩選影響）以維持選單穩定
  const allState = useAsync<DeviceRow[]>(() => api.listDevices(), [api]);
  const typeOptions = useMemo(
    () => deriveTypes(allState.data ?? []),
    [allState.data],
  );

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-bold tracking-wide text-fg">
          {t("deviceList.title")}
        </h1>
        <p className="text-sm text-fg-secondary">{t("deviceList.subtitle")}</p>
      </div>

      <div className="flex flex-wrap gap-4">
        <label className="flex flex-col gap-1 text-xs text-fg-muted">
          {t("deviceList.filterStatus")}
          <select
            aria-label={t("deviceList.filterStatus")}
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            className="rounded-md border border-line bg-surface px-2 py-1.5 text-sm text-fg"
          >
            <option value="">{t("deviceList.allStatuses")}</option>
            {KNOWN_DEVICE_STATUSES.map((s) => (
              <option key={s} value={s}>
                {t(`device.status.${s}`)}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1 text-xs text-fg-muted">
          {t("deviceList.filterType")}
          <select
            aria-label={t("deviceList.filterType")}
            value={type}
            onChange={(e) => setType(e.target.value)}
            className="rounded-md border border-line bg-surface px-2 py-1.5 text-sm text-fg"
          >
            <option value="">{t("deviceList.allTypes")}</option>
            {typeOptions.map((ty) => (
              <option key={ty} value={ty}>
                {ty}
              </option>
            ))}
          </select>
        </label>
      </div>

      <AsyncBoundary state={state}>
        {(devices) => (
          <div className="flex flex-col gap-2">
            <span className="text-xs text-fg-muted">
              {t("deviceList.resultCount", { count: devices.length })}
            </span>
            <DeviceTable
              devices={devices}
              renderDeviceId={(id) => (
                <Link
                  to={deviceDetailPath(id)}
                  className="font-mono text-accent hover:underline"
                >
                  {id}
                </Link>
              )}
            />
          </div>
        )}
      </AsyncBoundary>
    </div>
  );
}
