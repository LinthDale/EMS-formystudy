/**
 * i18n scaffold 測試（FR-531：zh-Hant 在地化）
 */
import { describe, expect, it } from "vitest";
import i18n from "@/i18n";

describe("i18n — zh-Hant", () => {
  it("預設語系為 zh-Hant", () => {
    expect(i18n.language).toBe("zh-Hant");
  });

  it("設備狀態字串完整（FR-503 狀態機 + stale + unknown fallback）", () => {
    expect(i18n.t("device.status.candidate")).toBe("候選");
    expect(i18n.t("device.status.confirmed")).toBe("已確認");
    expect(i18n.t("device.status.active")).toBe("運轉中");
    expect(i18n.t("device.status.retired")).toBe("已退役");
    expect(i18n.t("device.status.unknown")).toBe("未知狀態");
    expect(i18n.t("device.status.stale")).toBe("過時");
  });

  it("支援插值（deviceTable.shown）", () => {
    expect(i18n.t("deviceTable.shown", { shown: 4, total: 6 })).toBe("顯示 4 / 6 台");
  });
});
