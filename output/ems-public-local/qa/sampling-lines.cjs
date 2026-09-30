const {chromium}=require('C:/Users/User/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const base=process.argv[2]||'https://synaiq-ai.com/ems/';
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});let context;
 try{
  context=await browser.newContext({viewport:{width:1440,height:1100}});
  const creds=JSON.parse(fs.readFileSync(path.resolve(__dirname,'../../../.local/ems-preview-login.json'),'utf8'));
  const login=await context.request.post('https://synaiq-ai.com/ems/api/auth/login',{headers:{Origin:'https://synaiq-ai.com'},data:creds});
  assert.equal(login.status(),200,'authenticated public session');
  const page=await context.newPage(),errors=[],results=[];
  page.on('pageerror',e=>errors.push(e.message));
  if(base.startsWith('http://127.0.0.1:4181/'))await page.route('**/ems/api/**',async route=>{
   assert.equal(route.request().method(),'GET');
   const u=new URL(route.request().url());
   await route.fulfill({response:await context.request.get('https://synaiq-ai.com'+u.pathname+u.search)});
  });
  await page.goto(base+'#Monitor');const f=page.frameLocator('#screen');
  await f.locator('.trend').first().waitFor({timeout:30000});
  await f.locator('#auto').selectOption('0');
  const frame=page.frames().find(x=>x.url().includes('/live/Monitor.html'));
  for(const [id,period,expectedCharts]of [['delta-sim-001','900',4],['delta-sim-001','3600',4],['sim-001','900',4],['plc-001','900',6],['sensor-001','900',2]]){
   let data;
   for(const [control,value]of [['device',id],['period',period]]){
    if(await f.locator('#'+control).inputValue()===value)continue;
    const responsePromise=page.waitForResponse(r=>r.url().includes('/devices/'+id+'/history?'));
    await f.locator('#'+control).selectOption(value);
    const response=await responsePromise;assert.equal(response.status(),200,'history query');data=await response.json();
    await frame.waitForFunction(()=>document.querySelector('#connection').dataset.state!=='loading');
    assert.equal(await f.locator('#connection').getAttribute('data-state'),'history',await f.locator('#message').innerText());
   }
   const series=await frame.evaluate(()=>[...document.querySelectorAll('.trend')].map(el=>{
    const options=echarts.getInstanceByDom(el).getOption();const s=options.series[0];
    return {key:el.dataset.signal,connectNulls:s.connectNulls,width:s.lineStyle.width,data:s.data,connections:s.data.slice(1).filter((p,i)=>p[1]!==null&&s.data[i][1]!==null).length,step:s.step};
   }));
   assert.equal(series.length,expectedCharts);
   for(const s of series){
    assert.equal(s.connectNulls,false,'long gaps remain visible');assert.equal(s.width,2);
    const rows=data.series.filter(r=>r.signal===s.key).sort((a,b)=>Date.parse(a.time)-Date.parse(b.time));
    const useLast=['energy_kwh','pump_on','valve_open'].includes(s.key);
    assert.deepEqual(s.data.filter(p=>p[1]!==null),rows.map(r=>[Date.parse(r.time),useLast?r.last:r.value]),'line keeps every actual reading unchanged');
    if(rows.length>=10)assert.ok(s.connections>rows.length*.6,`${id}/${s.key}: expected connected line, got ${s.connections} segments from ${rows.length} points`);
    if(['pump_on','valve_open'].includes(s.key))assert.equal(s.step,'end');
   }
   const summary={device:id,period,charts:series.map(({key,data,connections})=>({key,points:data.filter(p=>p[1]!==null).length,connections}))};
   results.push(summary);console.log(JSON.stringify(summary));
   if(id==='delta-sim-001'&&period==='900'){
    await f.locator('#chart-grid').screenshot({path:path.join(__dirname,'sampling-lines-'+(base.startsWith('https:')?'public':'staging')+'-desktop.png')});
    await page.setViewportSize({width:390,height:844});await page.waitForTimeout(200);
    assert.ok(await frame.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    await f.locator('#chart-grid').screenshot({path:path.join(__dirname,'sampling-lines-'+(base.startsWith('https:')?'public':'staging')+'-mobile.png')});
    await page.setViewportSize({width:1440,height:1100});
   }
  }
  assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(__dirname,'sampling-lines-'+(base.startsWith('https:')?'public':'staging')+'.json'),JSON.stringify({base,results,errors},null,2));
 }finally{
  if(context)await context.request.post('https://synaiq-ai.com/ems/api/auth/logout',{headers:{Origin:'https://synaiq-ai.com'}}).catch(()=>{});
  await browser.close();
 }
})().catch(e=>{console.error(e);process.exit(1)});