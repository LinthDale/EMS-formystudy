// Local-only verification. Credentials remain in .local and are never printed.
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require('playwright');
(async()=>{
 const root=path.resolve(__dirname,'../../..');
 const credentials=JSON.parse(fs.readFileSync(path.join(root,'.local/ems-preview-login.json'),'utf8'));
 const browser=await chromium.launch({headless:true,channel:process.env.DELTA_TEST_BROWSER || 'msedge'});
 try {
  const page=await browser.newPage({viewport:{width:1440,height:1100}});
  const errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:4178/live/Monitor.html');
  await page.locator('#username').fill(credentials.username);
  await page.locator('#password').fill(credentials.password);
  await page.locator('#login-form button[type=submit]').click();
  await page.locator('#device option[value="delta-sim-001"]').waitFor({state:'attached'});
  await page.locator('#device').selectOption('delta-sim-001');
  await page.waitForFunction(()=>document.querySelector('#table-body')?.children.length>0
    && document.querySelector('#message')?.textContent.includes('delta-sim-001'));
  await page.waitForFunction(()=>[...document.querySelectorAll('.trend')].every(el=>{const c=echarts.getInstanceByDom(el);const series=c?.getOption()?.series?.[0];return series?.showSymbol&&series.data.some(p=>p[1]!==null)}));
  const state=await page.locator('#connection').textContent();
  const label=await page.locator('#device option:checked').textContent();
  const cards=await page.locator('#cards').innerText();
  const records=await page.locator('#table-body tr').count();
  if(label!=='太陽能逆變器(delta-sim-001)'||!records||errors.length)
   throw Error('Delta UI acceptance failed');
  const out=path.join(root,'output/delta-verification');
  fs.mkdirSync(out,{recursive:true});
  await page.screenshot({path:path.join(out,'monitor.png'),fullPage:true});
  fs.writeFileSync(path.join(out,'ui-result.json'),JSON.stringify({state,label,cards,records,errors},null,2));
  console.log(JSON.stringify({state,label,cards,records,errors},null,2));
 } finally {await browser.close();}
})().catch(e=>{console.error(e.message);process.exitCode=1;});
