// Mocked E2E for the Alarms page Telegram demo panel: PRD-0019 legacy flow + PRD-0024 booth QR binding.
// Every /api request is fulfilled by Playwright routes, so nothing reaches a BFF and no Telegram message is sent.
// Usage: node qa/alarm-demo.cjs [base-url, default http://127.0.0.1:4178/] [screenshot-dir, default this folder]
const {chromium}=require('C:/Users/User/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const assert=require('node:assert/strict');
const {join}=require('node:path');
const base=process.argv[2]||'http://127.0.0.1:4178/';
const shots=process.argv[3]||__dirname;
const L1='https://t.me/TaistroEmsDemoBot?start=bQ3x9_LmN-2pRtYvWzK8aHc',L2='https://t.me/TaistroEmsDemoBot?start=b7Hk2_Pq-9sDfGh3JkLmN0r';
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function until(condition,ms,label){const end=Date.now()+ms;while(!condition()){if(Date.now()>end)throw Error('timed out waiting for '+label);await delay(100);}}
// `binding` block of GET /api/alarms/demo. Expiry is kept absolute so each poll reports the true remaining seconds.
const booth=({state='ready',link=L1,current=null,count=0}={})=>({state,deep_link:state==='ready'?link:null,current,today:{date:'2026-10-13',visitor_count:count}});
const visitor=(display='@da***',seconds=412)=>({display,expiresAt:Date.now()+seconds*1000,username:'leaked_full_username'});
const wire=b=>{if(!b||!b.current)return b;const {expiresAt,...rest}=b.current;return {...b,current:{...rest,expires_in_seconds:Math.max(0,Math.ceil((expiresAt-Date.now())/1000))}};};
const sends=n=>Array.from({length:n},(_,i)=>({status:'sent',event_id:`00000000-0000-4000-8000-${String(i).padStart(12,'0')}`,sent_at:new Date(Date.now()-i*60000).toISOString(),channel:'telegram',target:i%3===2?'default':'visitor',visitor_number:i%3===2?null:n-i}));
const remaining=text=>{const m=/剩 (\d+):(\d\d)）/.exec(text);assert.ok(m,'countdown in '+text);return Number(m[1])*60+Number(m[2]);};
(async()=>{const browser=await chromium.launch({channel:'msedge',headless:true}),results=[];try{
 const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];
 page.setDefaultTimeout(9000);
 page.on('pageerror',e=>errors.push(e.message));
 const state={logged:false,mode:'success',recent:[],cooldown:0,binding:undefined,gets:0,sends:0,post:{cooldown:30}};
 const reply=(route,status,body)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});
 await page.route('**/api/**',route=>reply(route,401,{detail:'unauthenticated'})); // fallback: no request reaches the relay's BFF proxy
 await page.route('**/api/auth/login',route=>{state.logged=true;return reply(route,200,{role:'ops'});});
 await page.route('**/api/alarms/demo',async route=>{
  if(!state.logged)return reply(route,401,{detail:'unauthenticated'});
  if(route.request().method()==='GET'){
   state.gets++;const body={configured:state.mode!=='unconfigured',cooldown_seconds:state.cooldown,recent:state.recent};
   if(state.binding!==undefined)body.binding=wire(state.binding);
   return reply(route,200,body);
  }
  state.sends++;
  await delay(150);
  if(state.mode==='failure')return reply(route,502,{detail:'telegram_delivery_unknown'});
  const data={status:'sent',channel:'telegram',event_id:route.request().postDataJSON().request_id,sent_at:new Date().toISOString(),cooldown_seconds:state.post.cooldown};
  if(state.post.target)Object.assign(data,{target:state.post.target,visitor_number:state.post.number});
  state.recent=state.post.target?[data,...state.recent].slice(0,10):[data];state.cooldown=state.post.cooldown;
  return reply(route,200,data);
 });
 const frame=page.frameLocator('#screen'),button=frame.locator('#alarm-demo-trigger'),status=frame.locator('#alarm-demo-status');
 const qrSvg=frame.locator('#alarm-demo-qr svg'),note=frame.locator('#alarm-demo-bot-note'),toggle=frame.locator('#alarm-demo-toggle');
 const child=()=>page.frames().find(f=>f.url().includes('Alarms.dc.html'));
 const text=async selector=>(await frame.locator(selector).first().textContent()).trim();
 const enabled=()=>page.waitForFunction(()=>document.querySelector('#screen').contentDocument.querySelector('#alarm-demo-trigger')?.disabled===false);
 const panelShot=name=>frame.locator('#alarm-demo').screenshot({path:join(shots,`alarm-demo-booth-${name}.png`)});
 const setVisibility=value=>child().evaluate(v=>{Object.defineProperty(document,'visibilityState',{configurable:true,get:()=>v});Object.defineProperty(document,'hidden',{configurable:true,get:()=>v==='hidden'});document.dispatchEvent(new Event('visibilitychange'));},value);
 async function load(patch){Object.assign(state,{logged:true,mode:'success',cooldown:0,recent:[],post:{cooldown:0}},patch);await page.reload();await status.filter({hasText:'已連接 Telegram'}).waitFor();}
 async function check(name,fn){
  try{await fn();results.push(true);console.log('PASS '+name);}
  catch(e){results.push(false);console.log('FAIL '+name+' :: '+String(e?.message||e).split('\n').filter(Boolean).slice(0,3).join(' | ').slice(0,400));}
 }

 await check('legacy panel without a binding field: login, one POST per click, cooldown, retained state, honest failure, no retry, 320/390/768/1440px',async()=>{
  await page.goto(base+'#Alarms');
  await frame.locator('#alarm-demo-login').waitFor({state:'visible'});
  assert.equal(await button.isDisabled(),true);
  await frame.locator('#alarm-demo-password').fill('mock-password-only');
  await frame.locator('#alarm-demo-login button').click();
  await enabled();
  await button.click();
  await status.filter({hasText:'已發送至 Telegram'}).waitFor();
  assert.equal(state.sends,1);assert.equal(await button.isDisabled(),true);
  assert.equal(await frame.locator('#alarm-demo-recent li').count(),1);
  assert.equal(await frame.locator('#alarm-demo-booth').isVisible(),false,'no booth block without a binding field');
  assert.equal(await toggle.isVisible(),false,'no toggle for a single row');
  // A DC/React update elsewhere in this page must retain the demo panel and its state.
  const ack=frame.getByRole('button',{name:'確認',exact:true}).first();
  if(await ack.count()){await ack.click();assert.equal(await frame.locator('#alarm-demo-trigger').count(),1);assert.equal(await frame.locator('#alarm-demo-recent li').count(),1);}
  for(const width of [1440,768,390,320]){
   await page.setViewportSize({width,height:1000});await page.waitForTimeout(250);
   const geometry=await child().evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth,panel:document.querySelector('#alarm-demo').getBoundingClientRect().toJSON(),button:document.querySelector('#alarm-demo-trigger').getBoundingClientRect().toJSON()}));
   assert.ok(geometry.scroll<=geometry.width+1,JSON.stringify(geometry));
   assert.ok(geometry.button.x>=0&&geometry.button.right<=geometry.width,JSON.stringify(geometry));
   if(width===1440||width===390)await page.screenshot({path:join(shots,'alarm-demo-mock-'+width+'.png'),fullPage:true});
  }
  await page.setViewportSize({width:1440,height:1000});
  // Failure never renders a success row, and reloading does not replay POST.
  state.recent=[];state.cooldown=0;state.mode='failure';await page.reload();
  await enabled();
  await button.click();await status.filter({hasText:'發送結果尚未確認'}).waitFor();
  assert.equal(await frame.locator('#alarm-demo-recent li').count(),0);assert.equal(state.sends,2);
  await page.reload();await status.filter({hasText:'已連接 Telegram'}).waitFor();assert.equal(state.sends,2);
  state.mode='unconfigured';await page.reload();await status.filter({hasText:'尚未設定 Telegram'}).waitFor();assert.equal(await button.isDisabled(),true);
 });

 await check('binding:null (feature off) keeps the PRD-0019 panel: no QR, legacy intro, unlabeled rows, no polling',async()=>{
  await load({binding:null,recent:[{status:'sent',event_id:'11111111-2222-4333-8444-555555555555',sent_at:new Date().toISOString(),channel:'telegram'}]});
  assert.equal(await frame.locator('#alarm-demo-booth').isVisible(),false);
  assert.equal(await qrSvg.count(),0);
  assert.equal(await text('.alarm-demo-top p'),'發送一則標示「無需處置」的測試訊息到已設定的 Telegram 接收對象。');
  assert.doesNotMatch(await text('#alarm-demo-recent li'),/訪客|預設對象/);
  assert.equal((await button.textContent()).trim(),'觸發警報');
  const gets=state.gets;await delay(5000);assert.equal(state.gets,gets,'no polling without a binding');
 });

 await check('ready + unbound: QR from deep_link, 目前綁定：無, today count, no bot note, unchanged button label',async()=>{
  await load({binding:booth(),recent:sends(3)});
  await qrSvg.waitFor();
  assert.equal(await qrSvg.getAttribute('data-link'),L1);
  assert.equal(await qrSvg.getAttribute('role'),'img');
  assert.ok(await qrSvg.getAttribute('aria-label'),'QR has an accessible name');
  assert.match(await qrSvg.getAttribute('viewBox'),/^0 0 (\d+) \1$/);
  assert.equal(await qrSvg.locator('path').count(),1);
  assert.equal(await text('#alarm-demo-binding'),'目前綁定：無（將發送至預設對象）');
  assert.equal(await text('#alarm-demo-today'),'今日已觸發：0 位客人');
  assert.equal(await note.isVisible(),false);
  assert.equal((await button.textContent()).trim(),'觸發警報');
 });

 await check('recent list: 5 rows by default, 展開全部（10）/收合 with aria state, capped at 10, target labels',async()=>{
  await load({binding:booth(),recent:sends(12)});
  await qrSvg.waitFor();
  const rows=frame.locator('#alarm-demo-recent li'),visible=frame.locator('#alarm-demo-recent li:visible');
  assert.equal(await rows.count(),10,'list is capped at 10');
  assert.equal(await visible.count(),5);
  assert.equal((await toggle.textContent()).trim(),'展開全部（10）');
  assert.equal(await toggle.getAttribute('aria-expanded'),'false');
  assert.equal(await toggle.getAttribute('aria-controls'),'alarm-demo-recent');
  assert.match(await rows.nth(0).textContent(),/訪客 #12/);
  assert.match(await rows.nth(2).textContent(),/預設對象/);
  await toggle.click();
  assert.equal(await visible.count(),10);
  assert.equal((await toggle.textContent()).trim(),'收合');
  assert.equal(await toggle.getAttribute('aria-expanded'),'true');
  await panelShot('unbound-expanded-1440');
  await toggle.click();
  assert.equal(await visible.count(),5);
  assert.equal(await toggle.getAttribute('aria-expanded'),'false');
 });

 await check('polling every 4 s: masked binding with m:ss countdown, today count, no full username, QR kept for same link',async()=>{
  await load({binding:booth(),recent:sends(3)});
  await qrSvg.waitFor();
  await qrSvg.evaluate(node=>{node.dataset.probe='kept';});
  const gets=state.gets;
  state.binding=booth({current:visitor(),count:2});
  await frame.locator('#alarm-demo-binding').filter({hasText:'@da***'}).waitFor();
  assert.ok(state.gets>gets,'a poll GET happened');
  const first=await text('#alarm-demo-binding');
  assert.match(first,/^目前綁定：@da\*\*\*（剩 6:[45]\d）$/);
  assert.equal(await text('#alarm-demo-today'),'今日已觸發：2 位客人');
  assert.equal(await qrSvg.getAttribute('data-probe'),'kept','QR is not redrawn while deep_link is unchanged');
  assert.ok(!(await frame.locator('#alarm-demo').textContent()).includes('leaked_full_username'),'only the masked display is rendered');
  await delay(2200);
  const later=await text('#alarm-demo-binding');
  assert.ok(remaining(later)<remaining(first),`countdown ticks: ${first} -> ${later}`);
 });

 await check('QR is redrawn when deep_link rotates (bound state screenshot)',async()=>{
  await load({binding:booth({current:visitor(),count:2}),recent:sends(7)});
  await qrSvg.waitFor();
  await qrSvg.evaluate(node=>{node.dataset.probe='old';});
  state.binding={...state.binding,deep_link:L2};
  await frame.locator(`#alarm-demo-qr svg[data-link="${L2}"]`).waitFor();
  assert.equal(await qrSvg.count(),1);
  assert.equal(await qrSvg.getAttribute('data-probe'),null,'a new QR element replaced the old one');
  assert.match(await text('#alarm-demo-binding'),/^目前綁定：@da\*\*\*（剩 \d+:\d\d）$/);
  await panelShot('bound-1440');
 });

 await check('send while a visitor is bound: visitor status with today number and 訪客 #N row',async()=>{
  await load({binding:booth({current:visitor(),count:2}),recent:sends(2),post:{cooldown:0,target:'visitor',number:3}});
  await qrSvg.waitFor();await enabled();
  const before=state.sends;
  await button.click();
  await status.filter({hasText:'已發送給目前綁定的訪客（今天第 3 位）。'}).waitFor();
  assert.equal(state.sends,before+1,'exactly one POST');
  assert.match(await text('#alarm-demo-recent li'),/訪客 #3/);
  assert.equal((await button.textContent()).trim(),'觸發警報');
 });

 await check('send without a binding: default-target status and 預設對象 row',async()=>{
  await load({binding:booth(),post:{cooldown:0,target:'default',number:null}});
  await qrSvg.waitFor();await enabled();
  await button.click();
  await status.filter({hasText:'已發送至預設 Telegram 對象。'}).waitFor();
  assert.match(await text('#alarm-demo-recent li'),/預設對象/);
 });

 await check('bot states starting/webhook_active/conflict/unauthorized/unavailable show a note and hide the QR',async()=>{
  for(const [botState,expected] of [['starting',/啟動中/],['webhook_active',/Webhook/],['conflict',/另有程式/],['unauthorized',/授權失效/],['unavailable',/暫時無法使用/],['something_new',/暫時無法使用/]]){
   await load({binding:booth({state:botState,count:1})});
   await note.waitFor();
   assert.match(await note.textContent(),expected,botState);
   assert.equal(await frame.locator('#alarm-demo-qr').isVisible(),false,botState+' hides the QR');
   assert.equal(await text('#alarm-demo-binding'),'目前綁定：無（將發送至預設對象）',botState);
   assert.equal(await text('#alarm-demo-today'),'今日已觸發：1 位客人',botState);
  }
 });

 await check('a deep_link that is not https://t.me/<bot>?start=<code> is never drawn',async()=>{
  for(const link of ['javascript:alert(1)','https://evil.example/TaistroEmsDemoBot?start=bQ3x9','https://t.me/TaistroEmsDemoBot?start=b"><img src=x>']){
   await load({binding:{...booth(),deep_link:link}});
   await note.filter({hasText:'QR Code 暫時無法顯示'}).waitFor();
   assert.equal(await qrSvg.count(),0,link);
  }
 });

 await check('polling pauses while the page is hidden and resumes immediately when visible',async()=>{
  await load({binding:booth()});
  await qrSvg.waitFor();
  await setVisibility('hidden');
  const gets=state.gets;await delay(5000);
  assert.equal(state.gets,gets,'no GET while hidden');
  await setVisibility('visible');
  await until(()=>state.gets>gets,2000,'a GET right after becoming visible');
 });

 await check('401 during polling shows the login form, hides the QR and stops polling; login resumes it',async()=>{
  await load({binding:booth()});
  await qrSvg.waitFor();
  state.logged=false;
  await frame.locator('#alarm-demo-login').waitFor({state:'visible'});
  assert.equal(await frame.locator('#alarm-demo-booth').isVisible(),false);
  const gets=state.gets;await delay(5000);
  assert.equal(state.gets,gets,'polling stopped after 401');
  await frame.locator('#alarm-demo-password').fill('mock-password-only');
  await frame.locator('#alarm-demo-login button').click();
  await qrSvg.waitFor();
  const resumed=state.gets;await until(()=>state.gets>resumed,6000,'polling after login');
 });

 await check('booth layout: QR 240 px desktop / 180 px at <=650 px, no horizontal overflow at 1440/768/390/320 px',async()=>{
  await load({binding:booth({current:visitor(),count:4}),recent:sends(10)});
  await qrSvg.waitFor();await toggle.click();
  for(const width of [1440,768,390,320]){
   await page.setViewportSize({width,height:1000});await page.waitForTimeout(300);
   const g=await child().evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth,qr:document.querySelector('#alarm-demo-qr svg').getBoundingClientRect().toJSON(),panel:document.querySelector('#alarm-demo').getBoundingClientRect().toJSON()}));
   assert.ok(g.scroll<=g.width+1,'no horizontal overflow '+JSON.stringify(g));
   assert.ok(g.qr.x>=0&&g.qr.right<=g.width&&g.qr.right<=g.panel.right,'QR inside the panel '+JSON.stringify(g));
   const expected=g.width<=650?180:240;
   assert.ok(Math.abs(g.qr.width-expected)<1&&Math.abs(g.qr.height-expected)<1,`QR ${g.qr.width}px at frame width ${g.width}, expected ${expected}`);
   if(width===390)await panelShot('bound-expanded-390');
  }
  await page.setViewportSize({width:1440,height:1000});
 });

 await check('no JavaScript exceptions on the page',async()=>{assert.deepEqual(errors,[]);});
}finally{await browser.close();}
const passed=results.filter(Boolean).length,failed=results.length-passed;
console.log(`SUMMARY alarm-demo.cjs: ${passed} passed, ${failed} failed (all API calls mocked; no real Telegram sent)`);
if(failed)process.exitCode=1;
})().catch(e=>{console.error(e);process.exit(1)});
