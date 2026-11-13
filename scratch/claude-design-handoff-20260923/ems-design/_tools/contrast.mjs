// Phase-1 token math: WCAG contrast for text/background pairs + OKLCH for chart colours.
// Writes an ASCII-only report to contrast.txt next to this script. Never prints CJK.
import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));

const hexToRgb = (hex) => {
  const h = hex.replace("#", "");
  return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16) / 255);
};
const lin = (c) => (c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4));
const luminance = (hex) => {
  const [r, g, b] = hexToRgb(hex).map(lin);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};
const contrast = (a, b) => {
  const [la, lb] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (la + 0.05) / (lb + 0.05);
};
const oklch = (hex) => {
  const [r, g, b] = hexToRgb(hex).map(lin);
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  const L = 0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s;
  const A = 1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s;
  const B = 0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s;
  const C = Math.sqrt(A * A + B * B);
  let H = (Math.atan2(B, A) * 180) / Math.PI;
  if (H < 0) H += 360;
  return { L, C, H };
};

const [, , pairsArg] = process.argv;
const cfg = JSON.parse(pairsArg ? (await import("node:fs")).readFileSync(pairsArg, "utf8") : "{}");

const lines = [];
lines.push("TEXT / NON-TEXT CONTRAST (need: text 4.5, large>=24px 3.0, marks/borders 3.0)");
for (const p of cfg.pairs ?? []) {
  const ratio = contrast(p.fg, p.bg);
  const need = p.need ?? 4.5;
  const verdict = ratio >= need ? "PASS" : "FAIL";
  lines.push(
    `${verdict}  ${ratio.toFixed(2).padStart(5)}:1  need ${need.toFixed(1)}  fg ${p.fg} on bg ${p.bg}  [${p.id}]`
  );
}
lines.push("");
lines.push("OKLCH (L 0-1, C chroma, H hue deg) - categorical band light 0.43-0.77, chroma floor 0.10");
for (const c of cfg.colors ?? []) {
  const { L, C, H } = oklch(c.hex);
  lines.push(`${c.hex}  L ${L.toFixed(3)}  C ${C.toFixed(3)}  H ${H.toFixed(1).padStart(5)}  [${c.id}]`);
}
writeFileSync(join(here, cfg.out ?? "contrast.txt"), lines.join("\n") + "\n", "ascii");
console.log(`wrote ${lines.length} lines`);
