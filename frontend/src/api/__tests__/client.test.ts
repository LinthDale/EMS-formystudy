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

  it("buildMeasurementsPath 以 PostgREST 運算子組 query（device_id=eq. / time=gte.）", () => {
    const path = buildMeasurementsPath("electricity", {
      deviceId: "sim-001",
      since: "2026-06-10T00:00:00Z",
      limit: 100,
    });
    expect(path).toContain("/api/measurements/electricity?");
    expect(path).toContain("device_id=eq.sim-001");
    expect(path).toContain(`time=gte.${encodeURIComponent("2026-06-10T00:00:00Z")}`);
    expect(path).toContain("order=time.desc");
    expect(path).toContain("limit=100");
  });

  it("factory 域走 /api/measurements/factory", () => {
    expect(buildMeasurementsPath("factory", {})).toBe(
      "/api/measurements/factory?order=time.desc",
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
});
