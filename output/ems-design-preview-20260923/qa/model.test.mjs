import {test} from 'node:test';
import assert from 'node:assert/strict';
import {normaliseRows, statusFor, seriesPath} from '../public/live/model.mjs';
test('sorts samples without mutation and rejects another device',()=>{const a=[{device_id:'sim-001',time:'2026-09-23T00:00:02Z',power_kw:12},{device_id:'sim-001',time:'2026-09-23T00:00:01Z',power_kw:null},{device_id:'other',time:'2026-09-23T00:00:03Z',power_kw:99}];const b=normaliseRows(a,'sim-001');assert.equal(b.length,2);assert.equal(b[0].power_kw,null);assert.equal(a[0].power_kw,12)});
test('rejects malformed payload; never manufactures zeroes',()=>{assert.throws(()=>normaliseRows({},'sim-001'));assert.equal(normaliseRows([{device_id:'sim-001',time:'bad',power_kw:12}],'sim-001').length,0)});
test('distinguishes empty stale and live',()=>{assert.equal(statusFor([],100000,30000),'empty');assert.equal(statusFor([{time:new Date(0).toISOString()}],100000,30000),'stale');assert.equal(statusFor([{time:new Date(90000).toISOString()}],100000,30000),'live')});
test('chart breaks at missing samples',()=>{const rows=[1,null,3].map((v,i)=>({time:new Date(i*1000).toISOString(),power_kw:v}));assert.equal((seriesPath(rows,'power_kw',100,100).path.match(/M/g)||[]).length,2)});
