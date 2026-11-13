// Round 3: helper tones derived from the site palette (hue held, lightness moved). ASCII -> tokens3.txt.
import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const lin = (c) => (c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4));
const rgbOf = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
const lum = (hex) => {
  const [r, g, b] = rgbOf(hex).map(lin);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};
const contrast = (x, y) => {
  const [p, q] = [lum(x), lum(y)].sort((u, v) => v - u);
  return (p + 0.05) / (q + 0.05);
};
const toHex = (L, C, Hdeg) => {
  const h = (Hdeg * Math.PI) / 180;
  const a = C * Math.cos(h), b = C * Math.sin(h);
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3;
  const rgb = [
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
  ];
  const enc = (c) => {
    const x = Math.min(1, Math.max(0, c));
    return x <= 0.0031308 ? 12.92 * x : 1.055 * Math.pow(x, 1 / 2.4) - 0.055;
  };
  return "#" + rgb.map((c) => Math.round(enc(c) * 255).toString(16).padStart(2, "0")).join("").toLowerCase();
};
const CARD = "#f8f8f7", PAPER = "#f4f4f2", LIT = "#e5ebdc", SAGE = "#e1e7dc";
const rows = [
  ["gold-deep L0.62 (threshold lines)", 0.62, 0.1, 85.4],
  ["gold-deep L0.60", 0.6, 0.1, 85.4],
  ["olive-ink L0.50 (olive text)", 0.5, 0.055, 133.2],
  ["olive-ink L0.48", 0.48, 0.055, 133.2],
  ["danger-tint soft", 0.945, 0.018, 35],
  ["warn-tint check", 0.945, 0.03, 85.6],
  ["p2-tint (gold family)", 0.94, 0.035, 85.4],
];
const out = ["helper tones (hex, contrast on card / paper / lit / sage)"];
for (const [name, L, C, H] of rows) {
  const hex = toHex(L, C, H);
  out.push(`${hex}  card ${contrast(hex, CARD).toFixed(2)}  paper ${contrast(hex, PAPER).toFixed(2)}  lit ${contrast(hex, LIT).toFixed(2)}  sage ${contrast(hex, SAGE).toFixed(2)}  [${name}]`);
}
out.push("");
out.push("text on derived tints");
const tints = { dangerSoft: toHex(0.945, 0.018, 35), p2: toHex(0.94, 0.035, 85.4) };
out.push(`#96493e on ${tints.dangerSoft}: ${contrast("#96493e", tints.dangerSoft).toFixed(2)}`);
out.push(`#282825 on ${tints.p2}: ${contrast("#282825", tints.p2).toFixed(2)}`);
out.push(`#64645e on ${tints.p2}: ${contrast("#64645e", tints.p2).toFixed(2)}`);
out.push(`#cca858 mark on ${tints.p2}: ${contrast("#cca858", tints.p2).toFixed(2)}`);
out.push(`#282825 on #cca858 (callout): ${contrast("#282825", "#cca858").toFixed(2)}`);
out.push(`#f4f4f2 on #1d1e20 (active nav label): ${contrast("#f4f4f2", "#1d1e20").toFixed(2)}`);
out.push(`#cca858 on #2b2d2f (active icon/bar on lifted band): ${contrast("#cca858", "#2b2d2f").toFixed(2)}`);
writeFileSync(join(here, "tokens3.txt"), out.join("\n") + "\n", "ascii");
console.log("ok");
