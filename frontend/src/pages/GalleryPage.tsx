/**
 * GalleryPage — EMS Design System 元件展示頁（§6.4）。
 * 用途：P1 design 驗收 gate 的 desktop/mobile 截圖 artifact；
 * 全部資料來自固定 mock fixtures（P1 不接 BFF，§9.3 wiring 屬 Phase 1）。
 */
import { useTranslation } from "react-i18next";
import {
  MOCK_DEVICES,
  MOCK_ELECTRICITY_LATEST,
  MOCK_FACTORY_LATEST,
  MOCK_POWER_SERIES_KW,
  MOCK_REVIEW_DIGEST,
} from "@/api/fixtures";
import { KNOWN_DEVICE_STATUSES } from "@/api/types";
import { DeviceStatusPill } from "@/components/ems/DeviceStatusPill";
import { ConfidenceMeter } from "@/components/ems/ConfidenceMeter";
import { MeasurementCard } from "@/components/ems/MeasurementCard";
import { SignalSparkline } from "@/components/ems/SignalSparkline";
import { ReviewDigestPanel } from "@/components/ems/ReviewDigestPanel";
import { DeviceTable } from "@/components/ems/DeviceTable";
import { FontSwitcher } from "@/components/ems/FontSwitcher";
import { PowerTrendChart } from "@/charts/PowerTrendChart";
import { Card, CardContent } from "@/components/ui/card";

const CONFIDENCE_SAMPLES = [0.18, 0.42, 0.66, 0.8, 0.93, null] as const;

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-3" aria-label={title}>
      <h2 className="text-lg font-semibold tracking-wide text-fg">{title}</h2>
      {children}
    </section>
  );
}

export function GalleryPage() {
  const { t } = useTranslation();

  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-bold tracking-wide text-fg">
          {t("gallery.title")}
        </h1>
        <p className="text-sm text-fg-secondary">{t("gallery.subtitle")}</p>
      </div>

      <Section title={t("gallery.sections.typography")}>
        <Card>
          <CardContent className="flex flex-col gap-3">
            <FontSwitcher />
            <p className="text-xs text-fg-muted">{t("typography.sectionHint")}</p>
          </CardContent>
        </Card>
      </Section>

      <Section title={t("gallery.sections.statusPill")}>
        <Card>
          <CardContent className="flex flex-wrap items-center gap-3">
            {KNOWN_DEVICE_STATUSES.map((status) => (
              <DeviceStatusPill key={status} status={status} />
            ))}
            <DeviceStatusPill status="quarantined" />
            <DeviceStatusPill status="retired" stale />
          </CardContent>
        </Card>
      </Section>

      <Section title={t("gallery.sections.confidenceMeter")}>
        <Card>
          <CardContent className="flex flex-wrap items-center gap-6">
            {CONFIDENCE_SAMPLES.map((value, i) => (
              <ConfidenceMeter key={i} value={value} />
            ))}
          </CardContent>
        </Card>
      </Section>

      <Section title={t("gallery.sections.measurementCard")}>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <MeasurementCard
            domain="electricity"
            label="即時功率"
            value={MOCK_ELECTRICITY_LATEST.power_kw}
            unit="kW"
            timestamp={MOCK_ELECTRICITY_LATEST.time}
          />
          <MeasurementCard
            domain="electricity"
            label="電壓"
            value={MOCK_ELECTRICITY_LATEST.voltage}
            unit="V"
            timestamp={MOCK_ELECTRICITY_LATEST.time}
          />
          <MeasurementCard
            domain="factory"
            label="馬達轉速"
            value={MOCK_FACTORY_LATEST.motor_speed}
            unit="RPM"
            digits={0}
            timestamp={MOCK_FACTORY_LATEST.time}
          />
          <MeasurementCard
            domain="factory"
            label="溫度（無值示範）"
            value={null}
            unit="°C"
          />
        </div>
      </Section>

      <Section title={t("gallery.sections.sparkline")}>
        <Card>
          <CardContent className="flex flex-wrap items-center gap-8">
            <SignalSparkline
              name="power_kw"
              values={MOCK_POWER_SERIES_KW}
              domain="electricity"
            />
            <SignalSparkline
              name="motor_speed"
              values={[1480, 1502, 1495, 1510, 1500, 1492]}
              domain="factory"
            />
            <SignalSparkline name="battery_pct" values={[88]} />
          </CardContent>
        </Card>
      </Section>

      <Section title={t("gallery.sections.reviewDigest")}>
        <ReviewDigestPanel review={MOCK_REVIEW_DIGEST} />
      </Section>

      <Section title={t("gallery.sections.deviceTable")}>
        <DeviceTable devices={MOCK_DEVICES} pageSize={4} />
      </Section>

      <Section title={t("gallery.sections.chartTheme")}>
        <Card>
          <CardContent>
            <PowerTrendChart
              title={t("gallery.chartDemoTitle")}
              values={MOCK_POWER_SERIES_KW}
              unit="kW"
            />
          </CardContent>
        </Card>
      </Section>
    </div>
  );
}
