/**
 * App shell 煙霧測試（Wave 1）：landmark（banner/nav/main）+ 品牌字串 zh-Hant
 * + 預設路由（/ → /devices，FR-500 設備清單）。
 *
 * 以 memory router（renderRoute helper）驗證 shell + 預設重導；createBrowserRouter
 * 的整合佈線見 src/app/router.tsx（appRoutes 由 helper 共用，等價驗證）。
 */
import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { renderRoute } from "@/test/render-route";

describe("App shell", () => {
  it("渲染 banner / nav / main landmark 與品牌字串（a11y FR-532）", async () => {
    renderRoute({ path: "/" });
    expect(screen.getByRole("banner")).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "主導覽" })).toBeInTheDocument();
    expect(screen.getByRole("main")).toBeInTheDocument();
    expect(screen.getByText("SynaIQ EMS")).toBeInTheDocument();
    expect(screen.getByText("能源管理平台")).toBeInTheDocument();
    // 預設路由重導至設備清單（FR-500）
    expect(
      await screen.findByRole("heading", { name: "設備清單" }),
    ).toBeInTheDocument();
  });
});
