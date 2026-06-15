/**
 * MeasurementCard（FR-520）：依域（electricity / factory）顯示最新量測值。
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MeasurementCard } from "@/components/ems/MeasurementCard";

describe("MeasurementCard", () => {
  it("顯示量測名稱、數值與單位（electricity 域）", () => {
    render(
      <MeasurementCard
        domain="electricity"
        label="即時功率"
        value={58.7}
        unit="kW"
        timestamp="2026-06-11T02:59:30Z"
      />,
    );
    const card = screen.getByRole("group", { name: "即時功率" });
    expect(card).toHaveAttribute("data-domain", "electricity");
    expect(screen.getByText("58.7")).toBeInTheDocument();
    expect(screen.getByText("kW")).toBeInTheDocument();
    expect(screen.getByText("電力")).toBeInTheDocument();
  });

  it("factory 域帶 data-domain=factory 與「工廠」域標", () => {
    render(
      <MeasurementCard domain="factory" label="馬達轉速" value={1500} unit="RPM" digits={0} />,
    );
    expect(screen.getByRole("group", { name: "馬達轉速" })).toHaveAttribute(
      "data-domain",
      "factory",
    );
    expect(screen.getByText("1500")).toBeInTheDocument();
    expect(screen.getByText("工廠")).toBeInTheDocument();
  });

  it("無值 → em-dash，不顯示 NaN / undefined", () => {
    render(<MeasurementCard domain="electricity" label="即時功率" value={null} unit="kW" />);
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.queryByText(/NaN|undefined/)).toBeNull();
  });

  it("timestamp 以 zh-Hant 呈現「更新於」", () => {
    render(
      <MeasurementCard
        domain="electricity"
        label="即時功率"
        value={58.7}
        unit="kW"
        timestamp="2026-06-11T02:59:30Z"
      />,
    );
    expect(screen.getByText(/更新於/)).toBeInTheDocument();
  });
});
