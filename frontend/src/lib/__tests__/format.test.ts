import { describe, expect, it } from "vitest";
import {
  formatDateTime,
  formatMeasurementValue,
  formatPercent01,
} from "@/lib/format";

describe("formatMeasurementValue", () => {
  it("依 digits 取小數位", () => {
    expect(formatMeasurementValue(58.71)).toBe("58.7");
    expect(formatMeasurementValue(1500, 0)).toBe("1500");
  });
  it("null / undefined / NaN → em-dash", () => {
    expect(formatMeasurementValue(null)).toBe("—");
    expect(formatMeasurementValue(undefined)).toBe("—");
    expect(formatMeasurementValue(Number.NaN)).toBe("—");
  });
});

describe("formatDateTime", () => {
  it("ISO → zh-Hant 在地化字串", () => {
    const out = formatDateTime("2026-06-11T02:59:30Z");
    expect(out).toContain("2026");
    expect(out).not.toBe("—");
  });
  it("無效輸入容錯為 em-dash（不丟例外）", () => {
    expect(formatDateTime(null)).toBe("—");
    expect(formatDateTime("not-a-date")).toBe("—");
  });
});

describe("formatPercent01", () => {
  it("0–1 → 整數百分比", () => {
    expect(formatPercent01(0.42)).toBe("42%");
    expect(formatPercent01(1)).toBe("100%");
  });
});
