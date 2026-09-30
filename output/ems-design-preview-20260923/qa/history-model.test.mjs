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

// FR-1802 / ADR-032: normal sparse samples connect, telemetry gaps stay visible.
const {chartLinePoints}=await import('../public/live/history-model.mjs');
function sampledPoints(seconds,step=2,end=110,key='power_kw'){
 const at=second=>new Date(Date.UTC(2026,0,1)+second*1000).toISOString();
 return chartPoints({since:at(0),until:at(end),bucket_seconds:step,series:seconds.map((s,i)=>({signal:key,time:at(s),value:i,min:i-1,max:i+1,last:key==='pump_on'?i%2:i+10,samples:1,last_time:at(s)}))},key);
}
test('normal 10-second inverter samples form a connected line without invented values',()=>{
 const points=sampledPoints([0,10,20,30,40],2,42),before=structuredClone(points);
 const result=chartLinePoints(points,2);
 assert.deepEqual(result,points.filter(p=>p.value!==null));
 assert.deepEqual(points,before,'source buckets must stay unchanged');
 assert.deepEqual(result.map(p=>p.samples),[1,1,1,1,1]);
});
test('normal jitter connects but a long outage stays broken including range edges',()=>{
 const points=sampledPoints([4,14,26,40,50,90,100]);
 const result=chartLinePoints(points,2);
 assert.deepEqual(result.filter(p=>p.value!==null),points.filter(p=>p.value!==null));
 assert.ok(!result.some(p=>p.value===null&&p.time>points[2].time&&p.time<points[25].time),'normal 10-14 second intervals should connect');
 assert.ok(result.some(p=>p.value===null&&p.time>points[25].time&&p.time<points[45].time),'40 second outage must retain a break');
 assert.equal(result[0].value,null,'no extrapolation before first reading');
 assert.equal(result.at(-1).value,null,'no extrapolation after last reading');
});
test('dense meter gaps and sparse cold-start gaps remain visible',()=>{
 for(const seconds of [[0,2,4,6,12,14],[],[10],[0,10],[0,10,20]]){
  const points=sampledPoints(seconds);
  assert.deepEqual(chartLinePoints(points,2),points);
 }
});
test('counter last values and boolean step states survive sparse line formatting',()=>{
 for(const key of ['energy_kwh','pump_on']){
  const points=sampledPoints([0,10,20,30,40],2,42,key);
  assert.deepEqual(chartLinePoints(points,2),points.filter(p=>p.value!==null));
  assert.equal(chartLinePoints(points,2)[0].value,key==='pump_on'?0:10,'counter/state uses last, never average');
 }
});
test('coarse historical buckets keep the original empty intervals',()=>{
 const points=sampledPoints([0,60,120,180,300],60,360);
 assert.deepEqual(chartLinePoints(points,60),points);
});