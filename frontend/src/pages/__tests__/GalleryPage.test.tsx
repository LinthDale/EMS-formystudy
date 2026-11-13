/**
 * GalleryPage（§6.4 P1 design 驗收 gate 的截圖 artifact 頁）煙霧測試：
 * - 全部 §6.4 章節呈現（6 個 domain components + chart theme demo）
 * - ECharts demo 以 'ems' theme 初始化（design gate 第 2 項：全面套用）
 * - 全字串 zh-Hant（FR-531）
 *
 * jsdom 無 canvas → echarts 以 mock 替身（僅驗 init/registerTheme 介面）；
 * theme 值仍由真 tokens.css 注入 documentElement 推導（單一真相）。
 */
import { beforeAll, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { parseTokens } from "@/test/parse-tokens";

const { initMock, registerThemeMock } = vi.hoisted(() => ({
  initMock: vi.fn((..._args: unknown[]) => ({
    setOption: vi.fn(),
    resize: vi.fn(),
    dispose: vi.fn(),
  })),
  registerThemeMock: vi.fn(),
}));

vi.mock("echarts/core", () => ({
  use: vi.fn(),
  registerTheme: registerThemeMock,
  init: initMock,
}));
vi.mock("echarts/charts", () => ({ LineChart: {} }));
vi.mock("echarts/components", () => ({ GridComponent: {}, TooltipComponent: {} }));
vi.mock("echarts/renderers", () => ({ CanvasRenderer: {} }));

import { GalleryPage } from "@/pages/GalleryPage";

beforeAll(() => {
  // 把 tokens.css 的值掛上 documentElement，讓 defaultTokenReader 讀得到（jsdom 不載入 CSS）
  for (const [name, value] of parseTokens()) {
    document.documentElement.style.setProperty(name, value);
  }
});

describe("GalleryPage", () => {
  it("渲染標題與全部元件章節（§6.4 gate 截圖頁）", () => {
    render(<GalleryPage />);
    expect(
      screen.getByRole("heading", { name: "EMS Design System 元件展示" }),
    ).toBeInTheDocument();
    for (const section of [
      /DeviceStatusPill/,
      /ConfidenceMeter/,
      /MeasurementCard/,
      /SignalSparkline/,
      /ReviewDigestPanel/,
      /DeviceTable/,
      /ECharts/,
    ]) {
      expect(screen.getByRole("heading", { name: section })).toBeInTheDocument();
    }
  });

  it("狀態徽章五態 + stale 全部展示（FR-503）", () => {
    render(<GalleryPage />);
    const pills = screen.getAllByRole("status");
    const statuses = pills.map((p) => p.getAttribute("data-status"));
    for (const s of ["candidate", "confirmed", "active", "retired", "unknown"]) {
      expect(statuses, `缺 ${s} 展示`).toContain(s);
    }
    expect(pills.some((p) => p.getAttribute("data-stale") === "true")).toBe(true);
  });

  it("ECharts demo 以 'ems' theme 初始化（無 default 配色）", () => {
    render(<GalleryPage />);
    expect(registerThemeMock).toHaveBeenCalledWith("ems", expect.any(Object));
    expect(initMock).toHaveBeenCalled();
    expect(initMock.mock.calls[0]?.[1]).toBe("ems");
  });

  it("設備清單與量測卡片以 mock fixtures 呈現", () => {
    render(<GalleryPage />);
    expect(screen.getByRole("table", { name: "設備清單" })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "即時功率" })).toBeInTheDocument();
  });
});
