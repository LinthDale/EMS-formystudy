// PRD-0024 booth QR: unit test for public/live/qr-svg.mjs and the vendored uqr 0.1.3.
// Usage: node qa/qr-svg.test.mjs [public-root]   (default: the source tree ../ems-design-preview-20260923/public;
// pass releases/<id>/public to test a built release). No network, no browser.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {resolve} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';

const here=fileURLToPath(new URL('.',import.meta.url));
const root=resolve(process.argv[2]||resolve(here,'../../ems-design-preview-20260923/public'));
const at=rel=>resolve(root,rel);
const load=rel=>import(pathToFileURL(at(rel)).href);
const SVG_NS='http://www.w3.org/2000/svg';
const UQR_SHA256='7f0e61c2f13bb3724edee7bfb876e13c54ac9ee4fcfa283c9fa93cfb1241c325'; // dist/index.mjs of the sha512-verified uqr-0.1.3.tgz
const BORDER=4;
const links=[
 'https://t.me/TaistroEmsDemoBot?start=bQ3x9_LmN-2pRtYvWzK8aHc',          // typical: "b" + 22 base64url chars (version 4)
 'https://t.me/abcde?start=b-_-_-_-_-_-_-_-_-_-_-_',                    // shortest bot name
 'https://t.me/'+'a'.repeat(29)+'bot?start='+'Zz09-_'.repeat(10)+'Zz09', // Telegram maxima: 32-char bot, 64-char start (version 7)
 'https://example.com/'+'q'.repeat(120)                                  // version 8: uneven blocks + version info
];

// ---- Independent ISO/IEC 18004 reader (byte mode, ECC level M, versions 1-10) ----
const ALIGN=[[],[],[6,18],[6,22],[6,26],[6,30],[6,34],[6,22,38],[6,24,42],[6,26,46],[6,28,50]];
const TOTAL_CODEWORDS=[0,26,44,70,100,134,172,196,242,292,346];
const M_BLOCKS=[null,[10,[[1,16]]],[16,[[1,28]]],[26,[[1,44]]],[18,[[2,32]]],[24,[[2,43]]],[16,[[4,27]]],[18,[[4,31]]],[22,[[2,38],[2,39]]],[22,[[3,36],[2,37]]],[26,[[4,43],[1,44]]]];
const MASKS=[(x,y)=>(x+y)%2===0,(x,y)=>y%2===0,(x,y)=>x%3===0,(x,y)=>(x+y)%3===0,(x,y)=>(Math.floor(y/2)+Math.floor(x/3))%2===0,
 (x,y)=>x*y%2+x*y%3===0,(x,y)=>(x*y%2+x*y%3)%2===0,(x,y)=>((x+y)%2+x*y%3)%2===0];
const EXP=[],LOG=[];
for(let i=0,v=1;i<255;i++){EXP[i]=EXP[i+255]=v;LOG[v]=i;v=(v<<1)^(v&128?0x11d:0);}
const gfMul=(a,b)=>a&&b?EXP[LOG[a]+LOG[b]]:0;

