import {cp,mkdir,readFile,writeFile,readdir} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {dirname,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
const base=dirname(fileURLToPath(import.meta.url));
const source=resolve(base,'../ems-design-preview-20260923/public');
const releaseId=process.argv[2]||'20260923-local-v1';
if(!/^[a-zA-Z0-9-]+$/.test(releaseId))throw Error('Invalid release name');
const release=resolve(base,'releases',releaseId);
await mkdir(resolve(base,'releases'),{recursive:true});
await mkdir(release); // Never overwrite an existing release.
await cp(source,resolve(release,'public'),{recursive:true});
const root=resolve(release,'public');
// Compile the fixed design logic into external scripts. Published documents never evaluate source strings.
for(const name of ['Main','Monitor','Demand','Storage','Alarms','Devices','Reports']){
 const file=resolve(root,`boards/${name}.dc.html`);let html=await readFile(file,'utf8');
 const matches=[...html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/gi)];
 const logic=matches.find(m=>m[2].includes('class Component extends DCLogic'));
 if(!logic)throw Error('Missing component '+name);
 await writeFile(resolve(root,`boards/${name}.compiled.js`),`window.__emsCompiledLogic=function(DCLogic,StreamableLogic,React){\n${logic[2]}\nreturn Component;\n};\n`);
 html=html.replace('<script src="./support.js"></script>',`<script src="./${name}.compiled.js"></script><script src="./support.js"></script>`);
 // Keep the inert source block for the template parser; executing code comes only from the precompiled file.
 html=html.replace('<x-dc>','<template data-ems-dc><x-dc>').replace('</x-dc>','</x-dc></template>');
 await writeFile(file,html);
}
const runtimeFile=resolve(root,'boards/support.js');let runtime=await readFile(runtimeFile,'utf8');
const start=runtime.indexOf('function Se(t){'),end=runtime.indexOf('function ke(',start);
if(start<0||end<0)throw Error('Unknown design runtime version');
runtime=runtime.slice(0,start)+'function Se(t){if(!window.__emsCompiledLogic)throw Error("Missing compiled component");return window.__emsCompiledLogic(z,z,T())}'+runtime.slice(end);
const imported='new Function("React","module","exports","require",v)(T(),x,x.exports,()=>({}));';
if(!runtime.includes(imported))throw Error('Unknown import compiler');
runtime=runtime.replace(imported,'throw Error("Dynamic imports are disabled in the published EMS preview");');
if(runtime.includes('new Function('))throw Error('Unexpected dynamic compiler');
runtime=runtime.replace('t.querySelector("x-dc")','t.querySelector("template[data-ems-dc]")?.content.querySelector("x-dc")').replace('n.querySelector("x-dc")','n.querySelector("template[data-ems-dc]")');
await writeFile(runtimeFile,runtime);
const liveFile=resolve(root,'live/history-live.mjs');let live=await readFile(liveFile,'utf8');
if(!live.includes('fetch(path,{'))throw Error('Unknown API client');
live=live.replace('fetch(path,{',"fetch(new URL(path.replace(/^\\//,''),new URL('../',import.meta.url)),{");
await writeFile(liveFile,live);
let index=await readFile(resolve(root,'index.html'),'utf8');
index=index.replace('tAIstro EMS｜設計預覽','tAIstro EMS｜能源監控');
await writeFile(resolve(root,'index.html'),index);
const records=[];
async function walk(dir,prefix=''){for(const item of await readdir(dir,{withFileTypes:true})){const rel=prefix+item.name;if(item.isDirectory())await walk(resolve(dir,item.name),rel+'/');else{const data=await readFile(resolve(dir,item.name));records.push({path:rel,bytes:data.length,sha256:createHash('sha256').update(data).digest('hex')});}}}
await walk(root);await writeFile(resolve(release,'manifest.json'),JSON.stringify({release:releaseId,builtAt:new Date().toISOString(),files:records},null,2));
console.log(JSON.stringify({release,files:records.length}));


