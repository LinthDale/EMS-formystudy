/**
 * DeviceListPage（FR-500）測試：mock 資料載入 + status 篩選 + device_id 連結至詳情。
 */
import { describe, expect, it } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderRoute } from "@/test/render-route";

describe("DeviceListPage", () => {
  it("載入 mock 設備清單並渲染表格（FR-500）", async () => {
    renderRoute({ path: "/devices" });
    expect(
      await screen.findByRole("table", { name: "設備清單" }),
    ).toBeInTheDocument();
    expect(screen.getByText("sim-001")).toBeInTheDocument();
  });

  it("device_id 為連結，導向設備詳情（FR-501）", async () => {
    renderRoute({ path: "/devices" });
    const link = await screen.findByRole("link", { name: "sim-001" });
    expect(link).toHaveAttribute("href", "/devices/sim-001");
  });

  it("依 status 篩選只剩符合的設備（經 BFF query）", async () => {
    const user = userEvent.setup();
    renderRoute({ path: "/devices" });
    await screen.findByText("sim-001");

    await user.selectOptions(
      screen.getByRole("combobox", { name: "狀態篩選" }),
      "candidate",
    );

    await waitFor(() => {
      expect(screen.queryByText("sim-001")).not.toBeInTheDocument();
    });
    const table = screen.getByRole("table", { name: "設備清單" });
    expect(within(table).getByText("mqtt-7f3a")).toBeInTheDocument();
  });
});
