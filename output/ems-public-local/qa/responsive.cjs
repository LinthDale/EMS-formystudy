const {chromium}=require('C:/Users/User/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('node:fs');const assert=require('node:assert/strict');
const base=process.argv[2]||'http://127.0.0.1:4178/';
(async()=>{const browser=await chromium.launch({channel:'msedge',headless:true});try{
const page=await browser.newPage();const results=[],errors=[];page.on('pageerror',e=>errors.push(e.message));
for(const width of (process.argv[3]?process.argv[3].split(",").map(Number):[1920,1366,1024,768,390])){
 await page.setViewportSize({width,height:width<650?844:1000});
 for(const name of ['Main','Demand','Storage','Alarms','Devices','Reports']){
  await page.goto(base+'#'+name);
  await page.waitForFunction(n=>{const w=document.querySelector('#screen').contentWindow;return w.__dcRootName?.()===n&&!!w.document.querySelector('.ems-board')&&!!w.__dcRegistry?.[n]?.Logic;},name,{timeout:20000});const frame=page.frameLocator('#screen');await frame.locator('.ems-main').waitFor();
  await page.waitForTimeout(550);
  const f=page.frames().find(f=>f.url().includes('/boards/'));
  const result=await f.evaluate(()=>{
   const rect=e=>{const b=e.getBoundingClientRect();return {x:Math.round(b.x),y:Math.round(b.y),w:Math.round(b.width),h:Math.round(b.height)}};
   const overflow=[...document.querySelectorAll('.ems-board *')].filter(e=>{
    const b=e.getBoundingClientRect();if(!b.width||!b.height||getComputedStyle(e).position==='absolute')return false;
    if(e.closest('.ems-data-table,.ems-nav-items'))return false;
    return b.right>innerWidth+2||b.left< -2;
   }).slice(0,12).map(e=>({tag:e.tagName,cls:e.className?.baseVal??e.className,text:e.textContent.trim().slice(0,40),...rect(e)}));
   return {vw:innerWidth,sw:document.documentElement.scrollWidth,root:rect(document.querySelector('.ems-board')),panels:[...document.querySelectorAll('.ems-panel')].map(e=>({id:e.getAttribute('aria-labelledby'),...rect(e)})),overflow};
  });
  if(result.sw>width)console.log(JSON.stringify(result));assert.equal(result.sw,width,name+' has horizontal page overflow at '+width);assert.equal(result.root.w,width,name+' does not fill viewport');results.push({width,name,...result});console.log(JSON.stringify({width,name,sw:result.sw,root:result.root,overflow:result.overflow}));
  if([1920,390].includes(width))await page.screenshot({path:__dirname+'/rwd-'+width+'-'+name+'.png',fullPage:true});
 }
}
assert.deepEqual(errors,[]);console.log('PASS: six pages fill five viewport sizes without page overflow or JavaScript exceptions');fs.writeFileSync(__dirname+'/responsive-results.json',JSON.stringify(results,null,2));
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
