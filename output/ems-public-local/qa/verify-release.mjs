import {readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
const base=new URL('../',import.meta.url);
const config=JSON.parse(await readFile(new URL('server-config.json',base),'utf8'));
const current=JSON.parse(await readFile(new URL(config.release+'/manifest.json',base),'utf8'));
const previous=JSON.parse(await readFile(new URL('releases/20260923-local-v8/manifest.json',base),'utf8'));
const changed=current.files.filter(f=>previous.files.find(p=>p.path===f.path)?.sha256!==f.sha256).map(f=>f.path);
for(let i=0;i<current.files.length;i+=4){await Promise.all(current.files.slice(i,i+4).map(async f=>{const r=await fetch('https://synaiq-ai.com/ems/'+f.path);if(r.status!==200)throw Error(f.path+' '+r.status);const digest=createHash('sha256').update(new Uint8Array(await r.arrayBuffer())).digest('hex');if(digest!==f.sha256)throw Error('Hash mismatch '+f.path);}));}
console.log(JSON.stringify({release:current.release,verifiedFiles:current.files.length,changedFromV8:changed}));
