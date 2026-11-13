// Nudge PV olive chroma above the 0.10 floor while holding L/H; re-validate with gold + charcoal.
import { writeFileSync } from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const VALIDATOR =
  "C:/Users/User/AppData/Local/Temp/claude/bundled-skills/2.1.280/76735e127e4ef637c4ddcecb5719d623/dataviz/scripts/validate_palette.js";
const { validate } = await import(pathToFileURL(VALIDATOR).href);
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
const ascii = (s) => s.replace(/\u0394/g, "dE").replace(/\u2194/g, "<->").replace(/[^\x20-\x7e]/g, "-");
const out = [];
for (const [L, C] of [[0.56, 0.105], [0.56, 0.11], [0.57, 0.105], [0.55, 0.11]]) {
  const olive = toHex(L, C, 118);
  for (const gold of ["#C78A3B", "#CB8E3E"]) {
    const pal = [olive, gold, "#51504B"];
    const { report } = validate(pal, { mode: "light", surface: "#FAF8F3", pairs: "all" });
    out.push(`olive L${L} C${C} -> ${pal.join(",")}`);
    for (const [name, state, detail] of report) out.push(`   ${String(state).padEnd(6)} ${name}: ${ascii(detail)}`);
  }
}
writeFileSync(join(here, "olive_nudge.txt"), out.join("\n") + "\n", "ascii");
console.log("ok");
