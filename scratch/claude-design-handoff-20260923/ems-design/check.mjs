// Static self-check for the tAIstro EMS canvas. Reads project/*.dc.html + project/canvas.json,
// writes an ASCII-only report to check.txt next to this file. Never renders, never prints CJK.
import { readFileSync, writeFileSync, readdirSync, existsSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = dirname(fileURLToPath(import.meta.url));
const PROJ = join(ROOT, 'project');
const LOGO_SRC = join(ROOT, '..', 'taistro-logo', 'taistro-01.svg');
const lines = [];
let errors = 0;
let warns = 0;
const esc = (s) => String(s).replace(/[^\x20-\x7e]/g, (c) => '\\u' + c.codePointAt(0).toString(16).padStart(4, '0'));
const fail = (f, m) => { errors++; lines.push(`  FAIL [${f}] ${esc(m)}`); };
const warn = (f, m) => { warns++; lines.push(`  WARN [${f}] ${esc(m)}`); };
const pass = (f, m) => lines.push(`  ok   [${f}] ${esc(m)}`);
const lineOf = (src, idx) => src.slice(0, idx).split('\n').length;

// ---------- canvas.json ----------
lines.push('== canvas.json');
let canvas = null;
try {
  canvas = JSON.parse(readFileSync(join(PROJ, 'canvas.json'), 'utf8'));
  pass('canvas.json', 'JSON.parse');
} catch (e) {
  fail('canvas.json', 'JSON.parse failed: ' + e.message);
}
const files = readdirSync(PROJ).filter((f) => f.endsWith('.dc.html')).sort();
let boards = {};
if (canvas) {
  ['v', 'createdOnFiles', 'title', 'launch', 'pages', 'boards', 'order', 'notes', 'designSystems'].forEach((k) => {
    if (!(k in canvas)) fail('canvas.json', 'missing key ' + k);
  });
  if (canvas.v !== 3) fail('canvas.json', 'v must be 3');
  const at = canvas.createdOnFiles && canvas.createdOnFiles.at;
  if (!canvas.createdOnFiles || canvas.createdOnFiles.v !== 1 || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$/.test(at || '')) {
    fail('canvas.json', 'createdOnFiles must be {v:1, at:RFC3339}');
  } else pass('canvas.json', 'createdOnFiles ' + at);
  if (!canvas.launch || canvas.launch.view !== 'canvas') fail('canvas.json', 'launch.view must be canvas');
  boards = canvas.boards || {};
  const keys = Object.keys(boards).sort();
  if (JSON.stringify(keys) !== JSON.stringify(files)) fail('canvas.json', 'boards keys differ from project files: ' + keys.join(',') + ' vs ' + files.join(','));
  else pass('canvas.json', 'boards match files (' + files.length + ')');
  if (JSON.stringify([...(canvas.order || [])].sort()) !== JSON.stringify(keys)) fail('canvas.json', 'order differs from boards');
  if ((canvas.order || [])[0] !== 'Main.dc.html') fail('canvas.json', 'first artboard must be Main.dc.html');
  if (!boards['Main.dc.html'] || boards['Main.dc.html'].x !== 0 || boards['Main.dc.html'].y !== 0) fail('canvas.json', 'Main.dc.html must sit at 0,0');
  keys.forEach((k) => {
    const b = boards[k];
    if (![b.x, b.y, b.w, b.h].every(Number.isInteger)) fail(k, 'x/y/w/h must be integers');
    if (b.w < 40 || b.w > 8000 || b.h < 40 || b.h > 8000) fail(k, 'w/h outside 40..8000');
    if (b.is_interactive !== true) fail(k, 'is_interactive must be true (sidebar links)');
  });
  // rows: 80 px between frames, 120 px between rows
  const rowsY = [...new Set(keys.map((k) => boards[k].y))].sort((a, b) => a - b);
  const rows = rowsY.map((y) => keys.filter((k) => boards[k].y === y).sort((a, b) => boards[a].x - boards[b].x));
  rows.forEach((row, ri) => {
    for (let i = 0; i + 1 < row.length; i++) {
      const a = boards[row[i]], b = boards[row[i + 1]];
      const gap = b.x - (a.x + a.w);
      if (gap !== 80) fail('canvas.json', `row ${ri + 1}: gap ${gap} px between ${row[i]} and ${row[i + 1]} (need 80)`);
    }
    if (ri > 0) {
      const prevBottom = Math.max(...rows[ri - 1].map((k) => boards[k].y + boards[k].h));
      const gap = rowsY[ri] - prevBottom;
      if (gap !== 120) fail('canvas.json', `row ${ri + 1}: ${gap} px below row ${ri} (need 120)`);
      else pass('canvas.json', `row ${ri + 1}: 120 px below row ${ri}`);
    }
    pass('canvas.json', `row ${ri + 1}: ${row.length} boards, 80 px spacing checked`);
  });
  // title1 notes: one per row, >= 223 px above it, over no frame and off the name strips
  const notes = canvas.notes || {};
  const titleRows = new Map();
  Object.entries(notes).forEach(([id, n]) => {
    if (n.kind !== 'title1') return;
    const ry = rowsY.find((y) => y > n.y);
    if (ry === undefined) { fail('canvas.json', `note ${id} is below every row`); return; }
    titleRows.set(ry, (titleRows.get(ry) || 0) + 1);
    if (ry - n.y < 223) fail('canvas.json', `note ${id} is ${ry - n.y} px above its row (need >= 223)`);
    else pass('canvas.json', `note ${id}: ${ry - n.y} px above row at y ${ry}`);
    const nr = { x0: n.x, x1: n.x + (n.maxW || 1000), y0: n.y, y1: n.y + 90 };
    keys.forEach((k) => {
      const b = boards[k];
      const strip = { x0: b.x, x1: b.x + b.w, y0: b.y - 40, y1: b.y + b.h };
      if (nr.x0 < strip.x1 && nr.x1 > strip.x0 && nr.y0 < strip.y1 && nr.y1 > strip.y0) fail('canvas.json', `note ${id} overlaps ${k} or its name strip`);
    });
  });
  rowsY.forEach((y, i) => { if ((titleRows.get(y) || 0) !== 1) fail('canvas.json', `row ${i + 1} has ${titleRows.get(y) || 0} title1 notes (need 1)`); });
}

// ---------- logo reference (second <g> of taistro-01.svg, all class cls-2 except the box rect) ----------
const logo = [];
if (existsSync(LOGO_SRC)) {
  const svg = readFileSync(LOGO_SRC, 'utf8');
  const re = /<(path|rect|circle|polygon)\s+class="cls-2"\s+([^>]*?)\/>/g;
  let m;
  while ((m = re.exec(svg))) {
    const [, tag, attrs] = m;
    if (tag === 'rect' && /x="130\.6"/.test(attrs)) continue;
    logo.push(`<${tag} fill="#cca858" ${attrs.trim()}>`);
  }
}

// ---------- artboards ----------
const VOID = new Set(['area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'source', 'track', 'wbr']);
const HOLE_OK = /^\s*(\$?[A-Za-z_][\w$]*(\.[A-Za-z_$][\w$]*)*|true|false|-?\d+(\.\d+)?)\s*$/;
const EMOJI = (cp) => (cp >= 0x1f000 && cp <= 0x1faff) || (cp >= 0x2600 && cp <= 0x27bf) || (cp >= 0x2b00 && cp <= 0x2bff) || cp === 0xfe0f || cp === 0x200d || (cp >= 0xe000 && cp <= 0xf8ff);
const summary = [];

files.forEach((file) => {
  const src = readFileSync(join(PROJ, file), 'utf8');
  const before = errors;
  lines.push('');
  lines.push('== ' + file);
  const b = boards[file] || {};
  const lineCount = src.split('\n').length;

  // head
  if (!/^<!doctype html>/i.test(src)) fail(file, 'must start with <!doctype html>');
  if (!src.includes('<html lang="zh-Hant">')) fail(file, 'html lang must be zh-Hant');
  if (!src.includes('<meta charset="utf-8">')) fail(file, 'missing meta charset utf-8');
  const title = /<title>([^<]+)<\/title>/.exec(src);
  if (!title || !title[1].trim()) fail(file, 'missing <title>');
  const sup = src.split('<script src="./support.js"></script>').length - 1;
  if (sup !== 1) fail(file, `support.js line found ${sup} times (need exactly 1)`); else pass(file, 'support.js line exact x1');

  // x-dc + helmet
  const xOpen = src.indexOf('<x-dc>'), xClose = src.indexOf('</x-dc>');
  if (xOpen < 0 || xClose < 0 || src.indexOf('<x-dc>', xOpen + 1) > 0) { fail(file, 'need exactly one <x-dc>...</x-dc>'); return; }
  const xdc = src.slice(xOpen + 6, xClose);
  const helm = /<helmet>([\s\S]*?)<\/helmet>/.exec(xdc);
  if (!helm) fail(file, 'missing <helmet>');
  else {
    const h = helm[1];
    const links = h.match(/<link\b[^>]*>/g) || [];
    if (links.length !== 1 || !/href="https:\/\/fonts\.googleapis\.com\/css2\?/.test(links[0])) fail(file, 'helmet must hold exactly one Google Fonts css2 link');
    const styles = h.match(/<style>([\s\S]*?)<\/style>/g) || [];
    if (styles.length !== 1) fail(file, 'helmet must hold exactly one <style>');
    else {
      const sels = [...styles[0].replace(/<\/?style>/g, '').matchAll(/([^{}]+)\{/g)].map((x) => x[1].trim());
      const bad = sels.filter((s) => !['body', 'a', 'a:hover'].includes(s));
      if (bad.length) fail(file, 'helmet style has extra selectors: ' + bad.join(' | ')); else pass(file, 'helmet = font link + body/a/a:hover only');
    }
    const rest = h.replace(/<link\b[^>]*>/g, '').replace(/<style>[\s\S]*?<\/style>/g, '').trim();
    if (rest) fail(file, 'helmet holds other content');
  }
  const afterHelmet = xdc.slice(xdc.indexOf('</helmet>') + 9);
  const rootM = /^\s*<div style="width: (\d+)px; height: (\d+)px;/.exec(afterHelmet);
  if (!rootM) fail(file, 'root element must be <div style="width: Wpx; height: Hpx; ...">');
  else if (+rootM[1] !== b.w || +rootM[2] !== b.h) fail(file, `root ${rootM[1]}x${rootM[2]} != board ${b.w}x${b.h}`);
  else pass(file, `root ${rootM[1]}x${rootM[2]} = board`);
  if ((xdc.match(/<style\b/g) || []).length !== 1) fail(file, '<style> only allowed once, inside helmet');

  // data-props + logic
  const dp = /<script type="text\/x-dc" data-dc-script data-props='([^']*)'>([\s\S]*?)<\/script>/.exec(src);
  if (!dp) fail(file, 'missing <script type="text/x-dc" data-dc-script data-props=...>');
  else {
    let props = null;
    try {
      props = JSON.parse(dp[1].replace(/&#39;/g, "'").replace(/&quot;/g, '"').replace(/&amp;/g, '&'));
      pass(file, 'data-props JSON.parse (' + Object.keys(props).join(',') + ')');
    } catch (e) { fail(file, 'data-props JSON.parse failed: ' + e.message); }
    if (props) {
      const pv = props.$preview || {};
      if (pv.width !== b.w || pv.height !== b.h) fail(file, `$preview ${pv.width}x${pv.height} != board ${b.w}x${b.h}`); else pass(file, '$preview = board');
      Object.entries(props).forEach(([k, v]) => { if (k !== '$preview' && !('editor' in v)) fail(file, 'prop ' + k + ' lacks an editor'); });
    }
    const js = dp[2];
    if (!/class Component extends DCLogic\s*\{/.test(js) || !/renderVals\s*\(\s*\)\s*\{/.test(js)) fail(file, 'logic must be class Component extends DCLogic with renderVals()');
    if (/^\s*(import|export)\s/m.test(js)) fail(file, 'import/export in logic');
    if (/Math\.random/.test(js)) fail(file, 'Math.random in renderVals (values would jitter)');
    // hole roots must be returned by renderVals (heuristic)
    const ri = js.lastIndexOf('return {');
    let retKeys = new Set();
    if (ri >= 0) {
      let depth = 0, end = ri + 7;
      for (let i = ri + 7; i < js.length; i++) { if (js[i] === '{') depth++; else if (js[i] === '}') { depth--; if (depth === 0) { end = i; break; } } }
      retKeys = new Set([...js.slice(ri + 8, end).matchAll(/([A-Za-z_$][\w$]*)\s*:/g)].map((x) => x[1]));
    }
    const loopVars = new Set([...xdc.matchAll(/<sc-for\b[^>]*\sas="([^"]+)"/g)].map((x) => x[1]).concat(['$index']));
    const missing = new Set();
    [...xdc.matchAll(/\{\{([\s\S]*?)\}\}/g)].forEach((h) => {
      const t = h[1].trim();
      if (/^(true|false|-?\d)/.test(t)) return;
      const root = t.split('.')[0];
      if (!loopVars.has(root) && !retKeys.has(root)) missing.add(root);
    });
    if (missing.size) fail(file, 'holes not returned by renderVals: ' + [...missing].join(', ')); else pass(file, 'every hole root is returned by renderVals');
  }

  // holes are dotted lookups
  const badHoles = [...xdc.matchAll(/\{\{([\s\S]*?)\}\}/g)].filter((h) => !HOLE_OK.test(h[1]));
  if (badHoles.length) badHoles.forEach((h) => fail(file, `hole is an expression at line ${lineOf(src, xOpen + 6 + h.index)}: ${h[0]}`));
  else pass(file, 'holes are dotted lookups (' + (xdc.match(/\{\{/g) || []).length + ')');

  // tag balance, quoting, self-closing, sc-* placement
  const tagRe = /<!--[\s\S]*?-->|<(\/?)([A-Za-z][\w:.-]*)((?:\s+[^\s"'>\/=]+(?:\s*=\s*(?:"[^"]*"|'[^']*'|[^\s"'>]+))?)*)\s*(\/?)>/g;
  const stack = [];
  let m, tagCount = 0, balanceOk = true;
  while ((m = tagRe.exec(xdc))) {
    if (m[0].startsWith('<!--')) continue;
    const [, close, rawName, attrs, selfClose] = m;
    const name = rawName.toLowerCase();
    const ln = lineOf(src, xOpen + 6 + m.index);
    tagCount++;
    if (selfClose) { fail(file, `self-closing <${rawName}/> at line ${ln}`); balanceOk = false; }
    if (!close) {
      [...attrs.matchAll(/([^\s"'>\/=]+)(?:\s*=\s*("[^"]*"|'[^']*'|[^\s"'>]+))?/g)].forEach((a) => {
        if (a[2] && !/^["']/.test(a[2])) { fail(file, `unquoted attribute ${a[1]} at line ${ln}`); balanceOk = false; }
        if (!a[2] && name !== 'script') warn(file, `bare attribute ${a[1]} on <${rawName}> at line ${ln}`);
      });
      if (/\sclass\s*=/.test(attrs)) fail(file, `class attribute at line ${ln}`);
      if (name === 'sc-for') {
        if (!/\slist="\{\{/.test(attrs) || !/\sas="/.test(attrs) || !/\shint-placeholder-count="/.test(attrs)) fail(file, `sc-for missing list/as/hint-placeholder-count at line ${ln}`);
      }
      if (name === 'sc-if') {
        if (!/\svalue="\{\{/.test(attrs) || !/\shint-placeholder-val="/.test(attrs)) fail(file, `sc-if missing value/hint-placeholder-val at line ${ln}`);
      }
      if ((name === 'sc-for' || name === 'sc-if') && stack.some((s) => s.name === 'svg' || s.name === 'table')) fail(file, `<${name}> inside <svg>/<table> at line ${ln}`);
      if (['iframe', 'object', 'embed'].includes(name)) fail(file, `<${name}> is not allowed (line ${ln})`);
      if (!VOID.has(name)) stack.push({ name, ln });
    } else {
      const top = stack.pop();
      if (!top || top.name !== name) { fail(file, `closing </${rawName}> at line ${ln} does not match <${top ? top.name : 'none'}> from line ${top ? top.ln : '-'}`); balanceOk = false; if (top) stack.push(top); }
    }
  }
  if (stack.length) { fail(file, 'unclosed elements: ' + stack.map((s) => `<${s.name}>@${s.ln}`).join(' ')); balanceOk = false; }
  if (balanceOk) pass(file, `tag balance, quoting, no self-closing (${tagCount} tags)`);

  // forbidden content
  ['innerHTML', 'appendChild', 'createElement', 'insertAdjacentHTML', 'document.write'].forEach((w) => { if (src.includes(w)) fail(file, 'forbidden API ' + w); });
  if (/\bdata:/.test(src.replace(/data-[\w-]+/g, ''))) fail(file, 'data: URI found');
  const urls = src.match(/https?:\/\/[^\s"')]+/g) || [];
  if (urls.length !== 1 || !urls[0].startsWith('https://fonts.googleapis.com/css2?')) fail(file, 'external URLs: ' + urls.join(' | ')); else pass(file, 'only external URL is the fonts css2 link');
  if (/synaiq/i.test(src)) fail(file, 'SynaIQ must not appear');
  if (!src.includes('示意資料')) fail(file, 'missing the sample-data label');
  let emoji = 0;
  for (const ch of src) { if (EMOJI(ch.codePointAt(0))) emoji++; }
  if (emoji) fail(file, emoji + ' emoji/private-use code points'); else pass(file, 'no emoji');

  // links
  const hrefs = [...xdc.matchAll(/\shref="([^"]*)"/g)].map((x) => x[1]).filter((h) => !h.startsWith('https://fonts.googleapis.com/'));
  hrefs.forEach((h) => {
    if (h.endsWith('.dc.html')) { if (!files.includes(h)) fail(file, 'href target missing: ' + h); }
    else if (h.startsWith('#')) { if (!xdc.includes(`id="${h.slice(1)}"`)) fail(file, 'anchor target missing: ' + h); }
    else fail(file, 'unexpected href: ' + h);
  });
  const navMissing = files.filter((f) => !hrefs.includes(f));
  if (navMissing.length) fail(file, 'sidebar lacks links to: ' + navMissing.join(', ')); else pass(file, 'links to all ' + files.length + ' artboards; every href target exists');
  const cur = [...xdc.matchAll(/<a href="([^"]+)" aria-current="page"/g)];
  if (cur.length !== 1 || cur[0][1] !== file) fail(file, 'aria-current="page" must mark exactly its own link'); else pass(file, 'active nav item = self (aria-current)');

  // controls
  [...xdc.matchAll(/<button\b([^>]*)>([\s\S]*?)<\/button>/g)].forEach((bt) => {
    const text = bt[2].replace(/<svg[\s\S]*?<\/svg>/g, '').replace(/<[^>]+>/g, '').trim();
    if (!/aria-label="[^"]+"/.test(bt[1]) && !text) fail(file, 'button without text or aria-label at line ' + lineOf(src, xOpen + 6 + bt.index));
  });
  [...xdc.matchAll(/<input\b([^>]*)>/g)].forEach((inp) => {
    const id = /\sid="([^"]+)"/.exec(inp[1]);
    if (!id || !xdc.includes(`for="${id[1]}"`)) fail(file, 'input without a matching <label for> at line ' + lineOf(src, xOpen + 6 + inp.index));
  });
  pass(file, 'buttons labelled; inputs paired with labels (' + (xdc.match(/<button\b/g) || []).length + ' buttons, ' + (xdc.match(/<input\b/g) || []).length + ' inputs)');

  // logo verbatim
  if (!logo.length) warn(file, 'logo source not found; verbatim check skipped');
  else {
    if (!xdc.includes('<svg viewBox="235.88 409.41 370.13 72.54" role="img" aria-label="tAIstro" style="height: 26px; width: auto; display: block;">')) fail(file, 'logo wrapper differs from the specified <svg>');
    const miss = logo.filter((frag) => xdc.split(frag).length - 1 !== 1);
    if (miss.length) miss.forEach((frag) => fail(file, 'logo shape not verbatim: ' + frag.slice(0, 70)));
    else pass(file, 'logo: 9 shapes verbatim, fill #cca858');
  }

  const fileErrors = errors - before;
  summary.push(`${file.padEnd(18)} ${String(b.w)}x${String(b.h).padEnd(5)} ${String(lineCount).padStart(4)} lines  ${fileErrors ? 'FAIL (' + fileErrors + ')' : 'PASS'}`);
});

lines.push('');
lines.push('== SUMMARY');
summary.forEach((s) => lines.push('  ' + s));
lines.push(`  canvas.json        ${canvas ? 'parsed' : 'unparsed'}`);
lines.push('');
lines.push(`RESULT: ${errors ? 'FAIL' : 'PASS'} - ${errors} error(s), ${warns} warning(s)`);
writeFileSync(join(ROOT, 'check.txt'), lines.map(esc).join('\n') + '\n', 'ascii');
process.exit(errors ? 1 : 0);
