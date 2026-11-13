const {chromium}=require('C:/Users/User/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const assert=require('node:assert/strict');
(async()=>{const b=await chromium.launch({channel:'msedge',headless:true});try{
 const page=await b.newPage({viewport:{width:1500,height:1120},acceptDownloads:true});const errors=[];page.on('pageerror',e=>errors.push(e.message));
 let failure=false,empty=false;
 await page.route('**/api/**',async route=>{
  const u=new URL(route.request().url());let data;
  if(u.pathname.endsWith('/auth/session'))data={username:'QA',role:'ops'};
  else if(u.pathname==='/api/devices')data=['plc-001','sensor-001','sim-001'].map(device_id=>({device_id}));
  else if(u.pathname.endsWith('/history')){
   if(failure){await route.fulfill({status:502,json:{detail:'unavailable'}});return;}
   const from=Date.parse(u.searchParams.get('since')),until=Date.parse(u.searchParams.get('until'));
   const keys=u.pathname.includes('sim-001')?['power_kw','voltage','current','energy_kwh']:u.pathname.includes('plc-001')?['temperature','humidity','pressure','motor_speed','pump_on','valve_open']:['temperature','humidity'];
   const step=Math.ceil((until-from)/600000),series=[];
   if(!empty)for(let i=0;i<600;i++){if(i>220&&i<260)continue;for(const [k,key]of keys.entries()){const state=key.endsWith('_on')||key.endsWith('_open');const value=state?Math.floor(i/70)%2:50+k*10+Math.sin(i/25)*5;series.push({signal:key,time:new Date(from+i*step*1000).toISOString(),value,min:state?value:value-2,max:state?value:value+3,last:value,samples:3,last_time:new Date(from+i*step*1000).toISOString()});}}
   data={device_id:u.pathname.split('/')[3],since:new Date(from).toISOString(),until:new Date(until).toISOString(),bucket_seconds:step,series};
  }else if(u.pathname.endsWith('/records')){
   const offset=Number(u.searchParams.get('offset')),until=Date.parse(u.searchParams.get('until'));
   data={has_more:offset===0,rows:empty?[]:Array.from({length:100},(_,i)=>({time:new Date(until-(offset+i+1)*1000).toISOString(),power_kw:42+i,voltage:380,current:70,energy_kwh:90,temperature:25,humidity:55,pressure:1001,motor_speed:1500,pump_on:false,valve_open:true}))};
  }else{await route.continue();return;}await route.fulfill({json:data});
 });
 await page.goto('http://127.0.0.1:4178/live/Monitor.history.html');
 await page.locator('.trend').first().waitFor();await page.selectOption('#auto','0');assert.equal(await page.locator('.trend').count(),4);
 assert.match(await page.locator('#device').innerText(),/工控電腦/);
 await page.locator('#next').click();await page.waitForFunction(()=>document.querySelector('#page-label').textContent.includes('第 2 頁'));assert.equal(await page.locator('#table-body tr').count(),100);
 const downloadPromise=page.waitForEvent('download');await page.locator('#export').click();const d=await downloadPromise;assert.match(d.suggestedFilename(),/page-2/);
 await page.selectOption('#device','plc-001');await page.waitForFunction(()=>document.querySelectorAll('.trend').length===6);assert.match(await page.locator('#cards').innerText(),/幫浦狀態/);
 await page.locator('.trend').first().hover({position:{x:180,y:100}});
 await page.screenshot({path:__dirname+'/history-mock-desktop.png',fullPage:true});
 await page.selectOption('#period','custom');await page.locator('#from').fill('2026-01-01T00:00');await page.locator('#to').fill('2026-02-01T00:00');await page.locator('#custom-range button').click();assert.match(await page.locator('#message').innerText(),/7 天/);
 await page.selectOption('#period','900');await page.locator('.trend').first().waitFor();
 empty=true;await page.locator('#refresh').click();await page.waitForFunction(()=>document.querySelector('#connection').textContent==='沒有資料');assert.equal(await page.locator('.trend').count(),0);
 empty=false;failure=true;await page.locator('#refresh').click();await page.waitForFunction(()=>document.querySelector('#connection').textContent==='查詢未完成');assert.equal(await page.locator('.trend').count(),0);
 failure=false;await page.locator('#refresh').click();await page.locator('.trend').first().waitFor();await page.setViewportSize({width:390,height:844});await page.waitForTimeout(250);
 assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'mobile must fit');
 await page.screenshot({path:__dirname+'/history-mock-mobile.png',fullPage:true});assert.deepEqual(errors,[]);
 console.log('PASS: four/six charts; labels; history page 2; CSV; range validation; empty/error clears; mobile fits; no JS errors');
}finally{await b.close()}})().catch(e=>{console.error(e);process.exit(1)});
