/**
 * ReviewPage（FR-511/512）測試：digest 渲染 + confirm / override / reject 動作（樂觀更新 AC-3）
 * + 失敗錯誤態（AC-5）。
 */
import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderRoute } from "@/test/render-route";
import { createMockEmsApiClient } from "@/api/client";

describe("ReviewPage", () => {
  it("渲染 AI 審閱 digest（FR-511，純文字）", async () => {
    renderRoute({ path: "/queue/mqtt-7f3a" });
    // ReviewDigestPanel 標題 + rationale 文字（純文字渲染）
    expect(await screen.findByText("AI 審閱摘要")).toBeInTheDocument();
    expect(screen.getByText(/Topic 階層含 temp/)).toBeInTheDocument();
  });

  it("confirm 呼叫 client 並顯示成功結果（AC-3）", async () => {
    const user = userEvent.setup();
    const client = createMockEmsApiClient();
    const spy = vi.spyOn(client, "confirmDevice");
    renderRoute({ path: "/queue/mqtt-7f3a", client });
    await screen.findByText("AI 審閱摘要");

    await user.click(screen.getByRole("button", { name: "確認分類" }));

    expect(spy).toHaveBeenCalledWith("mqtt-7f3a");
    expect(await screen.findByText(/已確認：mqtt-7f3a/)).toBeInTheDocument();
  });

  it("reject 呼叫 client 並顯示退役結果（AC-3）", async () => {
    const user = userEvent.setup();
    const client = createMockEmsApiClient();
    const spy = vi.spyOn(client, "rejectDevice");
    renderRoute({ path: "/queue/mqtt-7f3a", client });
    await screen.findByText("AI 審閱摘要");

    await user.click(screen.getByRole("button", { name: "拒絕（退役）" }));

    expect(spy).toHaveBeenCalledWith("mqtt-7f3a");
    expect(await screen.findByText(/已拒絕：mqtt-7f3a/)).toBeInTheDocument();
  });

  it("override 表單送出 device_type 並顯示結果（AC-3）", async () => {
    const user = userEvent.setup();
    const client = createMockEmsApiClient();
    const spy = vi.spyOn(client, "overrideDevice");
    renderRoute({ path: "/queue/mqtt-7f3a", client });
    await screen.findByText("AI 審閱摘要");

    await user.click(screen.getByRole("button", { name: "覆寫分類" }));
    await user.type(
      screen.getByRole("textbox", { name: "正確的設備類型" }),
      "pressure_sensor",
    );
    await user.click(screen.getByRole("button", { name: "送出覆寫" }));

    expect(spy).toHaveBeenCalledWith("mqtt-7f3a", {
      device_type: "pressure_sensor",
      signals: [],
    });
    expect(await screen.findByText(/已覆寫：mqtt-7f3a/)).toBeInTheDocument();
  });

  it("動作失敗顯示明確錯誤訊息（AC-5）", async () => {
    const user = userEvent.setup();
    const client = createMockEmsApiClient();
    vi.spyOn(client, "confirmDevice").mockRejectedValue(new Error("boom"));
    renderRoute({ path: "/queue/mqtt-7f3a", client });
    await screen.findByText("AI 審閱摘要");

    await user.click(screen.getByRole("button", { name: "確認分類" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("動作失敗，請重試");
  });
});
