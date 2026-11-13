// Build the sequential olive ramp (heatmap) from OKLCH steps; write hexes + contrast to ramp.txt (ASCII).
import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const SURFACE = "#FAF8F3";
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
  return "#" + rgb.map((c) => Math.round(enc(c) * 255).toString(16).padStart(2, "0")).join("").toUpperCase();
};
const lin = (c) => (c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4));
const lum = (hex) => {
  const [r, g, b] = [1, 3, 5].map((i) => lin(parseInt(hex.slice(i, i + 2), 16) / 255));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};
const contrast = (x, y) => {
  const [p, q] = [lum(x), lum(y)].sort((u, v) => v - u);
  return (p + 0.05) / (q + 0.05);
};
const steps = [
  [100, 0.93, 0.035], [200, 0.86, 0.055], [300, 0.78, 0.075], [400, 0.7, 0.09],
  [500, 0.62, 0.1], [600, 0.54, 0.1], [700, 0.46, 0.09],
];
const out = ["sequential olive ramp, H 118 (step L C hex contrast-on-card)"];
const hexes = [];
for (const [n, L, C] of steps) {
  const hex = toHex(L, C, 118);
  hexes.push(hex);
  out.push(`${n}  L${L}  C${C}  ${hex}  ${contrast(hex, SURFACE).toFixed(2)}:1`);
}
out.push("");
out.push("csv:" + hexes.join(","));
writeFileSync(join(here, "ramp.txt"), out.join("\n") + "\n", "ascii");
console.log("ok");
