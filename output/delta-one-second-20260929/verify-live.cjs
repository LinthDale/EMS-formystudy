const {chromium}=require('C:/Users/User/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs'),path=require('path'),assert=require('assert/strict');
(async()=>{
 const root=path.resolve(__dirname,'../..'),started=Math.max(Date.parse(fs.readFileSync(path.join(__dirname,'deployed-at.txt'),'utf8')),...JSON.parse(fs.readFileSync(path.join(__dirname,'runtime-current.json'),'utf8')).map(r=>Date.parse(r.started)));
 const until=Date.now()-10000,since=Math.max(started+5000,until-120000);
 assert.ok(until-since>=60000,'allow at least 60 seconds of new data');
 const browser=await chromium.launch({channel:'msedge',headless:true});let context;
 try{
  context=await browser.newContext({viewport:{width:1440,height:1100}});
  const auth=await context.request.post('https://synaiq-ai.com/ems/api/auth/login',{headers:{Origin:'https://synaiq-ai.com'},data:JSON.parse(fs.readFileSync(path.join(root,'.local/ems-preview-login.json'),'utf8'))});assert.equal(auth.status(),200);
  const query=new URLSearchParams({since:new Date(since).toISOString(),until:new Date(until).toISOString(),limit:'1000',offset:'0'});
  const res=await context.request.get('https://synaiq-ai.com/ems/api/devices/delta-sim-001/records?'+query);assert.equal(res.status(),200);
  const data=await res.json(),rows=data.rows.sort((a,b)=>Date.parse(a.time)-Date.parse(b.time));assert.equal(data.has_more,false);assert.ok(rows.length>=60);
  const gaps=rows.slice(1).map((row,i)=>(Date.parse(row.time)-Date.parse(rows[i].time))/1000).sort((a,b)=>a-b);
  console.log(JSON.stringify({diagnostic:{rows:rows.length,min:Math.min(...gaps),max:Math.max(...gaps),bad:rows.slice(1).map((row,i)=>({at:row.time,gap:(Date.parse(row.time)-Date.parse(rows[i].time))/1000})).filter(r=>r.gap<.8||r.gap>1.2)}}));
  assert.ok(Math.min(...gaps)>.8&&Math.abs(gaps[Math.floor(gaps.length/2)]-1)<.01,'one-second nominal cadence, no catch-up burst');
  assert.ok(gaps.filter(g=>g<1.2).length>gaps.length*.9,'at least 90% of measured intervals must be one second');
  const interruptions=rows.slice(1).map((r,i)=>({start:Date.parse(rows[i].time),end:Date.parse(r.time),seconds:(Date.parse(r.time)-Date.parse(rows[i].time))/1000})).filter(g=>g.seconds>1.2);
  const volts=rows.map(r=>r.voltage);assert.ok(new Set(volts).size>10);assert.ok(Math.min(...volts)>=225.4&&Math.max(...volts)<=234.5);
  assert.ok(rows.every((r,i)=>i===0||r.energy_kwh>=rows[i-1].energy_kwh),'energy counter never decreases within this runtime');
  const original=await context.request.get('https://synaiq-ai.com/ems/api/devices/sim-001/records?'+query);assert.equal(original.status(),200);const oldRows=(await original.json()).rows;assert.ok(oldRows.length>=60,'existing meter still collecting');
  oldRows.sort((a,b)=>Date.parse(a.time)-Date.parse(b.time));
  const originalGaps=oldRows.slice(1).map((r,i)=>({start:Date.parse(oldRows[i].time),end:Date.parse(r.time)})).filter(g=>g.end-g.start>1500);
  for(const gap of interruptions)assert.ok(originalGaps.some(g=>g.start<gap.end&&g.end>gap.start),'every irregular interval must coincide with the existing meter, never silently hide a Delta-only failure');
  const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));await page.goto('https://synaiq-ai.com/ems/#Monitor');const f=page.frameLocator('#screen');await f.locator('.trend').first().waitFor();await f.locator('#auto').selectOption('0');
  const historyResponse=page.waitForResponse(r=>r.url().includes('/delta-sim-001/history?')&&r.status()===200);await f.locator('#device').selectOption('delta-sim-001');const history=await(await historyResponse).json();const frame=page.frames().find(f=>f.url().includes('/live/Monitor.html'));await frame.waitForFunction(()=>document.querySelector('#connection').dataset.state==='history');
  const recent=history.series.filter(r=>Date.parse(r.time)>since&&r.signal==='voltage');assert.ok(recent.filter(r=>r.samples>=2&&r.min!==r.max).length>=10,'dense noisy data produces separate min/max readings');
  await frame.evaluate(start=>{for(const el of document.querySelectorAll('.trend'))echarts.getInstanceByDom(el).dispatchAction({type:'dataZoom',startValue:start,endValue:Date.now()})},since);
  await f.locator('#chart-grid').screenshot({path:path.join(__dirname,'live-chart-desktop.png')});
  await page.setViewportSize({width:390,height:844});await page.waitForTimeout(150);assert.ok(await frame.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await f.locator('#chart-grid').screenshot({path:path.join(__dirname,'live-chart-mobile.png')});assert.deepEqual(errors,[]);
  const result={sharedClockGaps:interruptions,since:new Date(since).toISOString(),until:new Date(until).toISOString(),rows:rows.length,intervalSeconds:{min:Math.min(...gaps),median:gaps[Math.floor(gaps.length/2)],max:Math.max(...gaps)},voltage:{min:Math.min(...volts),max:Math.max(...volts),unique:new Set(volts).size},power:{min:Math.min(...rows.map(r=>r.power_kw)),max:Math.max(...rows.map(r=>r.power_kw))},originalMeterRows:oldRows.length,graphBucketSeconds:history.bucket_seconds,graphRecentVaryingBuckets:recent.filter(r=>r.samples>=2&&r.min!==r.max).length,errors};
  fs.writeFileSync(path.join(__dirname,'live-result.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result,null,2));
 }finally{if(context)await context.request.post('https://synaiq-ai.com/ems/api/auth/logout',{headers:{Origin:'https://synaiq-ai.com'}}).catch(()=>{});await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});