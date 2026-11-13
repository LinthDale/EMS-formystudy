/**
 * DeviceDetailPage（FR-501）測試：基本資料 + signals 列表 + candidate 的審閱連結。
 */
import { describe, expect, it } from "vitest";
import { screen, within } from "@testing-library/react";
import { renderRoute } from "@/test/render-route";

describe("DeviceDetailPage", () => {
  it("渲染設備基本資料與 signals（FR-501）", async () => {
    renderRoute({ path: "/devices/sim-001" });
    // 標題區 device_id
    expect(await screen.findByText("sim-001")).toBeInTheDocument();
    // signals（mock 有 voltage/current/power_kw）
    expect(screen.getByText("voltage")).toBeInTheDocument();
    expect(screen.getByText("power_kw")).toBeInTheDocument();
  });

  it("candidate 設備提供前往審閱連結（FR-510/511）", async () => {
    renderRoute({ path: "/devices/mqtt-7f3a" });
    const link = await screen.findByRole("link", { name: /前往審閱/ });
    expect(link).toHaveAttribute("href", "/queue/mqtt-7f3a");
  });

  it("非 candidate 設備不顯示審閱連結", async () => {
    renderRoute({ path: "/devices/sim-001" });
    await screen.findByText("sim-001");
    expect(screen.queryByRole("link", { name: /前往審閱/ })).not.toBeInTheDocument();
  });

  it("無 signal 的設備顯示 empty state", async () => {
    renderRoute({ path: "/devices/mqtt-7f3a" });
    await screen.findByText("mqtt-7f3a");
    const signalsRegion = screen.getByText("此設備尚無 signal");
    expect(signalsRegion).toBeInTheDocument();
  });

  it("查無設備時顯示錯誤態 + 可重試（AC-5）", async () => {
    renderRoute({ path: "/devices/does-not-exist" });
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    const alert = screen.getByRole("alert");
    expect(within(alert).getByRole("button", { name: "重試" })).toBeInTheDocument();
  });
});
