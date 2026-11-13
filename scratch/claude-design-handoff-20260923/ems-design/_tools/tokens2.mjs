// Round 2 (synaiq-web tokens): OKLCH of site hexes, derived warn/danger families, chart-set validation,
// text contrast on the site surfaces. ASCII-only report -> tokens2.txt. Prints nothing but "ok".
import { writeFileSync } from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const VALIDATOR =
  "C:/Users/User/AppData/Local/Temp/claude/bundled-skills/2.1.280/76735e127e4ef637c4ddcecb5719d623/dataviz/scripts/validate_palette.js";
const { validate } = await import(pathToFileURL(VALIDATOR).href);

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
const oklch = (hex) => {
  const [r, g, b] = rgbOf(hex).map(lin);
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  const L = 0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s;
  const A = 1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s;
  const B = 0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s;
  let H = (Math.atan2(B, A) * 180) / Math.PI;
  if (H < 0) H += 360;
  return [L, Math.hypot(A, B), H];
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
const f = (n, d = 3) => n.toFixed(d);
const ascii = (s) => s.replace(/\u0394/g, "d").replace(/\u2194/g, "<->").replace(/[^\x20-\x7e]/g, "-");

const CARD = "#f8f8f7", PAPER = "#f4f4f2";
const out = [];

out.push("== SITE HEXES: OKLCH + contrast on card #f8f8f7 / paper #f4f4f2");
const site = {
  ink: "#282825", muted: "#64645e", inverse: "#c4c4be", lightInk: "#d2d8ca", paper: PAPER, paperLight: CARD,
  warmPaper: "#f2f0e8", warmPaper2: "#e8e5da", sage: "#e1e7dc", sage2: "#e9ece4", lit: "#e5ebdc",
  dark: "#292a2e", sidebar: "#1d1e20", slate: "#34383a", olive: "#647956", oliveEd: "#667655", oliveBar: "#64754f",
  olivePen: "#637859", gold: "#cca858", kwUnder: "#a9bc99", markUnder: "#529a6a", kpiGreen: "#345e40",
  success: "#426d4b", rowRule: "#b4b4ac", film: "#d5d5ce", tableHead: "#e9e9e3", cardBorder: "#afafa0",
};
for (const [k, v] of Object.entries(site)) {
  const [L, C, H] = oklch(v);
  out.push(`${v}  L ${f(L)} C ${f(C)} H ${f(H, 1).padStart(5)}  card ${f(contrast(v, CARD), 2)}  paper ${f(contrast(v, PAPER), 2)}  [${k}]`);
}

out.push("");
out.push("== DERIVED STATUS FAMILIES (hue moved, L/C held near olive L0.54 / gold C0.11)");
const derived = [
  ["warn-mark", 0.6, 0.105, 75], ["warn-text", 0.52, 0.095, 72], ["warn-tint", 0.945, 0.03, 85],
  ["danger-mark", 0.54, 0.11, 32], ["danger-text", 0.5, 0.105, 30], ["danger-tint", 0.94, 0.025, 30],
  ["good-tint(site lit)", -1, 0, 0], ["info-tint", 0.93, 0.008, 100],
];
const dhex = {};
for (const [name, L, C, H] of derived) {
  if (L < 0) continue;
  const hex = toHex(L, C, H);
  dhex[name] = hex;
  const [l2, c2, h2] = oklch(hex);
  out.push(`${hex}  L ${f(l2)} C ${f(c2)} H ${f(h2, 1).padStart(5)}  card ${f(contrast(hex, CARD), 2)}  paper ${f(contrast(hex, PAPER), 2)}  [${name}]`);
}

out.push("");
out.push("== TEXT / MARK CONTRAST (need text 4.5, large>=24px 3.0, marks 3.0)");
const pairs = [
  ["ink on card", site.ink, CARD, 4.5], ["ink on lit", site.ink, site.lit, 4.5],
  ["muted on card", site.muted, CARD, 4.5], ["muted on paper", site.muted, PAPER, 4.5],
  ["muted on lit", site.muted, site.lit, 4.5], ["muted on sage", site.muted, site.sage, 4.5],
  ["muted on table head", site.muted, site.tableHead, 4.5], ["muted on warm paper2", site.muted, site.warmPaper2, 4.5],
  ["kpi green on card", site.kpiGreen, CARD, 4.5], ["kpi green on paper", site.kpiGreen, PAPER, 4.5],
  ["success on lit", site.success, site.lit, 4.5], ["success on card", site.success, CARD, 4.5],
  ["olive text on card", site.olive, CARD, 4.5], ["olive pen text on card", site.olivePen, CARD, 4.5],
  ["olive text on sage", site.olive, site.sage, 4.5],
  ["gold wordmark on header dark", site.gold, site.dark, 4.5], ["gold on sidebar", site.gold, site.sidebar, 4.5],
  ["inverse on header", site.inverse, site.dark, 4.5], ["inverse on sidebar", site.inverse, site.sidebar, 4.5],
  ["light-ink on sidebar", site.lightInk, site.sidebar, 4.5], ["paper on ink button", PAPER, site.ink, 4.5],
  ["paper on sidebar active band #2b2d2f", PAPER, "#2b2d2f", 4.5],
  ["gold mark on card (bar/marker)", site.gold, CARD, 3.0], ["olive mark on card", site.olive, CARD, 3.0],
  ["slate mark on card", site.slate, CARD, 3.0], ["row rule on card (info)", site.rowRule, CARD, 1.0],
  ["film line on card (info)", site.film, CARD, 1.0], ["card border #afafa0 on paper (non-text)", site.cardBorder, PAPER, 3.0],
  ["warn-text on card", dhex["warn-text"], CARD, 4.5], ["warn-text on warn-tint", dhex["warn-text"], dhex["warn-tint"], 4.5],
  ["warn-mark on card", dhex["warn-mark"], CARD, 3.0],
  ["danger-text on card", dhex["danger-text"], CARD, 4.5], ["danger-text on danger-tint", dhex["danger-text"], dhex["danger-tint"], 4.5],
  ["danger-mark on card", dhex["danger-mark"], CARD, 3.0],
  ["ink on warn-tint", site.ink, dhex["warn-tint"], 4.5], ["ink on danger-tint", site.ink, dhex["danger-tint"], 4.5],
  ["muted on info-tint", site.muted, dhex["info-tint"], 4.5],
  ["card text on danger-mark (P0 chip fill)", CARD, dhex["danger-mark"], 4.5],
  ["card text on olive (filled olive)", CARD, site.olive, 4.5],
  ["ink on gold (label inside gold segment)", site.ink, site.gold, 4.5],
  ["card text on slate (label inside slate)", CARD, site.slate, 4.5],
];
for (const [id, fg, bg, need] of pairs) {
  const r = contrast(fg, bg);
  out.push(`${r >= need ? "PASS" : "FAIL"}  ${f(r, 2).padStart(5)}:1 need ${need}  ${fg} on ${bg}  [${id}]`);
}

out.push("");
out.push("== CHART SETS (validator, light, surface card #f8f8f7, pairs all) - slots only from documented site hexes");
const sets = {
  "S1 olive/gold/slate": ["#647956", "#cca858", "#34383a"],
  "S2 markUnder/gold/slate": ["#529a6a", "#cca858", "#34383a"],
  "S3 olive/gold/muted": ["#647956", "#cca858", "#64645e"],
  "S4 kpiGreen/gold/slate": ["#345e40", "#cca858", "#34383a"],
  "S5 olive/gold/ink": ["#647956", "#cca858", "#282825"],
  "S6 olive/gold/slate + other rowRule": ["#647956", "#cca858", "#34383a", "#b4b4ac"],
};
for (const [name, pal] of Object.entries(sets)) {
  const { report, ok } = validate(pal, { mode: "light", surface: CARD, pairs: "all" });
  out.push(`${name}: ${pal.join(",")}  overall ${ok ? "PASS" : "FAIL"}`);
  for (const [n, st, d] of report) out.push(`    ${String(st).padEnd(6)} ${n}: ${ascii(d)}`);
}

out.push("");
out.push("== SEQUENTIAL OLIVE RAMP (heatmap), hue of site olive, L 0.95 -> 0.40");
const [, , hOl] = oklch(site.olive);
const ramp = [[100, 0.95, 0.02], [200, 0.88, 0.035], [300, 0.8, 0.05], [400, 0.72, 0.06], [500, 0.63, 0.065], [600, 0.54, 0.06], [700, 0.45, 0.055]];
for (const [n, L, C] of ramp) {
  const hex = toHex(L, C, hOl);
  out.push(`${n}  ${hex}  L ${L} C ${C}  card ${f(contrast(hex, CARD), 2)}`);
}
out.push("");
out.push("== TOU ORDINAL TINTS (gold hue), off / mid / peak backgrounds + ink-label contrast");
const [, , hGo] = oklch(site.gold);
for (const [n, L, C] of [["off", 0.965, 0.012], ["mid", 0.925, 0.035], ["peak", 0.865, 0.06]]) {
  const hex = toHex(L, C, hGo);
  out.push(`${n}  ${hex}  ink ${f(contrast(site.ink, hex), 2)}  muted ${f(contrast(site.muted, hex), 2)}`);
}
writeFileSync(join(here, "tokens2.txt"), out.join("\n") + "\n", "ascii");
console.log("ok");
