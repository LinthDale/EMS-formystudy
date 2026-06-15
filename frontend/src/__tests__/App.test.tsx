/**
 * App shell 煙霧測試：landmark（banner/main）+ 品牌字串 zh-Hant（FR-531/532）。
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

vi.mock("echarts/core", () => ({
  use: vi.fn(),
  registerTheme: vi.fn(),
  init: vi.fn(() => ({ setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn() })),
}));
vi.mock("echarts/charts", () => ({ LineChart: {} }));
vi.mock("echarts/components", () => ({ GridComponent: {}, TooltipComponent: {} }));
vi.mock("echarts/renderers", () => ({ CanvasRenderer: {} }));

import { App } from "@/App";
import { parseTokens } from "@/test/parse-tokens";

describe("App", () => {
  it("渲染 banner / main landmark 與品牌字串（a11y FR-532）", () => {
    for (const [name, value] of parseTokens()) {
      document.documentElement.style.setProperty(name, value);
    }
    render(<App />);
    expect(screen.getByRole("banner")).toBeInTheDocument();
    expect(screen.getByRole("main")).toBeInTheDocument();
    expect(screen.getByText("SynaIQ EMS")).toBeInTheDocument();
    expect(screen.getByText("能源管理平台")).toBeInTheDocument();
    // gallery 掛載於 main 之下
    expect(
      screen.getByRole("heading", { name: "EMS Design System 元件展示" }),
    ).toBeInTheDocument();
  });
});
