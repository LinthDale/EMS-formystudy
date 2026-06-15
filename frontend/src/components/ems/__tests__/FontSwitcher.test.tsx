/**
 * FontSwitcher 測試（PRD-0005 §6.4：可調整字體控制）。
 * - 由註冊表 driven（可擴充：選項數 = registry 中可選 sans 數）。
 * - 選擇即改 documentElement --ems-font-sans + 持久化 localStorage。
 * - a11y：原生 <select> 有 label，鍵盤可達。
 */
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FontSwitcher } from "@/components/ems/FontSwitcher";
import { FONT_PREF_STORAGE_KEY } from "@/lib/font-preference";
import { DEFAULT_SANS_FONT_ID, getFont, sansFonts } from "@/styles/fonts";

beforeEach(() => {
  localStorage.clear();
  document.documentElement.style.removeProperty("--ems-font-sans");
});
afterEach(() => {
  localStorage.clear();
  document.documentElement.style.removeProperty("--ems-font-sans");
});

describe("FontSwitcher（可調整字體）", () => {
  it("以可存取的下拉選單呈現（a11y label）", () => {
    render(<FontSwitcher />);
    expect(screen.getByRole("combobox", { name: /字體/ })).toBeInTheDocument();
  });

  it("選項由註冊表 driven（可選 sans 字體全列出）", () => {
    render(<FontSwitcher />);
    const options = screen.getAllByRole("option");
    expect(options.length).toBe(sansFonts().length);
    for (const f of sansFonts()) {
      expect(
        options.some((o) => (o as HTMLOptionElement).value === f.id),
        `下拉缺少字體選項 ${f.id}`,
      ).toBe(true);
    }
  });

  it("切換字體即改 --ems-font-sans 並持久化", async () => {
    const user = userEvent.setup();
    render(<FontSwitcher />);
    const select = screen.getByRole("combobox", { name: /字體/ });
    await user.selectOptions(select, "space-grotesk");

    expect(localStorage.getItem(FONT_PREF_STORAGE_KEY)).toBe("space-grotesk");
    expect(
      document.documentElement.style.getPropertyValue("--ems-font-sans"),
    ).toBe(getFont("space-grotesk")!.stack.join(", "));
  });

  it("初始選中反映已持久化的偏好", () => {
    localStorage.setItem(FONT_PREF_STORAGE_KEY, "space-grotesk");
    render(<FontSwitcher />);
    const select = screen.getByRole("combobox", {
      name: /字體/,
    }) as HTMLSelectElement;
    expect(select.value).toBe("space-grotesk");
  });

  it("無偏好時預設選中 DEFAULT_SANS_FONT_ID", () => {
    render(<FontSwitcher />);
    const select = screen.getByRole("combobox", {
      name: /字體/,
    }) as HTMLSelectElement;
    expect(select.value).toBe(DEFAULT_SANS_FONT_ID);
  });
});
