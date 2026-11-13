import fs from 'node:fs';
import path from 'node:path';
const base=path.resolve(import.meta.dirname,'..');
const file=path.join(base,'public/boards/Main.dc.html');let s=fs.readFileSync(file,'utf8');
const crops=[['100 112',100,112,'50 0 520 620'],['160 62',160,62,'635 90 605 440'],['220 86',220,86,'0 730 625 455'],['130 72',130,86,'640 660 600 575']];
for(const [vb,w,h,crop] of crops){const re=new RegExp('<svg data-icon-set="pencil-v2" viewBox="0 0 '+vb+'"[\\s\\S]*?</svg>');if(!re.test(s))throw Error('Missing icon '+vb);s=s.replace(re,`<svg data-icon-set="illustration-v3" viewBox="${crop}" width="${w}" height="${h}" aria-hidden="true" style="display:block;overflow:hidden;flex-shrink:0"><image href="../assets/energy-illustrations-v3.png" width="1254" height="1254" /></svg>`);}
fs.writeFileSync(file,s);
const server=path.join(base,'server.mjs');fs.writeFileSync(server,fs.readFileSync(server,'utf8').replace("'.svg':'image/svg+xml'","'.svg':'image/svg+xml','.png':'image/png'"));
console.log('Four illustrations applied');