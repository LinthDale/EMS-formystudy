const {chromium}=require('C:/Users/User/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const assert=require('node:assert/strict');
(async()=>{const b=await chromium.launch({channel:'msedge',headless:true});try{
 const p=await b.newPage({viewport:{width:1920,height:1000}});const errors=[];p.on('pageerror',e=>errors.push(e.message));
 await p.goto('https://synaiq-ai.com/ems/#Reports');const f=p.frameLocator('#screen');await f.locator('.ems-chart').waitFor();
 await f.getByRole('radio',{name:'日報',exact:true}).click();await f.locator('#repTitle').filter({hasText:'日報'}).waitFor();
 for(const width of [390,1440,768]){
  await p.setViewportSize({width,height:900});
  await p.waitForFunction(()=>{const doc=document.querySelector('#screen').contentDocument;const chart=doc.querySelector('.ems-chart'),svg=chart?.querySelector('svg[role=img]');return svg&&Math.abs(Number(svg.getAttribute('width'))-(chart.getBoundingClientRect().width-72))<2;});
  assert.match(await f.locator('#repTitle').innerText(),/日報/);
  const hit=f.locator('.ems-chart>div[style*="cursor: crosshair"]');await hit.hover({position:{x:40,y:70}});
  await f.locator('.ems-chart [role=status]').waitFor();
  const tip=await f.locator('.ems-chart [role=status]').boundingBox();assert.ok(tip.x>=0&&tip.x+tip.width<=width+1,'tooltip stays visible');
 }
 assert.deepEqual(errors,[]);console.log('PASS live viewport resizing, responsive chart geometry, report selection retained, visible hover details');
}finally{await b.close()}})().catch(e=>{console.error(e);process.exit(1)});
