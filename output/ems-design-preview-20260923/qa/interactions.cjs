const {chromium}=require('C:/Users/User/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({channel:'msedge',headless:true});try{
 const page=await browser.newPage({viewport:{width:1440,height:1080}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://127.0.0.1:4178/#Storage');
 await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('原稿'));
 let frame=page.frames().find(f=>f.url().includes('Storage.dc.html'));
 const scenarios=[];
 for(const mode of ['GRID_TIE','STANDBY','ISLAND','FAULT']){await page.selectOption('#scenario',mode);await frame.waitForFunction(m=>document.body.innerText.includes(m),mode);scenarios.push(mode);}
 await page.screenshot({path:__dirname+'/Storage-fault.png',fullPage:true});
 await page.selectOption('#page-select','Main');await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('原稿'));
 frame=page.frames().find(f=>f.url().includes('Main.dc.html'));
 await page.selectOption('#scenario','alarm');await frame.waitForFunction(()=>!document.body.innerText.includes('目前無警示事件'));
 await page.selectOption('#scenario','normal');await frame.getByText('目前無警示事件',{exact:true}).waitFor();
 await page.screenshot({path:__dirname+'/Main.png',fullPage:true});
 await page.setViewportSize({width:390,height:844});await page.screenshot({path:__dirname+'/mobile.png',fullPage:true});
 await page.selectOption('#zoom','1');assert(await page.locator('#viewport').evaluate(e=>e.scrollWidth>e.clientWidth),'100% allows canvas horizontal scrolling');
 assert.deepEqual(errors,[]);console.log(JSON.stringify({storageModes:scenarios,mainAlarmReset:'passed',zoom:'passed',errors},null,2));
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exit(1)});
