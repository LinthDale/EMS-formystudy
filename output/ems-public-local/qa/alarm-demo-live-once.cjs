const {chromium}=require('C:/Users/User/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const base='https://synaiq-ai.com/ems/';
(async()=>{const browser=await chromium.launch({channel:'msedge',headless:true});try{
 const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 page.on('console',m=>{if(m.type()==='error'&&m.text().includes('Content Security Policy'))errors.push(m.text());});
 const credentials=JSON.parse(fs.readFileSync(path.resolve(__dirname,'../../../.local/ems-preview-login.json'),'utf8'));
 await page.goto(base+'#Alarms');const frame=page.frameLocator('#screen');
 await frame.locator('#alarm-demo-login').waitFor({state:'visible'});
 await frame.locator('#alarm-demo-username').fill(credentials.username);
 await frame.locator('#alarm-demo-password').fill(credentials.password);
 await frame.locator('#alarm-demo-login button').click();
 await page.waitForFunction(()=>document.querySelector('#screen').contentDocument.querySelector('#alarm-demo-trigger')?.disabled===false);
 assert.equal(await frame.locator('#alarm-demo-password').inputValue(),'');
 // The marker is intentionally written before clicking. Do not rerun after an uncertain outcome.
 const marker=path.join(__dirname,'alarm-demo-live-attempt.json');
 fs.writeFileSync(marker,JSON.stringify({startedAt:new Date().toISOString(),url:base+'#Alarms'}),{flag:'wx'});
 const responseWait=page.waitForResponse(r=>r.url().endsWith('/api/alarms/demo')&&r.request().method()==='POST');
 await frame.locator('#alarm-demo-trigger').click();
 const response=await responseWait;
 const data=await response.json();
 fs.writeFileSync(path.join(__dirname,'alarm-demo-live-result.json'),JSON.stringify({httpStatus:response.status(),...data},null,2));
 assert.equal(response.status(),200);assert.equal(data.status,'sent');assert.equal(data.channel,'telegram');
 await frame.locator('#alarm-demo-status').filter({hasText:'已發送至 Telegram'}).waitFor();
 assert.equal(await frame.locator('#alarm-demo-trigger').isDisabled(),true);
 assert.equal(await frame.locator('#alarm-demo-recent li').filter({hasText:data.event_id.slice(0,8)}).count(),1);
 await page.screenshot({path:path.join(__dirname,'alarm-demo-live-desktop.png'),fullPage:true});
 await page.reload();await frame.locator('#alarm-demo-recent li').waitFor();
 for(const width of [390,320]){
  await page.setViewportSize({width,height:844});await page.waitForTimeout(200);
  const child=page.frames().find(f=>f.url().includes('Alarms.dc.html'));
  assert.ok(await child.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  if(width===390)await page.screenshot({path:path.join(__dirname,'alarm-demo-live-mobile.png'),fullPage:true});
 }
 assert.deepEqual(errors,[]);
 console.log(JSON.stringify({verified:'One real Telegram demo sent through public EMS UI',httpStatus:response.status(),event_id:data.event_id,sent_at:data.sent_at,desktop:true,mobile:[320,390],reloadHistory:true}));
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
