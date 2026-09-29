const {chromium}=require('C:/Users/User/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({channel:'msedge',headless:true});try{
 const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];let sent=0;
 page.on('pageerror',e=>errors.push(e.message));
 page.on('request',r=>{if(r.url().endsWith('/api/alarms/demo')&&r.method()==='POST')sent++;});
 page.on('console',m=>{if(m.type()==='error'&&m.text().includes('Content Security Policy'))errors.push(m.text());});
 const credentials=JSON.parse(fs.readFileSync(path.resolve(__dirname,'../../../.local/ems-preview-login.json'),'utf8'));
 const delivered=JSON.parse(fs.readFileSync(path.join(__dirname,'alarm-demo-live-result.json'),'utf8'));
 await page.goto('https://synaiq-ai.com/ems/#Alarms');const frame=page.frameLocator('#screen');
 await frame.locator('#alarm-demo-login').waitFor({state:'visible'});
 await frame.locator('#alarm-demo-password').fill(credentials.password);await frame.locator('#alarm-demo-login button').click();
 const event=frame.locator('#alarm-demo-recent li').filter({hasText:delivered.event_id.slice(0,8)});
 await event.waitFor();assert.equal(await event.count(),1);
 const child=page.frames().find(f=>f.url().includes('Alarms.dc.html'));
 const status=await child.evaluate(async()=>{const r=await fetch('../api/alarms/demo');return r.json()});
 assert.equal(status.configured,true);assert.ok(status.recent.some(x=>x.event_id===delivered.event_id));
 await page.screenshot({path:path.join(__dirname,'alarm-demo-live-desktop.png'),fullPage:true});
 await page.reload();await event.waitFor();
 for(const width of [390,320]){
  await page.setViewportSize({width,height:844});await page.waitForTimeout(200);
  const current=page.frames().find(f=>f.url().includes('Alarms.dc.html'));
  assert.ok(await current.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  if(width===390)await page.screenshot({path:path.join(__dirname,'alarm-demo-live-mobile.png'),fullPage:true});
 }
 assert.equal(sent,0);assert.deepEqual(errors,[]);
 console.log(JSON.stringify({verified:'Existing real event present after reload; no resend',event_id:delivered.event_id,records:status.recent.map(x=>({event_id:x.event_id,sent_at:x.sent_at})),mobile:[320,390]}));
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
