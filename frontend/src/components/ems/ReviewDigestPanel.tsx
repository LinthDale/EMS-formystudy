/**
 * ReviewDigestPanel（FR-511）— AI digest 審閱面板。
 *
 * §9.5 [必過]：digest 為 LLM 產出、且寫入端可能被 MQTT payload 注入 →
 * 一律「純文字渲染」：只輸出 React text node，無 innerHTML、無
 * markdown→HTML、無 dangerouslySetInnerHTML。本元件列入 code-review XSS 檢查。
 */
import { useTranslation } from "react-i18next";
import type { DigestOut } from "@/api/types";
import { formatDateTime } from "@/lib/format";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/cn";

export interface DigestRow {
  readonly path: string;
  readonly text: string;
}

const MAX_DEPTH = 4;

function scalarToText(value: unknown): string {
  if (value === null || value === undefined) return "—";
  return String(value);
}

function isScalar(value: unknown): boolean {
  return value === null || typeof value !== "object";
}

/**
 * 純函數：digest JSON → 扁平 {path, text} 列（dot-path）。
 * - 純量陣列以頓號連接；含物件的陣列 / 超深巢狀以 JSON 字串收斂（仍為純文字）
 * - 不改變輸入（immutability）
 */
export function flattenDigest(
  digest: Readonly<Record<string, unknown>>,
  prefix = "",
  depth = 0,
): readonly DigestRow[] {
  return Object.entries(digest).flatMap(([key, value]): readonly DigestRow[] => {
    const path = prefix ? `${prefix}.${key}` : key;
    if (isScalar(value)) {
      return [{ path, text: scalarToText(value) }];
    }
    if (Array.isArray(value)) {
      const text = value.every(isScalar)
        ? value.map(scalarToText).join("、")
        : JSON.stringify(value);
      return [{ path, text }];
    }
    if (depth >= MAX_DEPTH) {
      return [{ path, text: JSON.stringify(value) }];
    }
    return flattenDigest(value as Record<string, unknown>, path, depth + 1);
  });
}

const SOURCE_KEYS = ["llm", "system_fallback"] as const;

function sourceKey(source: string): string {
  return (SOURCE_KEYS as readonly string[]).includes(source) ? source : "unknown";
}

export interface ReviewDigestPanelProps {
  review: DigestOut;
  className?: string;
}

export function ReviewDigestPanel({ review, className }: ReviewDigestPanelProps) {
  const { t } = useTranslation();
  const rows = flattenDigest(review.digest);

  const meta: ReadonlyArray<readonly [string, string | null | undefined]> = [
    [t("review.provider"), review.provider],
    [t("review.model"), review.model],
    [t("review.promptVersion"), review.prompt_version],
    [t("review.generatedAt"), formatDateTime(review.generated_at)],
  ];

  return (
    <Card className={cn("max-w-xl", className)}>
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle>{t("review.title")}</CardTitle>
        <span
          data-source={sourceKey(review.summary_source)}
          className={cn(
            "rounded-full border border-line px-2.5 py-0.5 text-xs font-medium",
            review.summary_source === "llm"
              ? "text-accent border-accent/50"
              : "text-warn border-warn/50",
          )}
        >
          {t(`review.source.${sourceKey(review.summary_source)}`)}
        </span>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs sm:grid-cols-4">
          {meta.map(([label, value]) => (
            <div key={label} className="flex flex-col gap-0.5">
              <dt className="text-fg-muted">{label}</dt>
              {/* 純文字渲染（§9.5）：value 僅作為 text node 輸出 */}
              <dd className="font-mono text-fg-secondary">{value ?? "—"}</dd>
            </div>
          ))}
        </dl>
        <ul className="flex flex-col gap-2 border-t border-line pt-3">
          {rows.map((row) => (
            <li key={row.path} className="flex flex-col gap-0.5 text-sm">
              {/* path 與 text 一律 React text node — 不可改為任何 HTML 注入式渲染 */}
              <span className="font-mono text-xs text-fg-muted">{row.path}</span>
              <span className="break-words whitespace-pre-wrap text-fg">
                {row.text}
              </span>
            </li>
          ))}
        </ul>
        <p className="text-xs text-fg-muted">{t("review.plainTextNote")}</p>
      </CardContent>
    </Card>
  );
}
