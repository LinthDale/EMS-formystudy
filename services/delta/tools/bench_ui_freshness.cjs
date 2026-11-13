// Monitor contract verification using intercepted synthetic API responses.
// No credentials, database writes, screenshots, or shared service changes.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const {chromium} = require('playwright');
const origin = 'http://127.0.0.1:4178';
const scenarios = [
  {name:'fresh', ageMs:2000, expected:'live'},
  {name:'historical-backlog-with-fresh-registry', ageMs:120000, expected:'stale'},
  {name:'future-measurement', ageMs:-120000, expected:'stale'},
  {name:'empty', ageMs:2000, expected:'empty'},
  {name:'backend-error', ageMs:2000, expected:'error'},
];

async function main() {
  assert.equal(process.argv.length, 3, 'provide a new evidence directory');
  const out = path.resolve(process.argv[2]);
  fs.mkdirSync(out);
  const results = [];
  let browser, error = null, completed = false, sourceVerified = false, cleanup = false;
  try {
    browser = await chromium.launch({headless:true,channel:'msedge'});
    for (const scenario of scenarios) {
      const page = await browser.newPage({viewport:{width:1440,height:1100}});
      const errors = [], writes = [];
      page.on('pageerror', e => errors.push(e.message));
      const now = Date.now(), sampled = new Date(now-scenario.ageMs).toISOString();
      await page.route('**/api/**', async route => {
        const request=route.request(), u=new URL(request.url());
        if(request.method()!=='GET') {writes.push(u.pathname);await route.abort();return;}
        let data;
        if(u.pathname==='/api/auth/session') data={username:'isolated-qa',role:'ops'};
        else if(u.pathname==='/api/devices') data=[{device_id:'delta-sim-001',last_seen_at:new Date(now).toISOString()}];
        else if(u.pathname.endsWith('/history')) {
          if(scenario.name==='backend-error') {await route.fulfill({status:502,json:{detail:'controlled unavailable'}});return;}
          const since=u.searchParams.get('since'), until=u.searchParams.get('until');
          const bucket=2, anchor=Date.parse(since);
          const time=new Date(anchor+Math.floor((Date.parse(sampled)-anchor)/2000)*2000).toISOString();
          const values={power_kw:9,voltage:230,current:13,energy_kwh:655.38};
          const series=scenario.name==='empty'?[]:Object.entries(values).map(([signal,value])=>({
            signal,time,last_time:sampled,value,last:value,min:value,max:value,samples:1}));
          data={device_id:'delta-sim-001',since,until,bucket_seconds:bucket,series};
        } else if(u.pathname.endsWith('/records')) data={has_more:false,rows:scenario.name==='empty'?[]:[{
          time:sampled,power_kw:9,voltage:230,current:13,energy_kwh:655.38}]};
        else {await route.abort();return;}
        await route.fulfill({json:data});
      });
      try {
        await page.goto(origin+'/live/Monitor.html');
        await page.waitForFunction(()=>['live','stale','empty','error'].includes(document.querySelector('#connection')?.dataset.state));
        const record=await page.evaluate(()=>({
          state:document.querySelector('#connection').dataset.state,
          label:document.querySelector('#connection').textContent,
          device:document.querySelector('#device option:checked')?.textContent,
          cards:document.querySelector('#cards').innerText,
          rawRows:document.querySelectorAll('#table-body tr').length,
          chartCount:document.querySelectorAll('.trend').length,
          chartValues:Object.fromEntries([...document.querySelectorAll('.trend')].map(e=>[
            e.dataset.signal,(window.echarts.getInstanceByDom(e)?.getOption().series[0]?.data || [])
              .filter(p=>p[1]!==null).map(p=>p[1])])),
          rawCells:[...document.querySelectorAll('#table-body tr:first-child td')].slice(1).map(e=>e.textContent),
          values:Object.fromEntries([...document.querySelectorAll('[data-metric]')].map(e=>[e.dataset.metric,e.textContent])),
          updated:document.querySelector('#updated').textContent,
        }));
        record.scenario=scenario.name;
        record.expected_state=scenario.expected;
        record.fixture_measurement_time=sampled;
        record.fixture_registry_last_seen_at=new Date(now).toISOString();
        record.errors=errors; record.writes=writes;
        record.passed=record.state===scenario.expected && errors.length===0 && writes.length===0;
        if(['fresh','historical-backlog-with-fresh-registry'].includes(scenario.name))
          record.passed &&= record.rawRows===1 && record.chartCount===4
            && Object.entries({voltage:'230',current:'13',power_kw:'9',energy_kwh:'655.38'})
              .every(([key,value])=>record.values[key]===value
                && record.chartValues[key]?.length===1 && record.chartValues[key][0]===Number(value))
            && JSON.stringify(record.rawCells)===JSON.stringify(['9','230','13','655.38']);
        results.push(record);
        assert.ok(record.passed, scenario.name+' freshness contract failed');
      } finally {await page.close();}
    }
    const source={};
    const context=await browser.newContext();
    try {
      for(const name of ['Monitor.html','history-live.mjs','history-model.mjs','charts.mjs']) {
        const response=await context.request.get(origin+'/live/'+name);
        assert.ok(response.ok());
        const bytes=await response.body();
        fs.writeFileSync(path.join(out,name),bytes);
        source[name]=crypto.createHash('sha256').update(bytes).digest('hex');
      }
    } finally {await context.close();}
    fs.writeFileSync(path.join(out,'source-sha256.json'),JSON.stringify(source,null,2));
    sourceVerified = true;
    completed = true;
  } catch(e) {
    error = e.stack || String(e);
  } finally {
    try {if(browser) await browser.close(); cleanup = true;}
    catch(e) {error = [error,e.stack || String(e)].filter(Boolean).join('\n');}
    const passed = completed && sourceVerified && cleanup && !error
      && results.length===scenarios.length && results.every(r=>r.passed);
    fs.writeFileSync(path.join(out,'result.json'),JSON.stringify({
      scope:'Local 4178 Monitor with intercepted synthetic API, not live ingest or public site',
      scenarios:results,completed,source_verified:sourceVerified,cleanup,error,passed,
    },null,2));
    if(!passed) process.exitCode = 1;
  }
  console.log(JSON.stringify(results.map(r=>({scenario:r.scenario,state:r.state,passed:r.passed}))));
}
main().catch(e=>{console.error(e.message);process.exitCode=1;});
