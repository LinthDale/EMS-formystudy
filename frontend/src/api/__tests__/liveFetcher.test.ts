/**
 * Live Fetcher 測試（PRD-0005 §9.3 / §9.1 / §9.2）。
 *
 * 驗證：
 * - 一律 same-origin `/api`（無金鑰、無手動 Origin header）；cookie 走 credentials:include
 * - JSON 解析（含 204 / 空 body）
 * - 錯誤映射：401→needs-login、403→forbidden、4xx→訊息、5xx/502→generic
 *
 * §9.4：CSRF 由 SameSite=Strict cookie + BFF Origin allowlist 把關；瀏覽器
 * 對 same-origin 請求「自動」帶 Origin header。前端「絕不」手動設 Origin
 * （手設會被 forbidden header 規則忽略，且語義錯誤）——下方斷言即守此不變量。
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  EmsApiError,
  EmsForbiddenError,
  EmsNeedsLoginError,
  EmsServerError,
  createLiveFetcher,
} from "@/api/liveFetcher";

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
    ...init,
  });
}

/** 行使 fetcher 並回傳被丟出的 EmsApiError（型別收斂，供後續斷言 .status/.message）。 */
async function caught(p: Promise<unknown>): Promise<EmsApiError> {
  try {
    await p;
    throw new Error("expected fetcher to reject, but it resolved");
  } catch (e) {
    return e as EmsApiError;
  }
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("createLiveFetcher — request shape (§9.1/§9.2/§9.3)", () => {
  it("以 credentials:'include' 送出（攜帶 BFF session cookie）", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(jsonResponse([]));
    const fetcher = createLiveFetcher();
    await fetcher("/api/devices");
    const init = fetchSpy.mock.calls[0]?.[1] as RequestInit;
    expect(init.credentials).toBe("include");
  });

  it("path 原樣傳遞（same-origin /api，瀏覽器不直連後端）", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(jsonResponse([]));
    const fetcher = createLiveFetcher();
    await fetcher("/api/devices?status=candidate");
    expect(fetchSpy.mock.calls[0]?.[0]).toBe("/api/devices?status=candidate");
  });

  it("絕不手動設定 Origin header（CSRF 靠瀏覽器自動 Origin + SameSite cookie — §9.4）", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(jsonResponse([]));
    const fetcher = createLiveFetcher();
    await fetcher("/api/devices/x/confirm", { method: "POST" });
    const init = fetchSpy.mock.calls[0]?.[1] as RequestInit;
    const headers = new Headers(init.headers);
    expect(headers.has("origin")).toBe(false);
  });

  it("透傳呼叫端的 method / headers / body（per-device facade query 也照常帶上）", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(jsonResponse({}));
    const fetcher = createLiveFetcher();
    await fetcher("/api/devices/x/measurements?order=asc", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ a: 1 }),
    });
    expect(fetchSpy.mock.calls[0]?.[0]).toBe(
      "/api/devices/x/measurements?order=asc",
    );
    const init = fetchSpy.mock.calls[0]?.[1] as RequestInit;
    expect(init.method).toBe("POST");
    expect(init.body).toBe(JSON.stringify({ a: 1 }));
  });
});

describe("createLiveFetcher — success parsing", () => {
  it("回傳 JSON 解析後的 body", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse([{ device_id: "a" }]),
    );
    const fetcher = createLiveFetcher();
    await expect(fetcher("/api/devices")).resolves.toEqual([
      { device_id: "a" },
    ]);
  });

  it("204 No Content（如 logout）回傳 null，不嘗試解析空 body", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(null, { status: 204 }),
    );
    const fetcher = createLiveFetcher();
    await expect(fetcher("/api/auth/logout", { method: "POST" })).resolves.toBe(
      null,
    );
  });

  it("200 但空 body 也回傳 null（不丟 JSON parse 例外）", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("", { status: 200 }),
    );
    const fetcher = createLiveFetcher();
    await expect(fetcher("/api/devices")).resolves.toBe(null);
  });
});

describe("createLiveFetcher — error mapping (§9 降級不白屏)", () => {
  it("401 → EmsNeedsLoginError（需重新登入）", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ detail: "invalid or expired session" }, { status: 401 }),
    );
    const fetcher = createLiveFetcher();
    const err = await caught(fetcher("/api/devices"));
    expect(err).toBeInstanceOf(EmsNeedsLoginError);
    expect(err).toBeInstanceOf(EmsApiError);
    expect(err.status).toBe(401);
  });

  it("403 → EmsForbiddenError（無權）", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ detail: "role not permitted for this endpoint" }, { status: 403 }),
    );
    const fetcher = createLiveFetcher();
    const err = await caught(fetcher("/api/devices"));
    expect(err).toBeInstanceOf(EmsForbiddenError);
    expect(err.status).toBe(403);
  });

  it("其他 4xx → EmsApiError，帶後端 detail 訊息", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ detail: "limit must be 1..500" }, { status: 422 }),
    );
    const fetcher = createLiveFetcher();
    const err = await caught(fetcher("/api/devices?limit=9999"));
    expect(err).toBeInstanceOf(EmsApiError);
    expect(err).not.toBeInstanceOf(EmsServerError);
    expect(err.status).toBe(422);
    expect(err.message).toContain("limit must be 1..500");
  });

  it("4xx 但非 JSON body 仍給通用訊息（不丟 parse 例外）", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("<html>bad</html>", {
        status: 400,
        headers: { "Content-Type": "text/html" },
      }),
    );
    const fetcher = createLiveFetcher();
    const err = await caught(fetcher("/api/devices"));
    expect(err).toBeInstanceOf(EmsApiError);
    expect(err.status).toBe(400);
    expect(typeof err.message).toBe("string");
    expect(err.message.length).toBeGreaterThan(0);
  });

  it("5xx → EmsServerError（generic，不外洩後端細節）", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ detail: "stacktrace leak" }, { status: 500 }),
    );
    const fetcher = createLiveFetcher();
    const err = await caught(fetcher("/api/devices"));
    expect(err).toBeInstanceOf(EmsServerError);
    expect(err.status).toBe(500);
    expect(err.message).not.toContain("stacktrace leak");
  });

  it("502 Bad Gateway（上游故障）→ EmsServerError（generic）", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("upstream down", { status: 502 }),
    );
    const fetcher = createLiveFetcher();
    const err = await caught(fetcher("/api/devices"));
    expect(err).toBeInstanceOf(EmsServerError);
    expect(err.status).toBe(502);
  });

  it("網路層失敗（fetch reject）→ EmsServerError（status=0，可重試）", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("Failed to fetch"));
    const fetcher = createLiveFetcher();
    const err = await caught(fetcher("/api/devices"));
    expect(err).toBeInstanceOf(EmsServerError);
    expect(err.status).toBe(0);
  });
});
