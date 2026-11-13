/**
 * ConfirmationQueuePage（FR-510）測試：只列 candidate（AC-1）、依信心排序、審閱連結、空態。
 */
import { describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { renderRoute } from "@/test/render-route";
import { createMockEmsApiClient } from "@/api/client";

describe("ConfirmationQueuePage", () => {
  it("只列出 candidate 設備（AC-1）", async () => {
    renderRoute({ path: "/queue" });
    await screen.findByText("mqtt-7f3a");
    // confirmed/active/retired 設備不入佇列
    expect(screen.queryByText("sim-001")).not.toBeInTheDocument();
    expect(screen.queryByText("plc-001")).not.toBeInTheDocument();
  });

  it("預設依 ai_confidence asc（最低信心在前）", async () => {
    const client = createMockEmsApiClient();
    const spy = vi.spyOn(client, "listDevices");
    renderRoute({ path: "/queue", client });
    await screen.findByText("mqtt-7f3a");
    expect(spy).toHaveBeenCalledWith({
      status: "candidate",
      sort: "ai_confidence",
      order: "asc",
    });
  });

  it("每列含審閱連結至 ReviewPage（FR-511/512）", async () => {
    renderRoute({ path: "/queue" });
    const links = await screen.findAllByRole("link", { name: "審閱" });
    expect(links.length).toBeGreaterThan(0);
    expect(links.some((l) => l.getAttribute("href") === "/queue/mqtt-7f3a")).toBe(true);
  });

  it("空佇列顯示明確 empty state（AC-1）", async () => {
    const client = createMockEmsApiClient();
    vi.spyOn(client, "listDevices").mockResolvedValue([]);
    renderRoute({ path: "/queue", client });
    expect(
      await screen.findByText("目前沒有待確認的候選設備"),
    ).toBeInTheDocument();
  });

  it("切換排序方向會以 desc 重新查詢", async () => {
    const client = createMockEmsApiClient();
    const spy = vi.spyOn(client, "listDevices");
    const { container } = renderRoute({ path: "/queue", client });
    await screen.findByText("mqtt-7f3a");

    const sortBtn = screen.getByRole("button", { name: /AI 分類信心/ });
    sortBtn.click();

    await waitFor(() => {
      expect(spy).toHaveBeenCalledWith({
        status: "candidate",
        sort: "ai_confidence",
        order: "desc",
      });
    });
    expect(container).toBeTruthy();
  });
});
