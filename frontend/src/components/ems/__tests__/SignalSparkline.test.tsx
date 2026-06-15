/**
 * SignalSparkline（FR-501/520）：signal 迷你趨勢（純 SVG，顏色引用 token）。
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import {
  SignalSparkline,
  buildSparklinePoints,
} from "@/components/ems/SignalSparkline";

describe("buildSparklinePoints（純函數）", () => {
  it("首末點落在左右 padding 邊界", () => {
    const pts = buildSparklinePoints([1, 2, 3], 120, 32, 2);
    const pairs = pts.split(" ").map((p) => p.split(",").map(Number));
    expect(pairs[0]?.[0]).toBe(2);
    expect(pairs[pairs.length - 1]?.[0]).toBe(118);
  });

  it("常數序列 → 水平中線（不除以零）", () => {
    const pts = buildSparklinePoints([5, 5, 5], 120, 32, 2);
    const ys = pts.split(" ").map((p) => Number(p.split(",")[1]));
    expect(new Set(ys).size).toBe(1);
    expect(ys[0]).toBe(16);
  });

  it("最大值在頂、最小值在底（y 軸反向）", () => {
    const pts = buildSparklinePoints([0, 10], 100, 40, 0);
    const ys = pts.split(" ").map((p) => Number(p.split(",")[1]));
    expect(ys[0]).toBe(40); // min → bottom
    expect(ys[1]).toBe(0); // max → top
  });

  it("不改變輸入陣列（immutability）", () => {
    const input = [3, 1, 2];
    buildSparklinePoints(input, 100, 40, 2);
    expect(input).toEqual([3, 1, 2]);
  });
});

describe("SignalSparkline", () => {
  it("以 role=img + aria-label 呈現（a11y FR-532）", () => {
    const { container } = render(
      <SignalSparkline name="power_kw" values={[1, 2, 3, 2]} />,
    );
    expect(screen.getByRole("img", { name: "power_kw 趨勢" })).toBeInTheDocument();
    const polyline = container.querySelector("polyline");
    expect(polyline).not.toBeNull();
    expect(polyline?.getAttribute("points")).toBeTruthy();
  });

  it("線色引用 design token（var(--ems-…)），無硬編色票", () => {
    const { container } = render(
      <SignalSparkline name="power_kw" values={[1, 2, 3]} domain="electricity" />,
    );
    const stroke = container.querySelector("polyline")?.getAttribute("stroke") ?? "";
    expect(stroke).toMatch(/^var\(--ems-/);
  });

  it("資料 < 2 點 → 顯示「資料不足」且不渲染 svg", () => {
    const { container } = render(<SignalSparkline name="x" values={[1]} />);
    expect(container.querySelector("svg")).toBeNull();
    expect(screen.getByText("資料不足")).toBeInTheDocument();
  });
});
