/**
 * DeviceStatusPill（FR-503）：candidate/confirmed/active/retired/unknown
 * 五態 + stale 修飾；open-ended enum 收斂（§13.2）；zh-Hant 標籤（FR-531）。
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { DeviceStatusPill } from "@/components/ems/DeviceStatusPill";

describe("DeviceStatusPill", () => {
  it.each([
    ["candidate", "候選"],
    ["confirmed", "已確認"],
    ["active", "運轉中"],
    ["retired", "已退役"],
  ] as const)("已知狀態 %s 顯示 zh-Hant 標籤「%s」", (status, label) => {
    render(<DeviceStatusPill status={status} />);
    const pill = screen.getByRole("status");
    expect(pill).toHaveTextContent(label);
    expect(pill).toHaveAttribute("data-status", status);
  });

  it("未知 enum 值收斂為 unknown（§13.2 open-ended enum handling）", () => {
    render(<DeviceStatusPill status="quarantined" />);
    const pill = screen.getByRole("status");
    expect(pill).toHaveAttribute("data-status", "unknown");
    expect(pill).toHaveTextContent("未知狀態");
  });

  it("null / undefined 亦收斂為 unknown（不丟例外）", () => {
    render(<DeviceStatusPill status={null} />);
    expect(screen.getByRole("status")).toHaveAttribute("data-status", "unknown");
  });

  it("stale 修飾：顯示「過時」並進 aria-label（a11y）", () => {
    render(<DeviceStatusPill status="retired" stale />);
    const pill = screen.getByRole("status");
    expect(pill).toHaveAttribute("data-stale", "true");
    expect(pill).toHaveTextContent("過時");
    expect(pill.getAttribute("aria-label")).toContain("已退役");
    expect(pill.getAttribute("aria-label")).toContain("過時");
  });

  it("非 stale 不出現「過時」", () => {
    render(<DeviceStatusPill status="active" />);
    const pill = screen.getByRole("status");
    expect(pill).not.toHaveAttribute("data-stale");
    expect(pill).not.toHaveTextContent("過時");
  });
});
