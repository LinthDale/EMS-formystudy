/**
 * PowerTrendChart — ECharts line chart，全面套用 'ems' theme（§6.4 gate 第 2 項）。
 * 顏色 / 字體一律來自 charts/theme.ts（由 tokens.css 推導），不在 option 內帶色票。
 */
import { useEffect, useRef } from "react";
import * as echarts from "echarts/core";
import { LineChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import { EMS_CHARTS_THEME_NAME, registerEmsChartsTheme } from "./theme";

let echartsReady = false;

/** tree-shaken 註冊（bundle 不背全量 echarts — NFR LCP）+ 'ems' theme（冪等） */
function ensureEchartsReady(): void {
  if (!echartsReady) {
    echarts.use([LineChart, GridComponent, TooltipComponent, CanvasRenderer]);
    registerEmsChartsTheme(echarts);
    echartsReady = true;
  }
}

export interface PowerTrendChartProps {
  /** 圖表 aria-label（a11y FR-532） */
  title: string;
  /** 數值序列（依小時序） */
  values: readonly number[];
  unit?: string;
  height?: number;
}

export function PowerTrendChart({
  title,
  values,
  unit = "kW",
  height = 260,
}: PowerTrendChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    ensureEchartsReady();

    const chart = echarts.init(el, EMS_CHARTS_THEME_NAME);
    chart.setOption({
      grid: { left: 48, right: 16, top: 24, bottom: 28 },
      tooltip: { trigger: "axis" },
      xAxis: {
        type: "category",
        data: values.map((_, i) => `${String(i).padStart(2, "0")}:00`),
      },
      yAxis: { type: "value", name: unit },
      series: [
        {
          type: "line",
          smooth: true,
          areaStyle: { opacity: 0.12 },
          data: [...values],
        },
      ],
    });

    const onResize = () => chart.resize();
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      chart.dispose();
    };
  }, [values, unit]);

  return (
    <div
      ref={containerRef}
      role="img"
      aria-label={title}
      style={{ height }}
      className="w-full"
    />
  );
}
