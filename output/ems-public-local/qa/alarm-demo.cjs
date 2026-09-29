const {chromium}=require('C:/Users/User/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const assert=require('node:assert/strict');
const base=process.argv[2]||'http://127.0.0.1:4178/';
(async()=>{const browser=await chromium.launch({channel:'msedge',headless:true});try{
 const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 let logged=false,sends=0,mode='success',recent=[],cooldown=0;
 const reply=(route,status,body)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});
 await page.route('**/api/auth/login',route=>{logged=true;return reply(route,200,{role:'ops'});});
 await page.route('**/api/alarms/demo',async route=>{
  if(!logged)return reply(route,401,{detail:'unauthenticated'});
  if(route.request().method()==='GET')return reply(route,200,{configured:mode!=='unconfigured',cooldown_seconds:cooldown,recent});
  sends++;
  await new Promise(resolve=>setTimeout(resolve,150));
  if(mode==='failure')return reply(route,502,{detail:'telegram_delivery_unknown'});
  const data={status:'sent',channel:'telegram',event_id:route.request().postDataJSON().request_id,sent_at:new Date().toISOString(),cooldown_seconds:30};
  recent=[data];cooldown=30;return reply(route,200,data);
 });
 await page.goto(base+'#Alarms');
 const frame=page.frameLocator('#screen'),button=frame.locator('#alarm-demo-trigger'),status=frame.locator('#alarm-demo-status');
 await frame.locator('#alarm-demo-login').waitFor({state:'visible'});
 assert.equal(await button.isDisabled(),true);
 await frame.locator('#alarm-demo-password').fill('mock-password-only');
 await frame.locator('#alarm-demo-login button').click();
 await page.waitForFunction(()=>document.querySelector('#screen').contentDocument.querySelector('#alarm-demo-trigger')?.disabled===false);
 await button.click();
 await status.filter({hasText:'已發送至 Telegram'}).waitFor();
 assert.equal(sends,1);assert.equal(await button.isDisabled(),true);
 assert.equal(await frame.locator('#alarm-demo-recent li').count(),1);
 // A DC/React update elsewhere in this page must retain the demo panel and its state.
 const ack=frame.getByRole('button',{name:'確認',exact:true}).first();
 if(await ack.count()){await ack.click();assert.equal(await frame.locator('#alarm-demo-trigger').count(),1);assert.equal(await frame.locator('#alarm-demo-recent li').count(),1);}
 for(const width of [1440,768,390,320]){
  await page.setViewportSize({width,height:1000});await page.waitForTimeout(250);
  const child=page.frames().find(f=>f.url().includes('Alarms.dc.html'));
  const geometry=await child.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth,panel:document.querySelector('#alarm-demo').getBoundingClientRect().toJSON(),button:document.querySelector('#alarm-demo-trigger').getBoundingClientRect().toJSON()}));
  assert.ok(geometry.scroll<=geometry.width+1,JSON.stringify(geometry));
  assert.ok(geometry.button.x>=0&&geometry.button.right<=geometry.width,JSON.stringify(geometry));
  if(width===1440||width===390)await page.screenshot({path:__dirname+'/alarm-demo-mock-'+width+'.png',fullPage:true});
 }
 // Failure never renders a success row, and reloading does not replay POST.
 recent=[];cooldown=0;mode='failure';await page.reload();
 await page.waitForFunction(()=>document.querySelector('#screen').contentDocument.querySelector('#alarm-demo-trigger')?.disabled===false);
 await button.click();await status.filter({hasText:'發送結果尚未確認'}).waitFor();
 assert.equal(await frame.locator('#alarm-demo-recent li').count(),0);assert.equal(sends,2);
 await page.reload();await status.filter({hasText:'已連接 Telegram'}).waitFor();assert.equal(sends,2);
 mode='unconfigured';await page.reload();await status.filter({hasText:'尚未設定 Telegram'}).waitFor();assert.equal(await button.isDisabled(),true);
 assert.deepEqual(errors,[]);console.log('PASS: mocked UI login, one POST per click, cooldown, retained state, honest failure, no retry, 320/390/768/1440px; no real Telegram sent');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
