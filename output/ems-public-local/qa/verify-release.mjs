import {readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
// Read-only check: every file in the configured release manifest is served with the same SHA256.
// Usage: node qa/verify-release.mjs [config file in output/ems-public-local, default server-config.json]
//                                   [site, default https://synaiq-ai.com/ems/; or a loopback relay http://127.0.0.1:<port>/ems/]
const base=new URL('../',import.meta.url);
const configName=process.argv[2]||'server-config.json',site=process.argv[3]||'https://synaiq-ai.com/ems/';
if(!/^[\w.-]+\.json$/.test(configName))throw Error('Config must be a JSON file name in output/ems-public-local');
if(!/^(?:https:\/\/synaiq-ai\.com|http:\/\/127\.0\.0\.1:\d{2,5})\/ems\/$/.test(site))throw Error('Site must be https://synaiq-ai.com/ems/ or http://127.0.0.1:<port>/ems/');
const config=JSON.parse(await readFile(new URL(configName,base),'utf8'));
const current=JSON.parse(await readFile(new URL(config.release+'/manifest.json',base),'utf8'));
const previous=JSON.parse(await readFile(new URL('releases/20260923-local-v8/manifest.json',base),'utf8'));
const changed=current.files.filter(f=>previous.files.find(p=>p.path===f.path)?.sha256!==f.sha256).map(f=>f.path);
for(let i=0;i<current.files.length;i+=4){await Promise.all(current.files.slice(i,i+4).map(async f=>{const r=await fetch(site+f.path);if(r.status!==200)throw Error(f.path+' '+r.status);const digest=createHash('sha256').update(new Uint8Array(await r.arrayBuffer())).digest('hex');if(digest!==f.sha256)throw Error('Hash mismatch '+f.path);}));}
console.log(JSON.stringify({release:current.release,verifiedFiles:current.files.length,changedFromV8:changed,site}));
