const {chromium}=require('C:/Users/User/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
(async()=>{const b=await chromium.launch({channel:'msedge',headless:true});try{const p=await b.newPage({viewport:{width:1440,height:1000}});for(const name of ['Main','Demand','Storage','Alarms','Devices','Reports']){
 await p.goto('https://synaiq-ai.com/ems/#'+name);await p.waitForFunction(n=>{const w=document.querySelector('#screen').contentWindow;return !!w.__dcRegistry?.[n]?.Logic;},name);
 const f=p.frames().find(f=>f.url().includes(name+'.dc.html'));
 console.log(name,JSON.stringify(await f.evaluate(()=>{
 const main=document.querySelector('main');
 function describe(e,d){const out={tag:e.tagName,id:e.id,role:e.getAttribute('role'),label:e.getAttribute('aria-labelledby'),style:e.getAttribute('style')};if(d>0)out.children=Array.from(e.children).filter(x=>!['SVG','PATH','SPAN'].includes(x.tagName.toUpperCase())).map(x=>describe(x,d-1));return out;}
 return describe(main,2);
 })));
 }}finally{await b.close();}})();
