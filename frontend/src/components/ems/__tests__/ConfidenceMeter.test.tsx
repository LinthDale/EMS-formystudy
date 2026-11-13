/**
 * ConfidenceMeter（FR-510）：ai_confidence 0–1 視覺化。
 * 區帶：low < 0.5 ≤ medium < 0.8 ≤ high；null = 未分類；超界 clamp。
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { ConfidenceMeter, toConfidenceBand } from "@/components/ems/ConfidenceMeter";

describe("toConfidenceBand（純函數）", () => {
  it.each([
    [0, "low"],
    [0.49, "low"],
    [0.5, "medium"],
    [0.79, "medium"],
    [0.8, "high"],
    [1, "high"],
  ] as const)("%f → %s", (value, band) => {
    expect(toConfidenceBand(value)).toBe(band);
  });
});

describe("ConfidenceMeter", () => {
  it("以 role=meter 呈現並帶 aria-valuenow（a11y FR-532）", () => {
    render(<ConfidenceMeter value={0.93} />);
    const meter = screen.getByRole("meter");
    expect(meter).toHaveAttribute("aria-valuemin", "0");
    expect(meter).toHaveAttribute("aria-valuemax", "1");
    expect(meter).toHaveAttribute("aria-valuenow", "0.93");
    expect(meter).toHaveAttribute("data-band", "high");
  });

  it("顯示百分比文字（93%）", () => {
    render(<ConfidenceMeter value={0.93} />);
    expect(screen.getByText("93%")).toBeInTheDocument();
  });

  it.each([
    [0.42, "low"],
    [0.66, "medium"],
    [0.8, "high"],
  ] as const)("value %f → data-band %s", (value, band) => {
    render(<ConfidenceMeter value={value} />);
    expect(screen.getByRole("meter")).toHaveAttribute("data-band", band);
  });

  it("null → 顯示「未分類」且不渲染 meter", () => {
    render(<ConfidenceMeter value={null} />);
    expect(screen.queryByRole("meter")).toBeNull();
    expect(screen.getByText("未分類")).toBeInTheDocument();
  });

  it("超界值 clamp 至 [0,1]", () => {
    render(<ConfidenceMeter value={1.2} />);
    expect(screen.getByRole("meter")).toHaveAttribute("aria-valuenow", "1");
    expect(screen.getByText("100%")).toBeInTheDocument();
  });
});
