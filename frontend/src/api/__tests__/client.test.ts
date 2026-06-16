/**
 * api-client stub 測試：
 * - 一律指向同源 BFF（/api，§9.3），URL 組裝對齊 openapi 1.3.0 契約
 * - P1 不接線：預設 fetcher 丟 EmsApiNotWiredError（不靜默）
 * - mock client：回傳不可變副本、語義對齊契約（filter/sort/分頁 bare array）
 */
import { describe, expect, it, vi } from "vitest";
import {
  BFF_BASE_PATH,
  EmsApiNotWiredError,
  buildListDevicesPath,
  buildMeasurementsPath,
  createEmsApiClient,
  createMockEmsApiClient,
} from "@/api/client";

describe("BFF 路徑組裝", () => {
  it("base path 為同源 /api（金鑰僅存於 BFF — §9.1）", () => {
    expect(BFF_BASE_PATH).toBe("/api");
  });

  it("buildListDevicesPath 組出契約 query（status/limit/offset/sort/order）", () => {
    expect(
      buildListDevicesPath({
        status: "candidate",
        limit: 50,
        offset: 0,
        sort: "ai_confidence",
        order: "desc",
      }),
    ).toBe("/api/devices?status=candidate&limit=50&offset=0&sort=ai_confidence&order=desc");
  });

  it("buildListDevicesPath 無參數時為 /api/devices", () => {
    expect(buildListDevicesPath()).toBe("/api/devices");
  });

  it("buildMeasurementsPath 走 per-device facade（device_id 在 path；since/limit/order 在 query）", () => {
    const path = buildMeasurementsPath("sim-001", {
      since: "2026-06-10T00:00:00Z",
      limit: 100,
    });
    expect(path).toContain("/api/devices/sim-001/measurements?");
    expect(path).toContain(`since=${encodeURIComponent("2026-06-10T00:00:00Z")}`);
    expect(path).toContain("limit=100");
    expect(path).toContain("order=desc");
    // device_id 不再以 query 形式出現（已移至 path）
    expect(path).not.toContain("device_id=");
  });

  it("buildMeasurementsPath 無 query 時帶預設 order=desc", () => {
    expect(buildMeasurementsPath("sim-001")).toBe(
      "/api/devices/sim-001/measurements?order=desc",
    );
  });

  it("buildMeasurementsPath device_id 進 path 前先 URL-encode（防 path injection）", () => {
    expect(buildMeasurementsPath("a/../b")).toBe(
      "/api/devices/a%2F..%2Fb/measurements?order=desc",
    );
  });
});

describe("createEmsApiClient（stub，P1 不接線）", () => {
  it("預設 fetcher：呼叫即拒絕 EmsApiNotWiredError（不靜默失敗）", async () => {
    const client = createEmsApiClient();
    await expect(client.listDevices()).rejects.toBeInstanceOf(EmsApiNotWiredError);
  });

  it("注入 fetcher 時以正確 path / method 轉發", async () => {
    const fetcher = vi.fn().mockResolvedValue([]);
    const client = createEmsApiClient(fetcher);
    await client.listDevices({ status: "candidate" });
    expect(fetcher).toHaveBeenCalledWith("/api/devices?status=candidate", undefined);

    await client.confirmDevice("mqtt-7f3a");
    expect(fetcher).toHaveBeenCalledWith(
      "/api/devices/mqtt-7f3a/confirm",
      expect.objectContaining({ method: "POST" }),
    );

    await client.listDeviceMeasurements("sim-001", { limit: 10 });
    expect(fetcher).toHaveBeenCalledWith(
      "/api/devices/sim-001/measurements?limit=10&order=desc",
      undefined,
    );
  });

  it("device_id 進 path 前先 URL-encode（防 path injection）", async () => {
    const fetcher = vi.fn().mockResolvedValue({});
    const client = createEmsApiClient(fetcher);
    await client.getDevice("a/../b");
    expect(fetcher).toHaveBeenCalledWith("/api/devices/a%2F..%2Fb", undefined);
  });
});

describe("createMockEmsApiClient（P1 mock 資料源）", () => {
  it("listDevices 依 status 過濾（AC-1：佇列只含 candidate）", async () => {
    const client = createMockEmsApiClient();
    const candidates = await client.listDevices({ status: "candidate" });
    expect(candidates.length).toBeGreaterThan(0);
    expect(candidates.every((d) => d.status === "candidate")).toBe(true);
  });

  it("listDevices 依 ai_confidence desc 排序且 NULLS LAST（契約語義）", async () => {
    const client = createMockEmsApiClient();
    const all = await client.listDevices({ sort: "ai_confidence", order: "desc" });
    const values = all.map((d) => d.ai_confidence ?? null);
    const nonNull = values.filter((v): v is number => v !== null);
    expect(nonNull).toEqual([...nonNull].sort((a, b) => b - a));
    const firstNull = values.indexOf(null);
    if (firstNull !== -1) {
      expect(values.slice(firstNull).every((v) => v === null)).toBe(true);
    }
  });

  it("回傳為新副本：呼叫端變更不汙染後續呼叫（immutability）", async () => {
    const client = createMockEmsApiClient();
    const first = await client.listDevices();
    first.pop();
    (first[0] as { device_id: string }).device_id = "mutated!";
    const second = await client.listDevices();
    expect(second.length).toBe(first.length + 1);
    expect(second[0]?.device_id).not.toBe("mutated!");
  });

  it("getHumanReview 回傳對應 device 的 digest", async () => {
    const client = createMockEmsApiClient();
    const review = await client.getHumanReview("mqtt-7f3a");
    expect(review.device_id).toBe("mqtt-7f3a");
    expect(review.summary_source).toBeTruthy();
  });

  it("confirmDevice 樂觀回傳 status=confirmed（AC-3）", async () => {
    const client = createMockEmsApiClient();
    const updated = await client.confirmDevice("mqtt-7f3a");
    expect(updated.device_id).toBe("mqtt-7f3a");
    expect(updated.status).toBe("confirmed");
  });

  it("overrideDevice 改 device_type 並記 classified_by=manual_override（AC-3）", async () => {
    const client = createMockEmsApiClient();
    const updated = await client.overrideDevice("mqtt-7f3a", {
      device_type: "pressure_sensor",
      signals: [],
    });
    expect(updated.status).toBe("confirmed");
    expect(updated.device_type).toBe("pressure_sensor");
    expect(updated.classified_by).toBe("manual_override");
  });

  it("rejectDevice 樂觀回傳 status=retired（AC-3）", async () => {
    const client = createMockEmsApiClient();
    const updated = await client.rejectDevice("mqtt-7f3a");
    expect(updated.status).toBe("retired");
  });

  it("mutating 動作對不存在 device 仍回 reject（不靜默）", async () => {
    const client = createMockEmsApiClient();
    await expect(client.confirmDevice("does-not-exist")).rejects.toBeInstanceOf(Error);
  });

  it("listDeviceMeasurements 回對應 device 的量測副本；未知 device 回空陣列", async () => {
    const client = createMockEmsApiClient();
    const m = await client.listDeviceMeasurements("sim-001");
    expect(m.length).toBeGreaterThan(0);
    expect(m.every((row) => row.device_id === "sim-001")).toBe(true);
    expect(await client.listDeviceMeasurements("plc-001")).toEqual([]);
  });
});
