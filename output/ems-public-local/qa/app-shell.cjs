const {chromium}=require('C:/Users/User/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const assert=require('node:assert/strict');
const base=process.argv[2]||'http://127.0.0.1:4178/';const publicSite=base.startsWith('https:');
(async()=>{const browser=await chromium.launch({channel:'msedge',headless:true});try{
 const page=await browser.newPage({viewport:{width:1500,height:1000}}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 if(publicSite)page.on('console',m=>{if(m.type()==='error'&&!(m.text().includes('401 (Unauthorized)')&&/\/api\/(auth\/session|alarms\/demo)$/.test(m.location().url)))errors.push(m.text());});
 await page.goto(base+'#Main');
 async function rendered(name){await page.waitForFunction(n=>{const w=document.querySelector('#screen').contentWindow;return w.__dcRootName?.()===n&&!!w.__dcRegistry?.[n]?.Logic;},name,{timeout:20000});}
 async function click(name){await page.frameLocator('#screen').locator('a[href$="'+name+'.dc.html"]').first().click();}
 await rendered('Main');
 assert.equal(await page.locator('.toolbar,#page-select,#zoom,#scenario,.notice').count(),0);
 assert.equal((await page.locator('#screen').boundingBox()).y,0);
 assert.ok(!(await page.locator('body').innerText()).includes('設計預覽'));
 assert.ok((await page.frameLocator('#screen').locator('body').innerText()).includes('示意資料'));
 for(const name of ['Demand','Storage','Alarms','Devices','Reports','Main']){
  await click(name);await rendered(name);assert.equal(new URL(page.url()).hash,'#'+name);console.log('NAV',name);
 }
 await page.screenshot({path:__dirname+'/app-shell-'+(publicSite?'public':'local')+'.png',fullPage:true});
 await click('Monitor');const frame=page.frameLocator('#screen');await frame.locator('#login-form').waitFor({state:'visible'});
 assert.equal(new URL(page.url()).hash,'#Monitor');await click('Main');await rendered('Main');
 await page.goBack();await frame.locator('#login-form').waitFor({state:'visible'});assert.equal(new URL(page.url()).hash,'#Monitor');
 await page.reload();await frame.locator('#login-form').waitFor({state:'visible'});assert.equal(new URL(page.url()).hash,'#Monitor');
 await page.setViewportSize({width:390,height:844});await page.waitForTimeout(250);
 const monitor=page.frames().find(f=>f.url().includes('live/Monitor.html'));assert.ok(await monitor.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
 assert.deepEqual(errors,[]);console.log('PASS: no preview shell, in-app sidebar navigation, browser back, direct Monitor refresh, mobile');
 }finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});

