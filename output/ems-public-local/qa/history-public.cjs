const {chromium}=require('C:/Users/User/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({channel:'msedge',headless:true});try{
 const c=await browser.newContext({viewport:{width:1500,height:1100},acceptDownloads:true});const p=await c.newPage(),errors=[],api=[];
 p.on('pageerror',e=>errors.push(e.message));p.on('response',r=>{if(r.url().includes('/api/'))api.push([r.status(),new URL(r.url()).pathname]);});
 await p.goto('https://synaiq-ai.com/ems/?revision=public-v1#Monitor');const f=p.frameLocator('#screen');
 await f.locator('#username').waitFor();const creds=JSON.parse(fs.readFileSync(path.resolve(__dirname,'../../../.local/ems-preview-login.json'),'utf8'));
 await f.locator('#username').fill(creds.username);await f.locator('#password').fill(creds.password);await f.getByRole('button',{name:'登入並連接'}).click();
 await f.locator('.trend').first().waitFor({timeout:30000});assert.equal(await f.locator('.trend').count(),4);
 console.log('INITIAL',await f.locator('#connection').innerText(),await f.locator('#cards').innerText());
 await f.locator('#auto').selectOption('5000');
 const before=await f.locator('#updated').innerText();await p.waitForTimeout(6200);const after=await f.locator('#updated').innerText();assert.notEqual(before,after);console.log('POLL',before,'=>',after);
 await f.locator('#auto').selectOption('0');await f.locator('#period').selectOption('86400');
 await f.locator('#resolution').filter({hasText:'144 秒'}).waitFor();assert.equal(await f.locator('#table-body tr').count(),100);
 const firstPage=await f.locator('#table-body tr').first().innerText();await f.locator('#next').click();await f.locator('#page-label').filter({hasText:'第 2 頁'}).waitFor();
 const secondPage=await f.locator('#table-body tr').first().innerText();assert.notEqual(firstPage,secondPage);console.log('PAGES',firstPage,'=>',secondPage);
 const pending=p.waitForEvent('download');await f.locator('#export').click();const download=await pending;const file=await download.path();assert.equal(fs.readFileSync(file,'utf8').trim().split(/\r?\n/).length,101);console.log('CSV',download.suggestedFilename());
 await f.locator('#period').selectOption('604800');await f.locator('#resolution').filter({hasText:'1008 秒'}).waitFor();
 for(const [id,n]of [['plc-001',6],['sensor-001',2]]){await f.locator('#device').selectOption(id);await f.locator('.trend').first().waitFor();assert.equal(await f.locator('.trend').count(),n);console.log('DEVICE',id,await f.locator('#cards').innerText());}
 await f.locator('#device').selectOption('sim-001');await f.locator('.trend').first().waitFor();await f.locator('#period').selectOption('3600');await f.locator('#resolution').filter({hasText:'6 秒'}).waitFor();
 await p.screenshot({path:__dirname+'/history-public-desktop.png',fullPage:true});
 await f.locator('#device').selectOption('plc-001');await f.locator('.trend').first().waitFor();await p.screenshot({path:__dirname+'/history-public-plc.png',fullPage:true});
 await f.locator('#period').selectOption('custom');await f.locator('#from').fill('2001-01-01T00:00');await f.locator('#to').fill('2001-01-01T01:00');await f.locator('#custom-range button').click();await f.locator('#connection').filter({hasText:'沒有資料'}).waitFor();assert.equal(await f.locator('.trend').count(),0);
 await f.locator('#period').selectOption('900');await f.locator('.trend').first().waitFor();await p.setViewportSize({width:390,height:844});await p.waitForTimeout(200);const frame=p.frames().find(x=>x.url().includes('/live/Monitor.html'));assert.ok(await frame.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'mobile iframe fits');
 await p.screenshot({path:__dirname+'/history-public-mobile.png',fullPage:true});assert.deepEqual(errors,[]);
 console.log('API',JSON.stringify(api));assert.ok(!api.some(([status])=>status>=500));
 
 console.log('PASS real history: login, three devices, advancing samples, 24h/7d range, raw pagination, 100-row CSV, empty custom range, mobile.');
 }finally{await browser.close()}})().catch(e=>{console.error(e);process.exit(1)});