function formatInfo(m){
 const n=m.length,bit=(x,y)=>m[y][x]?1:0;let a=0,b=0;
 for(let i=0;i<=5;i++)a|=bit(8,i)<<i;
 a|=bit(8,7)<<6|bit(8,8)<<7|bit(7,8)<<8;
 for(let i=9;i<15;i++)a|=bit(14-i,8)<<i;
 for(let i=0;i<8;i++)b|=bit(n-1-i,8)<<i;
 for(let i=8;i<15;i++)b|=bit(8,n-15+i)<<i;
 assert.equal(a,b,'both format-information copies agree');
 const raw=a^0x5412,data=raw>>>10;let rem=data;
 for(let i=0;i<10;i++)rem=(rem<<1)^((rem>>>9)*0x537);
 assert.equal(data<<10|rem,raw,'format information BCH code is valid');
 return {ecc:data>>>3,mask:data&7};
}
function functionModules(n,version){
 const f=Array.from({length:n},()=>Array(n).fill(false));
 const mark=(x,y,w,h)=>{for(let j=y;j<y+h;j++)for(let i=x;i<x+w;i++)f[j][i]=true;};
 mark(0,0,9,9);mark(n-8,0,8,9);mark(0,n-8,9,8); // finders, separators, format information, dark module
 mark(6,0,1,n);mark(0,6,n,1);                    // timing patterns
 const pos=ALIGN[version],last=pos.length-1;
 pos.forEach((cy,i)=>pos.forEach((cx,j)=>{if(!(i===0&&j===0||i===0&&j===last||i===last&&j===0))mark(cx-2,cy-2,5,5);}));
 if(version>=7){mark(n-11,0,3,6);mark(0,n-11,6,3);} // version information
 return f;
}
function readCodewords(m,mask){
 const n=m.length,f=functionModules(n,(n-17)/4),bits=[];
 for(let right=n-1;right>=1;right-=2){
  if(right===6)right=5;
  for(let k=0;k<n;k++)for(const x of [right,right-1]){
   const y=((right+1)&2)===0?n-1-k:k;
   if(!f[y][x])bits.push(m[y][x]!==MASKS[mask](x,y));
  }
 }
 const words=[];
 for(let i=0;i+8<=bits.length;i+=8)words.push(bits.slice(i,i+8).reduce((v,b)=>v<<1|(b?1:0),0));
 return words;
}
function decode(m){
 const n=m.length,version=(n-17)/4;
 assert.ok(Number.isInteger(version)&&version>=1&&version<ALIGN.length,'supported version '+version);
 const {ecc,mask}=formatInfo(m);
 assert.equal(ecc,0b00,'error correction level M');
 assert.equal(m[n-8][8],true,'dark module');
 const words=readCodewords(m,mask);
 assert.equal(words.length,TOTAL_CODEWORDS[version],'codeword capacity of version '+version);
 const [eccLen,groups]=M_BLOCKS[version];
 const blocks=groups.flatMap(([count,len])=>Array.from({length:count},()=>({len,data:[],ecc:[]})));
 let p=0;
 for(let i=0;i<Math.max(...blocks.map(b=>b.len));i++)for(const b of blocks)if(i<b.len)b.data.push(words[p++]);
 for(let i=0;i<eccLen;i++)for(const b of blocks)b.ecc.push(words[p++]);
 assert.equal(p,words.length,'all codewords consumed');
 for(const b of blocks)for(let k=0;k<eccLen;k++)
  assert.equal([...b.data,...b.ecc].reduce((acc,c)=>gfMul(acc,EXP[k])^c,0),0,'Reed-Solomon syndrome '+k+' is zero');
 const bits=blocks.flatMap(b=>b.data).flatMap(byte=>Array.from({length:8},(_,i)=>byte>>7-i&1));
 let cursor=0;const take=len=>{let v=0;for(let i=0;i<len;i++)v=v<<1|bits[cursor++];return v;};
 assert.equal(take(4),0b0100,'byte mode');
 const length=take(version<10?8:16),bytes=Array.from({length},()=>take(8));
 assert.equal(take(Math.min(4,bits.length-cursor)),0,'terminator');
 return Buffer.from(bytes).toString('utf8');
}
// Rebuild the module grid from the path; only unit-high horizontal runs are accepted.
function cellsFromPath(d,size){
 assert.match(d,/^(?:M\d+ \d+h\d+v1h-\d+z)*$/,'path holds only unit-height horizontal runs');
 const grid=Array.from({length:size},()=>Array(size).fill(false));let count=0;
 for(const [,x,y,w,back] of d.matchAll(/M(\d+) (\d+)h(\d+)v1h-(\d+)z/g)){
  const x0=Number(x),y0=Number(y),len=Number(w);
  assert.equal(back,w,'run closes on itself');assert.ok(len>0&&x0+len<=size&&y0<size,'run inside the symbol');
  for(let i=0;i<len;i++){assert.equal(grid[y0][x0+i],false,'runs never overlap');grid[y0][x0+i]=true;count++;}
 }
 return {grid,count};
}
// Minimal document: records createElementNS calls, refuses every HTML-string entry point.
function fakeDocument(){
 const doc={created:[],htmlWrites:0};
 class FakeElement{
  constructor(ns,name){this.namespaceURI=ns;this.localName=name;this.children=[];this.attrs=new Map();}
  setAttribute(k,v){this.attrs.set(k,String(v));}
  getAttribute(k){return this.attrs.has(k)?this.attrs.get(k):null;}
  append(...nodes){this.children.push(...nodes);}
  appendChild(node){this.children.push(node);return node;}
  set innerHTML(v){doc.htmlWrites++;throw Error('innerHTML is forbidden');}
  set outerHTML(v){doc.htmlWrites++;throw Error('outerHTML is forbidden');}
  insertAdjacentHTML(){doc.htmlWrites++;throw Error('insertAdjacentHTML is forbidden');}
 }
 doc.createElementNS=(ns,name)=>{doc.created.push(`${ns} ${name}`);return new FakeElement(ns,name);};
 doc.createElement=()=>{throw Error('SVG must be created with createElementNS');};
 return doc;
}

