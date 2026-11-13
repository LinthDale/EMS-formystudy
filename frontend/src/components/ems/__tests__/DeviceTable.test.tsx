/**
 * DeviceTable（FR-500）：分頁/排序設備清單。
 * §8.1.1：bare array + limit/offset → P1 採 infinite-scroll（載入更多）模式；
 * 排序語義對齊後端 allowlist：NULLS LAST、次序鍵 device_id。
 */
import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DeviceTable } from "@/components/ems/DeviceTable";
import { sortDevices } from "@/lib/device-sort";
import { MOCK_DEVICES } from "@/api/fixtures";

function rowIds(): string[] {
  return screen
    .getAllByRole("row")
    .slice(1) // skip header row
    .map((r) => within(r).getAllByRole("cell")[0]?.textContent ?? "");
}

describe("sortDevices（純函數，對齊後端排序語義）", () => {
  it("asc：null 信心值一律排最後（NULLS LAST）", () => {
    const sorted = sortDevices(MOCK_DEVICES, "ai_confidence", "asc");
    const values = sorted.map((d) => d.ai_confidence ?? null);
    const firstNull = values.indexOf(null);
    expect(firstNull).toBeGreaterThan(0);
    expect(values.slice(firstNull).every((v) => v === null)).toBe(true);
  });

  it("desc：最高信心在前，null 仍最後", () => {
    const sorted = sortDevices(MOCK_DEVICES, "ai_confidence", "desc");
    expect(sorted[0]?.device_id).toBe("plc-001"); // 0.93
    expect(sorted[sorted.length - 1]?.ai_confidence ?? null).toBeNull();
  });

  it("回傳新陣列、不改變輸入（immutability）", () => {
    const snapshot = MOCK_DEVICES.map((d) => d.device_id);
    const sorted = sortDevices(MOCK_DEVICES, "device_id", "desc");
    expect(sorted).not.toBe(MOCK_DEVICES);
    expect(MOCK_DEVICES.map((d) => d.device_id)).toEqual(snapshot);
  });
});

describe("DeviceTable", () => {
  it("渲染表格、caption 與每台設備的狀態徽章/信心量表", () => {
    render(<DeviceTable devices={[...MOCK_DEVICES]} pageSize={25} />);
    expect(screen.getByRole("table", { name: "設備清單" })).toBeInTheDocument();
    expect(rowIds()).toHaveLength(MOCK_DEVICES.length);
    // 狀態徽章存在（含 unknown 收斂）
    const pills = screen.getAllByRole("status");
    expect(pills.length).toBe(MOCK_DEVICES.length);
  });

  it("分頁（§8.1.1 載入更多）：先顯示 pageSize 筆，按鈕載入其餘", async () => {
    const user = userEvent.setup();
    render(<DeviceTable devices={[...MOCK_DEVICES]} pageSize={4} />);
    expect(rowIds()).toHaveLength(4);
    expect(screen.getByText("顯示 4 / 6 台")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "載入更多" }));
    expect(rowIds()).toHaveLength(6);
    expect(screen.queryByRole("button", { name: "載入更多" })).toBeNull();
  });

  it("點擊欄頭排序：第一次 asc、再點 desc，aria-sort 跟著更新", async () => {
    const user = userEvent.setup();
    render(<DeviceTable devices={[...MOCK_DEVICES]} pageSize={25} />);
    const header = screen.getByRole("button", { name: /AI 信心/ });

    await user.click(header); // asc
    let ids = rowIds();
    expect(ids[0]).toBe("edge-x1"); // 0.18 最低
    expect(ids[ids.length - 1]).toBe("sim-001"); // null → NULLS LAST
    expect(
      screen.getByRole("columnheader", { name: /AI 信心/ }),
    ).toHaveAttribute("aria-sort", "ascending");

    await user.click(header); // desc
    ids = rowIds();
    expect(ids[0]).toBe("plc-001"); // 0.93 最高
    expect(ids[ids.length - 1]).toBe("sim-001"); // null 仍最後
    expect(
      screen.getByRole("columnheader", { name: /AI 信心/ }),
    ).toHaveAttribute("aria-sort", "descending");
  });

  it("空清單 → 明確 empty state（AC-1）", () => {
    render(<DeviceTable devices={[]} />);
    expect(screen.getByText("目前沒有符合條件的設備")).toBeInTheDocument();
  });

  it("stale 設備在狀態欄帶過時標記（FR-503）", () => {
    render(<DeviceTable devices={[...MOCK_DEVICES]} pageSize={25} />);
    const staleRow = screen
      .getAllByRole("row")
      .find((r) => within(r).queryByText("legacy-pm-02"));
    expect(staleRow).toBeDefined();
    expect(within(staleRow as HTMLElement).getByRole("status")).toHaveAttribute(
      "data-stale",
      "true",
    );
  });
});
