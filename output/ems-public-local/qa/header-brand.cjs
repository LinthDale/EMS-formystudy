const {chromium}=require('C:/Users/User/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const root=path.resolve(__dirname,'../../..'),base=process.argv[2]||'http://127.0.0.1:4178/';
(async()=>{const b=await chromium.launch({channel:'msedge',headless:true});try{
 const p=await b.newPage(),errors=[];p.on('pageerror',e=>errors.push(e.message));
 async function ready(name){await p.waitForFunction(name=>{const w=document.querySelector('#screen').contentWindow;return name==='Monitor'?w.location.pathname.endsWith('/live/Monitor.html')&&!!w.document.querySelector('.ems-product-logo'):w.__dcRootName?.()===name&&!!w.__dcRegistry?.[name]?.Logic;},name);}
 for(const name of ['Main','Monitor','Demand','Storage','Alarms','Devices','Reports']){
  for(const width of [1920,1024,768,390,320]){
   await p.setViewportSize({width,height:900});await p.goto(base+'#'+name);await ready(name);
   const child=p.frames().find(f=>f.url().includes(name==='Monitor'?'live/Monitor.html':'boards/'+name+'.dc.html'));
   await child.evaluate(async()=>{await document.fonts.ready;await document.querySelector('.ems-product-logo').decode()});await p.waitForTimeout(100);
   const result=await child.evaluate(()=>{const rect=e=>e.getBoundingClientRect().toJSON();return {width:innerWidth,scroll:document.documentElement.scrollWidth,header:rect(document.querySelector('.ems-header')),logo:rect(document.querySelector('.ems-product-logo')),brand:rect(document.querySelector('.ems-brand')),actions:rect(document.querySelector('.ems-header-actions'))}});
   assert.equal(result.scroll,width,name+' '+JSON.stringify(result));assert.ok(result.actions.right<=width&&result.logo.right<=width,name+' '+JSON.stringify(result));
   if(name==='Monitor'&&[1920,390].includes(width))await child.locator('.ems-header').screenshot({path:path.join(__dirname,'monitor-header-'+width+'-20260929.png')});
  }
  console.log('PASS responsive common header',name);
 }
 if(!process.argv.includes('--no-auth')){
  await p.setViewportSize({width:1440,height:1000});await p.goto(base+'#Monitor');await ready('Monitor');const f=p.frameLocator('#screen');
  await f.locator('#login-panel').waitFor({state:'visible'});await f.locator('#header-account summary').click();await f.locator('#header-login').click();
  assert.equal(await f.locator('#username').evaluate(el=>el===document.activeElement),true);
  const creds=JSON.parse(fs.readFileSync(path.join(root,'.local/ems-preview-login.json'),'utf8'));
  await f.locator('#username').fill(creds.username);await f.locator('#password').fill(creds.password);await f.getByRole('button',{name:'登入並連接'}).click();
  await f.locator('.trend').first().waitFor({timeout:30000});assert.equal(await f.locator('#session-name').innerText(),creds.username);assert.equal(await f.locator('#session-role').innerText(),'維運 · OPS');
  await f.locator('#auto').selectOption('0');
  await p.setViewportSize({width:320,height:844});await p.waitForTimeout(100);await f.locator('#header-account summary').click();await f.locator('#logout').waitFor({state:'visible'});
  const menu=await f.locator('.ems-account-options').boundingBox();assert.ok(menu.x>=0&&menu.x+menu.width<=320);await f.locator('#logout').click();
  await f.locator('#login-panel').waitFor({state:'visible'});assert.equal(await f.locator('#session-name').innerText(),'尚未登入');assert.equal(await f.locator('.trend').count(),0);
  console.log('PASS live session: header login focus, actual account and charts, mobile dropdown, logout clears session and charts');
 }
 assert.deepEqual(errors,[]);
}finally{await b.close()}})().catch(e=>{console.error(e);process.exit(1)});