let qr,uqr;
test('vendored uqr 0.1.3 is the verified build and live/qr-svg.mjs loads',async()=>{
 const bytes=await readFile(at('assets/uqr-0.1.3.mjs'));
 assert.equal(createHash('sha256').update(bytes).digest('hex'),UQR_SHA256,'uqr is byte-identical to the verified npm tarball');
 assert.match(await readFile(at('assets/UQR-LICENSE.txt'),'utf8'),/^MIT License/);
 uqr=await load('assets/uqr-0.1.3.mjs');qr=await load('live/qr-svg.mjs');
 assert.equal(typeof qr.qrPath,'function');assert.equal(typeof qr.createQrSvg,'function');
});
test('path covers exactly the uqr dark modules inside a 4-module white quiet zone',()=>{
 for(const link of links){
  const {size,d}=qr.qrPath(link),ref=uqr.encode(link,{ecc:'M',border:BORDER});
  assert.equal(size,ref.size);assert.equal(size,ref.version*4+17+2*BORDER);
  const {grid,count}=cellsFromPath(d,size);
  assert.equal(count,ref.data.flat().filter(Boolean).length,'dark module count equals the uqr matrix');
  assert.deepEqual(grid,ref.data,'dark module positions equal the uqr matrix');
  grid.forEach((row,y)=>row.forEach((dark,x)=>{if(Math.min(x,y,size-1-x,size-1-y)<BORDER)assert.equal(dark,false,`quiet zone ${x},${y}`);}));
 }
});
test('rendered path decodes back to the exact link (ECC M, valid format information and Reed-Solomon)',()=>{
 for(const link of links){
  const {size,d}=qr.qrPath(link),{grid}=cellsFromPath(d,size);
  const symbol=grid.slice(BORDER,size-BORDER).map(row=>row.slice(BORDER,size-BORDER));
  assert.equal(decode(symbol),link);
 }
});
test('SVG is assembled only through createElementNS/setAttribute (no HTML parsing)',()=>{
 const doc=fakeDocument(),link=links[0],svg=qr.createQrSvg(doc,link),{size,d}=qr.qrPath(link);
 assert.deepEqual([...doc.created].sort(),[`${SVG_NS} path`,`${SVG_NS} svg`]);
 assert.equal(svg.localName,'svg');assert.equal(svg.namespaceURI,SVG_NS);
 assert.equal(svg.getAttribute('viewBox'),`0 0 ${size} ${size}`);
 assert.equal(svg.getAttribute('role'),'img');
 assert.ok(svg.getAttribute('aria-label'),'accessible name');
 assert.equal(svg.getAttribute('data-link'),link);
 assert.equal(svg.children.length,1);
 assert.equal(svg.children[0].localName,'path');assert.equal(svg.children[0].getAttribute('d'),d);
 assert.equal(doc.htmlWrites,0);
});
test('rejects empty, non-string and oversized input',()=>{
 assert.equal(typeof qr?.qrPath,'function','qr-svg module loaded');
 const refused={name:'TypeError',message:/QR text/};
 for(const bad of ['',null,undefined,42,{},'x'.repeat(257)])assert.throws(()=>qr.qrPath(bad),refused);
 assert.throws(()=>qr.createQrSvg(fakeDocument(),''),refused);
 assert.equal(qr.qrPath('x'.repeat(256)).size>0,true,'256 characters is still accepted');
});
test('QR and alarm panel sources never use HTML-string DOM APIs',async()=>{
 for(const rel of ['live/qr-svg.mjs','live/alarm-demo.mjs']){
  const source=await readFile(at(rel),'utf8');
  assert.doesNotMatch(source,/innerHTML|outerHTML|insertAdjacentHTML|DOMParser|createContextualFragment|document\.write|srcdoc|\beval\(|new Function/,rel);
 }
});
