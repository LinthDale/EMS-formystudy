const {chromium}=require('C:/Users/User/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try {
 const page=await browser.newPage({viewport:{width:1440,height:1050}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://127.0.0.1:4178/',{waitUntil:'networkidle'});
 await page.waitForSelector('#page-select');
 const names=['Main','Monitor','Demand','Storage','Alarms','Devices','Reports'];
 const results=[];
 for(const name of names){
  await page.selectOption('#page-select',name);
  await page.waitForFunction(n=>document.querySelector('iframe').contentWindow.__dcRootName?.()===n,name);
  const frame=page.frames().find(f=>f.url().includes(name+'.dc.html'));
  await frame.waitForFunction(()=>document.body.innerText.length>300 && !document.body.innerText.includes('{{'));
  assert(!(await frame.locator('body').innerText()).includes('{{'),name+' unresolved template');
  await page.screenshot({path:__dirname+'/'+name+'.png',fullPage:true});
  results.push({page:name,status:'rendered'});
 }
 await page.selectOption('#page-select','Main');
 await page.waitForFunction(()=>document.querySelector('iframe').contentWindow.__dcRootName?.()==='Main');
 await page.selectOption('#scenario','alarm');
 const main=page.frames().find(f=>f.url().includes('Main.dc.html'));
 await main.waitForFunction(()=>!document.body.innerText.includes('目前無警示事件'));
 await main.getByRole('link',{name:'需量管理',exact:true}).click();
 await page.waitForFunction(()=>document.querySelector('#page-select').value==='Demand');
 await page.setViewportSize({width:390,height:844});
 await page.screenshot({path:__dirname+'/mobile.png',fullPage:true});
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'mobile shell overflow');
 assert.deepEqual(errors,[],'browser errors');
 console.log(JSON.stringify({results,alarmScenario:'passed',sidebarNavigation:'passed',mobileShell:'passed',errors},null,2));
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
