import test from 'node:test';
import assert from 'node:assert/strict';
import {rangeFor,chartPoints,latestSignals,toCsv} from '../public/live/history-model.mjs';
test('relative range and timezone custom bounds',()=>{
 const r=rangeFor('3600','','',Date.parse('2026-09-23T10:00:00Z'));
 assert.equal(r.since,'2026-09-23T09:00:00.000Z');assert.equal(r.until,'2026-09-23T10:00:00.000Z');
 assert.throws(()=>rangeFor('custom','2026-01-01','2026-02-01'),/7/);
 assert.throws(()=>rangeFor('custom','',''),/時間/);
});
test('chart preserves gaps, min/max and last counter values',()=>{
 const data={since:'2026-01-01T00:00:00Z',until:'2026-01-01T00:00:03Z',bucket_seconds:1,series:[
 {signal:'power_kw',time:'2026-01-01T00:00:00Z',value:12,min:1,max:40,last:15,last_time:'2026-01-01T00:00:00Z',samples:3},
 {signal:'energy_kwh',time:'2026-01-01T00:00:00Z',value:12,min:1,max:40,last:40,last_time:'2026-01-01T00:00:00Z',samples:3}]};
 const a=chartPoints(data,'power_kw');assert.equal(a.length,3);assert.equal(a[0].value,12);assert.equal(a[0].max,40);assert.equal(a[1].value,null);
 assert.equal(chartPoints(data,'energy_kwh')[0].value,40);
 assert.equal(latestSignals(data.series).power_kw.last,15);
});
test('CSV uses fixed columns and escapes content',()=>{
 const csv=toCsv([{time:'2026-01-01T00:00:00Z',power_kw:3,pump_on:false}],['power_kw','pump_on']);
 assert.match(csv,/"3","false"/);assert.match(csv,/time,power_kw,pump_on/);
});
