// Inventory of literal style values used in the seven artboards (for ems-tokens.css). ASCII -> inventory.txt.
import { readFileSync, writeFileSync, readdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const PROJ = join(here, '..', 'project');
const ABBR = { 'Main.dc.html': 'Ma', 'Monitor.dc.html': 'Mo', 'Demand.dc.html': 'De', 'Storage.dc.html': 'St', 'Alarms.dc.html': 'Al', 'Devices.dc.html': 'Dv', 'Reports.dc.html': 'Re' };
const files = readdirSync(PROJ).filter((f) => f.endsWith('.dc.html'));
const esc = (s) => String(s).replace(/[^\x20-\x7e]/g, (c) => '\\u' + c.codePointAt(0).toString(16).padStart(4, '0'));
const cats = {
  hex: /#[0-9a-fA-F]{3,8}\b/g,
  'font-size': /font-size:\s*([\d.]+px)/g,
  'font-weight': /font-weight:\s*(\d+)/g,
  'letter-spacing': /letter-spacing:\s*(-?[\d.]+em)/g,
  'line-height': /line-height:\s*([\d.]+)\s*[;"]/g,
  'font-family': /font-family:\s*([^;"]+)/g,
  'border-radius': /border-radius:\s*([^;"]+)/g,
  gap: /(?:[\s;"])(?:gap|row-gap|column-gap):\s*([^;"]+)/g,
  padding: /padding(?:-left|-right|-top|-bottom)?:\s*([^;"]+)/g,
  'box-shadow': /box-shadow:\s*([^;"{}]+)/g,
  'stroke-width': /stroke-width:\s*([^;"]+)/g,
  'stroke-dasharray': /stroke-dasharray:\s*([^;"]+)/g,
  opacity: /(?:[\s;"])((?:fill-|stop-)?opacity):\s*([^;"]+)/g,
  border: /(?:[\s;"])(border(?:-left|-right|-top|-bottom)?(?:-width)?):\s*([^;"]+)/g,
  transform: /transform:\s*(rotate\([^)]*\))/g,
  'js-css-string': /'((?:inset )?-?\d[\d.]*px [^']*#[0-9a-fA-F]{3,8}|0 1px 2px #[0-9a-fA-F]+|none|transparent)'/g,
  height: /(?:[\s;"])height:\s*(\d+px)/g,
  width: /(?:[\s;"])width:\s*(\d+px)/g
};
const out = [];
for (const [cat, re] of Object.entries(cats)) {
  const map = new Map();
  for (const f of files) {
    const src = readFileSync(join(PROJ, f), 'utf8');
    for (const m of src.matchAll(re)) {
      const v = (m.length > 2 && m[2] !== undefined ? m[1] + ': ' + m[2] : (m[1] !== undefined ? m[1] : m[0])).trim().toLowerCase();
      if (!map.has(v)) map.set(v, new Map());
      const per = map.get(v);
      per.set(ABBR[f], (per.get(ABBR[f]) || 0) + 1);
    }
  }
  out.push(`== ${cat}: ${map.size} distinct`);
  [...map.entries()].sort((a, b) => a[0].localeCompare(b[0], 'en', { numeric: true })).forEach(([v, per]) => {
    const total = [...per.values()].reduce((a, b) => a + b, 0);
    out.push(`  ${esc(v).padEnd(58)} x${String(total).padEnd(4)} ${[...per.entries()].map(([k, n]) => k + n).join(' ')}`);
  });
  out.push('');
}
writeFileSync(join(here, 'inventory.txt'), out.join('\n') + '\n', 'ascii');
console.log('ok');
