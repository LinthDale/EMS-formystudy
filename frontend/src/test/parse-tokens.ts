/**
 * 測試 helper：把 tokens.css 解析成 name→value map。
 * 用途：驗證「tokens.css 是唯一視覺真相」——theme.ts 等消費端的輸出
 * 必須能直接對回本檔解析值（不經 jsdom CSS cascade，避免 jsdom 限制）。
 * 註：vitest `css:false` 會把 `?raw` CSS import 變空字串，故以 node:fs 讀檔。
 * 路徑解析：jsdom 環境下 import.meta.url 為 http: scheme，不能 fileURLToPath；
 * 以 vitest 的 cwd（frontend 專案根）解析實體路徑。
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

export const tokensCss: string = readFileSync(
  resolve(process.cwd(), "src/styles/tokens.css"),
  "utf-8",
);

export function parseTokens(css: string = tokensCss): ReadonlyMap<string, string> {
  const map = new Map<string, string>();
  const re = /(--ems-[\w-]+)\s*:\s*([^;]+);/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(css)) !== null) {
    map.set(m[1], m[2].trim().replace(/\s+/g, " "));
  }
  return map;
}

/** 把解析出的 token map 包成 charts/theme.ts 可用的 TokenReader */
export function tokenReaderFromCss(css?: string): (name: string) => string {
  const tokens = parseTokens(css);
  return (name: string) => tokens.get(name) ?? "";
}
