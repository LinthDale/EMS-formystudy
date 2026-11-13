// Search for brand-faithful categorical steps (PV olive, Grid gold, BESS slot 3) that clear the
// dataviz hard gates (CVD >= 8 target, normal-vision >= 15) on the warm card surface.
// ASCII-only report -> palette_search.txt. Nothing is printed except a line count.
import { writeFileSync } from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const VALIDATOR =
  "C:/Users/User/AppData/Local/Temp/claude/bundled-skills/2.1.280/76735e127e4ef637c4ddcecb5719d623/dataviz/scripts/validate_palette.js";
const { validate } = await import(pathToFileURL(VALIDATOR).href);

const SURFACE = "#FAF8F3";
const REF = { olive: "#7B8340", gold: "#B98A3C", slot3: "#4A4843" };

const toHex = (L, C, Hdeg) => {
  const h = (Hdeg * Math.PI) / 180;
  const a = C * Math.cos(h), b = C * Math.sin(h);
  const l_ = L + 0.3963377774 * a + 0.2158037573 * b;
  const m_ = L - 0.1055613458 * a - 0.0638541728 * b;
  const s_ = L - 0.0894841775 * a - 1.291485548 * b;
  const [l, m, s] = [l_ ** 3, m_ ** 3, s_ ** 3];
  const rgb = [
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
  ];
  if (rgb.some((c) => c < -0.0005 || c > 1.0005)) return null;
  const enc = (c) => {
    const x = Math.min(1, Math.max(0, c));
    return x <= 0.0031308 ? 12.92 * x : 1.055 * Math.pow(x, 1 / 2.4) - 0.055;
  };
  return "#" + rgb.map((c) => Math.round(enc(c) * 255).toString(16).padStart(2, "0")).join("").toUpperCase();
};
const lin = (c) => (c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4));
const rgbOf = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
const oklab = (hex) => {
  const [r, g, b] = rgbOf(hex).map(lin);
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  return [
    0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s,
    1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
    0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s,
  ];
};
const dist = (h1, h2) => {
  const [a, b] = [oklab(h1), oklab(h2)];
  return 100 * Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
};
const lum = (hex) => {
  const [r, g, b] = rgbOf(hex).map(lin);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};
const contrast = (x, y) => {
  const [p, q] = [lum(x), lum(y)].sort((u, v) => v - u);
  return (p + 0.05) / (q + 0.05);
};
const num = (s) => {
  const m = /\u0394E ([\d.]+)/.exec(s);
  return m ? parseFloat(m[1]) : NaN;
};

const range = (a, b, st) => {
  const out = [];
  for (let x = a; x <= b + 1e-9; x += st) out.push(+x.toFixed(3));
  return out;
};

const olives = [];
for (const H of [110, 114, 118]) for (const L of range(0.44, 0.64, 0.02)) for (const C of [0.1, 0.105, 0.11, 0.12]) {
  const hex = toHex(L, C, H);
  if (hex) olives.push({ hex, L, C, H });
}
const golds = [];
for (const H of [70, 74, 78]) for (const L of range(0.62, 0.8, 0.02)) for (const C of [0.1, 0.11, 0.12, 0.13]) {
  const hex = toHex(L, C, H);
  if (hex) golds.push({ hex, L, C, H });
}
const slot3Options = {
  "a charcoal (neutral, chroma-floor exempt)": { H: 90, Cs: [0.008, 0.012], Ls: range(0.43, 0.47, 0.01), exempt: true },
  "b umber": { H: 58, Cs: [0.1], Ls: range(0.4, 0.5, 0.02), exempt: false },
  "c slate-teal": { H: 215, Cs: [0.1], Ls: range(0.44, 0.56, 0.02), exempt: false },
  "d aubergine": { H: 350, Cs: [0.1], Ls: range(0.44, 0.56, 0.02), exempt: false },
};

const lines = [];
lines.push(`surface ${SURFACE}; gates: CVD worst >= 8 (target), normal >= 15 (hard), band 0.43-0.77`);
lines.push(`reference: olive ${REF.olive} gold ${REF.gold} charcoal ${REF.slot3}`);
lines.push("");

for (const [name, opt] of Object.entries(slot3Options)) {
  const s3 = [];
  for (const L of opt.Ls) for (const C of opt.Cs) {
    const hex = toHex(L, C, opt.H);
    if (hex) s3.push({ hex, L, C });
  }
  const results = [];
  for (const o of olives) for (const g of golds) {
    if (dist(o.hex, g.hex) < 15) continue;
    for (const t of s3) {
      const pal = [o.hex, g.hex, t.hex];
      const { report } = validate(pal, { mode: "light", surface: SURFACE, pairs: "all" });
      const get = (k) => report.find((r) => r[0] === k);
      const band = get("Lightness band")[1] === true;
      const chromaOk = get("Chroma floor")[1] === true;
      const cvd = num(get("CVD separation")[2]);
      const nor = num(get("Normal-vision floor")[2]);
      if (!band || cvd < 8 || nor < 15) continue;
      if (!chromaOk && !opt.exempt) continue;
      const score = dist(o.hex, REF.olive) + dist(g.hex, REF.gold) + (opt.exempt ? dist(t.hex, REF.slot3) : 0);
      results.push({ pal, cvd, nor, score, cO: contrast(o.hex, SURFACE), cG: contrast(g.hex, SURFACE), cT: contrast(t.hex, SURFACE), o, g, t });
    }
  }
  results.sort((x, y) => x.score - y.score);
  lines.push(`== slot 3 option ${name}: ${results.length} passing palettes; top 6 by closeness to reference`);
  for (const r of results.slice(0, 6)) {
    lines.push(
      `  PV ${r.pal[0]} (L${r.o.L} C${r.o.C} H${r.o.H}, ${r.cO.toFixed(2)}:1) | GRID ${r.pal[1]} (L${r.g.L} C${r.g.C} H${r.g.H}, ${r.cG.toFixed(2)}:1) | BESS ${r.pal[2]} (L${r.t.L} C${r.t.C}, ${r.cT.toFixed(2)}:1) | cvd ${r.cvd} normal ${r.nor} | dist ${r.score.toFixed(1)}`
    );
  }
  lines.push("");
}
writeFileSync(join(here, "palette_search.txt"), lines.join("\n") + "\n", "ascii");
console.log(`wrote ${lines.length} lines`);
