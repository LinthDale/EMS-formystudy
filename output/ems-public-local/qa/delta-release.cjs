const {chromium}=require('C:/Users/User/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const base=process.argv[2]||'https://synaiq-ai.com/ems/';
(async()=>{
 const b=await chromium.launch({channel:'msedge',headless:true});
 try{
  const c=await b.newContext({viewport:{width:1440,height:1000}});
  const creds=JSON.parse(fs.readFileSync(path.resolve(__dirname,'../../../.local/ems-preview-login.json'),'utf8'));
  const login=await c.request.post('https://synaiq-ai.com/ems/api/auth/login',{headers:{Origin:'https://synaiq-ai.com'},data:creds});
  assert.equal(login.status(),200,'authenticated public session');
  const p=await c.newPage(),errors=[];p.on('pageerror',e=>errors.push(e.message));
  // Staging checks compiled assets against authenticated, read-only public data.
  if(base.startsWith('http://127.0.0.1:4181/')){
   await p.route('**/ems/api/**',async route=>{
    assert.equal(route.request().method(),'GET');
    const u=new URL(route.request().url());
    const response=await c.request.get('https://synaiq-ai.com'+u.pathname+u.search);
    await route.fulfill({response});
   });
  }
  await p.goto(base+'#Monitor');const f=p.frameLocator('#screen');
  await f.locator('#device option[value="delta-sim-001"]').waitFor({state:'attached'});
  await f.locator('#device').selectOption('delta-sim-001');
  await f.locator('#message').filter({hasText:'delta-sim-001 · 圖表與紀錄均來自後端資料'}).waitFor({timeout:30000});
  const label=await f.locator('#device option:checked').innerText();
  assert.equal(label,'太陽能逆變器(delta-sim-001)');
  const child=p.frames().find(frame=>frame.url().includes('/live/Monitor.html'));
  const series=await child.evaluate(()=>[...document.querySelectorAll('.trend')].map(el=>{
   const s=echarts.getInstanceByDom(el).getOption().series[0];
   return {size:s.symbolSize,symbol:s.symbol,scale:s.emphasis.scale,connectNulls:s.connectNulls};
  }));
  assert.equal(series.length,4);
  for(const s of series){assert.equal(s.size,2);assert.equal(s.symbol,'circle');assert.equal(s.scale,false);assert.equal(s.connectNulls,false);}
  assert.deepEqual(errors,[]);
  const result={base,label,series,records:await f.locator('#table-body tr').count(),errors};
  fs.writeFileSync(path.join(__dirname,base.startsWith('https:')?'delta-public-20260929.json':'delta-staging-20260929.json'),JSON.stringify(result,null,2));
  console.log(JSON.stringify(result,null,2));
 }finally{await b.close();}
})().catch(e=>{console.error(e.message);process.exitCode=1;});

