#!/usr/bin/env node
// css-lint.mjs - tAIstro EMS CSS convention check (dependency-free, Node 18+).
// Run from <root>/css:  node css-lint.mjs > check-css.txt 2>&1
// Exit 0 = pass, 1 = at least one failure. Output is ASCII only.
//
// Enforces:
//  ems-app.css    - no hex / rgb() / hsl() colours, no px font-size, no s / ms durations
//                   (spec), plus: no raw px lengths, every var(--ems-*) defined,
//                   BEGIN/END blocks present and ordered, BEM-style .ems-* class names.
//  ems-tokens.css - sections 00..07 present, every token has a same-line comment,
//                   hex colours only in 00 PALETTE and each defined once,
//                   no duplicate literal inside one token category.
//  coverage       - every hex used in the seven project/*.dc.html artboards is defined in
//                   ems-tokens.css (listed when missing), and every font-size, weight,
//                   letter-spacing, line-height, radius, spacing, stroke, dash, opacity and
//                   font stack used there matches a token of its category.
import { readFileSync, readdirSync, existsSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const TOKENS = join(HERE, 'ems-tokens.css');
const APP = join(HERE, 'ems-app.css');
const PROJECT = join(HERE, '..', 'project');
const ARTBOARDS = ['Main', 'Monitor', 'Demand', 'Storage', 'Alarms', 'Devices', 'Reports'].map((n) => n + '.dc.html');
const BLOCKS = ['BASE', 'SHELL', 'CARDS', 'KPI', 'CHARTS', 'TABLES', 'CONTROLS', 'STATUS', 'UTILITIES'];

let failures = 0;
const out = [];
const esc = (s) => String(s).replace(/[^\x20-\x7e]/g, (c) => '\\u' + c.codePointAt(0).toString(16).padStart(4, '0'));
const ok = (m) => out.push('  ok   ' + esc(m));
const fail = (m) => { failures++; out.push('  FAIL ' + esc(m)); };
const info = (m) => out.push('  info ' + esc(m));
const stripComments = (css) => css.replace(/\/\*[\s\S]*?\*\//g, (c) => c.replace(/[^\n]/g, ' '));
const lineNo = (text, idx) => text.slice(0, idx).split('\n').length;
const HEX = /#[0-9a-fA-F]{3,8}\b/g;

for (const f of [TOKENS, APP]) {
  if (!existsSync(f)) { console.log('FAIL missing ' + f); process.exit(1); }
}
const tokensSrc = readFileSync(TOKENS, 'utf8');
const appSrc = readFileSync(APP, 'utf8');

// ---------------------------------------------------------------- tokens
out.push('css-lint - tAIstro EMS');
out.push('');
out.push('== ems-tokens.css');
const sections = [...tokensSrc.matchAll(/-{5,}\s*(0[0-7])\s+([A-Z][A-Z /]+)/g)].map((m) => m[1]);
const wantSections = ['00', '01', '02', '03', '04', '05', '06', '07'];
if (JSON.stringify(sections) === JSON.stringify(wantSections)) ok('numbered sections 00..07 present and in order');
else fail('numbered sections found: ' + sections.join(',') + ' (need 00..07 in order)');

const tokenLines = tokensSrc.split('\n');
const defs = new Map();
let section = '';
let inOverride = false;
let depth = 0;
let commentless = 0;
const hexWhere = new Map();
tokenLines.forEach((line, i) => {
  const sec = /-{5,}\s*(0[0-7])\s/.exec(line);
  if (sec) section = sec[1];
  if (/@media|:root\[/.test(line)) inOverride = true;
  const m = /^\s*(--ems-[a-z0-9-]+)\s*:\s*([^;]+);(.*)$/.exec(line);
  if (m) {
    const [, name, value, rest] = m;
    if (!/\/\*.+\*\//.test(rest)) { commentless++; fail(`line ${i + 1}: ${name} has no same-line comment`); }
    if (!inOverride && !defs.has(name)) defs.set(name, { value: value.trim(), line: i + 1, section });
    for (const h of value.matchAll(HEX)) {
      const hx = h[0].toLowerCase();
      if (section !== '00') fail(`line ${i + 1}: hex ${hx} outside 00 PALETTE`);
      hexWhere.set(hx, (hexWhere.get(hx) || []).concat(i + 1));
    }
  }
  depth += (line.match(/\{/g) || []).length - (line.match(/\}/g) || []).length;
  if (inOverride && depth <= 0) inOverride = false;
});
if (!commentless) ok(`${defs.size} tokens, each declaration carries a same-line comment`);
const dupHex = [...hexWhere.entries()].filter(([, lines]) => lines.length > 1);
if (dupHex.length) dupHex.forEach(([h, lines]) => fail(`hex ${h} defined ${lines.length} times (lines ${lines.join(', ')})`));
else ok(`hex colours only in 00 PALETTE, each defined exactly once (${hexWhere.size})`);

// resolve var() chains
const resolve = (value, seen = new Set()) => value.replace(/var\(\s*(--[a-z0-9-]+)\s*(?:,\s*([^()]*))?\)/g, (all, name, fallback) => {
  if (seen.has(name)) return all;
  const d = defs.get(name);
  if (!d) return fallback !== undefined ? fallback.trim() : all;
  return resolve(d.value, new Set([...seen, name]));
});
// duplicate literal inside a category (category = first segment after --ems-)
const byCat = new Map();
for (const [name, d] of defs) {
  if (/var\(/.test(d.value)) continue;
  const cat = name.slice(6).split('-')[0];
  const key = cat + '|' + d.value.toLowerCase().replace(/\s+/g, ' ');
  byCat.set(key, (byCat.get(key) || []).concat(name));
}
const dupLit = [...byCat.entries()].filter(([, names]) => names.length > 1);
if (dupLit.length) dupLit.forEach(([k, names]) => fail(`duplicate literal ${k.split('|')[1]} in category ${k.split('|')[0]}: ${names.join(', ')}`));
else ok('no duplicate literal inside any token category');

// ---------------------------------------------------------------- app
out.push('');
out.push('== ems-app.css');
const app = stripComments(appSrc);
const hexApp = [...app.matchAll(HEX)];
if (hexApp.length) hexApp.forEach((h) => fail(`hex colour ${h[0]} at line ${lineNo(app, h.index)}`)); else ok('no hex colour literals');
const fnApp = [...app.matchAll(/\b(rgba?|hsla?)\s*\(/gi)];
if (fnApp.length) fnApp.forEach((h) => fail(`${h[1]}() literal at line ${lineNo(app, h.index)}`)); else ok('no rgb() / hsl() literals');
const pxFont = [...app.matchAll(/font(?:-size)?\s*:[^;{}]*\d+(?:\.\d+)?px/gi)];
if (pxFont.length) pxFont.forEach((h) => fail(`px font-size at line ${lineNo(app, h.index)}`)); else ok('no px font-size');
const dur = [...app.matchAll(/(?<![\w-])\d*\.?\d+(?:ms|s)\b/g)];
if (dur.length) dur.forEach((h) => fail(`duration literal ${h[0]} at line ${lineNo(app, h.index)}`)); else ok('no s / ms duration literals');
const px = [...app.matchAll(/(?<![\w-])\d*\.?\d+px\b/g)];
if (px.length) px.forEach((h) => fail(`raw px length ${h[0]} at line ${lineNo(app, h.index)} (use a token)`)); else ok('no raw px lengths (tokens only)');

const marks = [...appSrc.matchAll(/\/\* =+ (BEGIN|END) ([A-Z]+) =+ \*\//g)].map((m) => m[1] + ' ' + m[2]);
const wantMarks = BLOCKS.flatMap((b) => ['BEGIN ' + b, 'END ' + b]);
if (JSON.stringify(marks) === JSON.stringify(wantMarks)) ok(`${BLOCKS.length} BEGIN/END blocks paired and in order: ${BLOCKS.join(' ')}`);
else fail('block markers are ' + marks.join(' | ') + ' (need BEGIN/END for ' + BLOCKS.join(', ') + ' in order)');
const outside = appSrc.split(/\/\* =+ END [A-Z]+ =+ \*\//).slice(1).map((chunk) => stripComments(chunk.split(/\/\* =+ BEGIN [A-Z]+ =+ \*\//)[0]).trim()).filter(Boolean);
if (outside.length) fail('rules found outside BEGIN/END blocks'); else ok('every rule sits inside a block');

const classNames = new Set([...app.replace(/\{[^{}]*\}/g, '{}').matchAll(/\.([A-Za-z_][\w-]*)/g)].map((m) => m[1]));
const BEM = /^ems-[a-z0-9]+(?:-[a-z0-9]+)*(?:__[a-z0-9]+(?:-[a-z0-9]+)*)?(?:--[a-z0-9]+(?:-[a-z0-9]+)*)?$/;
const badNames = [...classNames].filter((c) => !BEM.test(c));
if (badNames.length) badNames.forEach((c) => fail('class name breaks .ems-block__element--modifier: .' + c)); else ok(`${classNames.size} class names follow .ems-block__element--modifier`);

const refs = [...app.matchAll(/var\(\s*(--[a-z0-9-]+)/g)].map((m) => m[1]);
const undef = [...new Set(refs)].filter((r) => !defs.has(r));
if (undef.length) undef.forEach((r) => fail('var() references an undefined token: ' + r)); else ok(`every var() resolves to ems-tokens.css (${refs.length} references, ${new Set(refs).size} distinct)`);
const unusedInfo = [...defs.keys()].filter((n) => !refs.includes(n) && ![...defs.values()].some((d) => d.value.includes(n + ')') || d.value.includes(n + ',')));
info(`${unusedInfo.length} tokens are not referenced by ems-app.css (artboard mirrors or App-only)`);

// ---------------------------------------------------------------- coverage
out.push('');
out.push('== coverage: seven artboards vs ems-tokens.css');
const tokenValues = (prefix) => new Set([...defs.entries()].filter(([n]) => n.startsWith(prefix)).map(([, d]) => resolve(d.value).toLowerCase().replace(/\s+/g, ' ').trim()));
const normNum = (v) => String(parseFloat(v));
const famNorm = (v) => v.toLowerCase().replace(/["']/g, '').split(',').map((s) => s.trim()).filter(Boolean).join(',');
const artboardHex = new Map();
const used = { size: new Map(), weight: new Map(), tracking: new Map(), leading: new Map(), radius: new Map(), space: new Map(), stroke: new Map(), dash: new Map(), opacity: new Map(), family: new Map() };
const note = (cat, v, file) => { const m = used[cat]; if (!m.has(v)) m.set(v, new Set()); m.get(v).add(file.replace('.dc.html', '')); };
for (const file of ARTBOARDS) {
  const p = join(PROJECT, file);
  if (!existsSync(p)) { fail('missing artboard ' + file); continue; }
  const src = readFileSync(p, 'utf8');
  for (const h of src.matchAll(HEX)) {
    const hx = h[0].toLowerCase();
    if (!artboardHex.has(hx)) artboardHex.set(hx, new Set());
    artboardHex.get(hx).add(file.replace('.dc.html', ''));
  }
  const blocks = [...src.matchAll(/\sstyle="([^"]*)"/g)].map((m) => m[1]);
  const helmet = /<helmet>[\s\S]*?<style>([\s\S]*?)<\/style>/.exec(src);
  if (helmet) blocks.push(...[...helmet[1].matchAll(/\{([^}]*)\}/g)].map((m) => m[1]));
  for (const b of blocks) {
    for (const decl of b.split(';')) {
      const i = decl.indexOf(':');
      if (i < 0) continue;
      const prop = decl.slice(0, i).trim().toLowerCase();
      const val = decl.slice(i + 1).trim();
      if (!val || val.includes('{{')) continue;
      if (prop === 'font-size') note('size', val.toLowerCase(), file);
      else if (prop === 'font-weight') note('weight', val, file);
      else if (prop === 'letter-spacing') note('tracking', val.toLowerCase(), file);
      else if (prop === 'line-height') note('leading', normNum(val), file);
      else if (prop === 'border-radius') note('radius', val.toLowerCase(), file);
      else if (['gap', 'row-gap', 'column-gap'].includes(prop) || prop.startsWith('padding')) {
        val.split(/\s+/).filter((x) => x !== '0').forEach((x) => note('space', x.toLowerCase(), file));
      } else if (prop === 'stroke-width') note('stroke', val.toLowerCase(), file);
      else if (prop === 'stroke-dasharray') note('dash', val.replace(/\s+/g, ' '), file);
      else if (['opacity', 'fill-opacity', 'stop-opacity'].includes(prop)) note('opacity', normNum(val), file);
      else if (prop === 'font-family' && val !== 'inherit') note('family', famNorm(val), file);
    }
  }
}
const tokenHex = new Set(hexWhere.keys());
const missingHex = [...artboardHex.keys()].filter((h) => !tokenHex.has(h)).sort();
if (missingHex.length) missingHex.forEach((h) => fail(`artboard hex ${h} not defined in ems-tokens.css (used in ${[...artboardHex.get(h)].join(', ')})`));
else ok(`hex: ${artboardHex.size} distinct in artboards, all defined (tokens define ${tokenHex.size})`);
const tokenOnlyHex = [...tokenHex].filter((h) => !artboardHex.has(h));
if (tokenOnlyHex.length) info('hex defined in tokens but not used on the artboards: ' + tokenOnlyHex.join(', '));

const checks = [
  ['size', 'font-size', '--ems-font-size-', (v) => v],
  ['weight', 'font-weight', '--ems-weight-', (v) => v],
  ['tracking', 'letter-spacing', '--ems-tracking-', (v) => v],
  ['leading', 'line-height', '--ems-leading-', (v) => normNum(v)],
  ['radius', 'border-radius', '--ems-radius-', (v) => v],
  ['space', 'gap / padding', '--ems-space-', (v) => v],
  ['stroke', 'stroke-width', '--ems-stroke-', (v) => v],
  ['dash', 'stroke-dasharray', '--ems-dash-', (v) => v],
  ['opacity', 'opacity', '--ems-opacity-', (v) => normNum(v)],
  ['family', 'font-family', '--ems-font-', (v) => famNorm(v)]
];
for (const [cat, label, prefix, norm] of checks) {
  const have = new Set([...tokenValues(prefix)].map(norm));
  const missing = [...used[cat].keys()].filter((v) => !have.has(v));
  if (missing.length) missing.forEach((v) => fail(`${label} ${v} used in ${[...used[cat].get(v)].join(', ')} has no ${prefix}* token`));
  else ok(`${label}: ${used[cat].size} distinct values in artboards, all tokenised`);
}

out.push('');
out.push(`RESULT: ${failures ? 'FAIL' : 'PASS'} (${failures} failure${failures === 1 ? '' : 's'})`);
console.log(out.join('\n'));
process.exit(failures ? 1 : 0);
