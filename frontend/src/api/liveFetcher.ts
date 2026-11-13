/**
 * Live Fetcher（PRD-0005 Phase-1 Wave 2）— 真正接線同源 BFF。
 *
 * - **Same-origin `/api`**：path 原樣傳遞，瀏覽器不直連 device-service / PostgREST
 *   （§9.3 零 CORS 面）。bundle 內零金鑰（金鑰只在 BFF 伺服器側，§9.1）。
 * - **`credentials:"include"`**：攜帶 `HttpOnly; Secure; SameSite=Strict` session
 *   cookie（§9.2）；BFF 每請求驗 session 後才注入 key。
 * - **CSRF（§9.4）**：靠 SameSite=Strict cookie + BFF 端 Origin allowlist。瀏覽器
 *   對 same-origin 請求「自動」帶 Origin header；前端「絕不」手動設 Origin
 *   （Origin 為 forbidden header，手設無效且語義錯誤）。故此處不加任何 token、
 *   不碰 Origin header。
 * - **錯誤映射**：401→needs-login、403→forbidden、其他 4xx→帶後端 detail、
 *   5xx/502→generic（不外洩後端細節）；fetch reject（網路層）→ generic status=0。
 */
import type { Fetcher } from "./client";

/** API 錯誤基底：保留 HTTP status，供 UI / 守衛分流。 */
export class EmsApiError extends Error {
  readonly status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "EmsApiError";
    this.status = status;
  }
}

/** 401：session 不存在 / 過期 — 需（重新）登入。守衛據此導向 /login。 */
export class EmsNeedsLoginError extends EmsApiError {
  constructor(status = 401, message = "需要登入") {
    super(status, message);
    this.name = "EmsNeedsLoginError";
  }
}

/** 403：已登入但 role 無權此端點（§9.1 endpoint 級授權）。 */
export class EmsForbiddenError extends EmsApiError {
  constructor(status = 403, message = "無權限執行此操作") {
    super(status, message);
    this.name = "EmsForbiddenError";
  }
}

/** 5xx / 502 / 網路層：通用故障（不外洩後端細節）；UI 顯示可重試。 */
export class EmsServerError extends EmsApiError {
  constructor(status: number, message = "伺服器暫時無法處理，請稍後再試") {
    super(status, message);
    this.name = "EmsServerError";
  }
}

/** 後端錯誤 envelope（FastAPI/Starlette 慣例為 { detail }）。 */
interface ErrorBody {
  readonly detail?: unknown;
}

/** 安全解析 JSON body；非 JSON / 空 body 一律回 null（不丟例外）。 */
async function readJsonSafe(response: Response): Promise<unknown> {
  if (response.status === 204) return null;
  const text = await response.text();
  if (text.length === 0) return null;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return null;
  }
}

/** 從後端 body 取人類可讀 detail（僅 4xx 透出；5xx 一律 generic）。 */
function detailMessage(body: unknown, fallback: string): string {
  const detail = (body as ErrorBody | null)?.detail;
  if (typeof detail === "string" && detail.length > 0) return detail;
  return fallback;
}

function mapError(status: number, body: unknown): EmsApiError {
  if (status === 401) return new EmsNeedsLoginError(status);
  if (status === 403) {
    return new EmsForbiddenError(status, detailMessage(body, "無權限執行此操作"));
  }
  if (status >= 500) {
    // 不外洩後端 detail（可能含 stacktrace / 上游細節）。
    return new EmsServerError(status);
  }
  // 其他 4xx：透出後端 detail（例：422 欄位驗證訊息），供 UI 對應。
  return new EmsApiError(status, detailMessage(body, `請求失敗（HTTP ${status}）`));
}

/**
 * 建立 live fetcher。注入 `createEmsApiClient(liveFetcher)` 即得真實 client。
 *
 * 可選 `fetchImpl` 僅為測試 / SSR 注入；正式執行用全域 `fetch`。
 */
export function createLiveFetcher(
  fetchImpl: typeof fetch = (...args) => fetch(...args),
): Fetcher {
  return async (path, init) => {
    let response: Response;
    try {
      response = await fetchImpl(path, {
        ...init,
        // 攜帶 session cookie（§9.2）；不覆寫呼叫端 headers / body。
        credentials: "include",
      });
    } catch {
      // 網路層失敗（DNS / 連線中斷 / CORS 阻擋）：status=0，generic 可重試。
      throw new EmsServerError(0);
    }

    if (response.ok) {
      return readJsonSafe(response);
    }

    const body = await readJsonSafe(response);
    throw mapError(response.status, body);
  };
}
