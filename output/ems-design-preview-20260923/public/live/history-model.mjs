export const METRICS=Object.freeze({
 power_kw:['有效功率','kW','#647956'],voltage:['電壓','V','#927344'],current:['電流','A','#547a86'],energy_kwh:['累計電量','kWh','#707b57'],
 temperature:['溫度','°C','#a66d4e'],humidity:['濕度','%RH','#547a86'],motor_speed:['馬達轉速','RPM','#927344'],pressure:['壓力','kPa','#647956'],
 pump_on:['幫浦狀態','','#647956'],valve_open:['閥門狀態','','#547a86']
});
export const isState=key=>key==='pump_on'||key==='valve_open';
export const fmt=value=>typeof value==='number'&&Number.isFinite(value)?value.toLocaleString('zh-TW',{maximumFractionDigits:2}):'—';
export function displayValue(key,value){return isState(key)?value===1?'開啟':value===0?'關閉':'—':fmt(value);}
export function deviceLabel(id){const name={plc:'工控電腦',sim:'電表',sensor:'感測器'}[id.split('-')[0]];return name?name+'（'+id+'）':id;}
export function rangeFor(mode,from,to,now=Date.now()){
 const end=mode==='custom'?Date.parse(to):now;
 const start=mode==='custom'?Date.parse(from):end-Number(mode)*1000;
 if(!Number.isFinite(start)||!Number.isFinite(end)||end<=start)throw Error('請填入有效的開始與結束時間。');
 if(end-start>7*86400000)throw Error('單次查詢最多 7 天，請縮短時間範圍。');
 return {since:new Date(start).toISOString(),until:new Date(end).toISOString()};
}
export function latestSignals(series){const latest={};for(const row of series){if(!METRICS[row.signal])continue;if(!latest[row.signal]||Date.parse(row.last_time)>Date.parse(latest[row.signal].last_time))latest[row.signal]=row;}return latest;}
export function chartPoints(data,key){
 const rows=new Map(data.series.filter(r=>r.signal===key).map(r=>[Date.parse(r.time),r]));
 const points=[];const step=data.bucket_seconds*1000;
 for(let t=Date.parse(data.since);t<Date.parse(data.until);t+=step){const row=rows.get(t);points.push({time:t,value:row?(isState(key)||key==='energy_kwh'?row.last:row.value):null,min:row?.min??null,max:row?.max??null,samples:row?.samples??0});if(points.length>1201)throw Error('圖表資料超過限制');}
 return points;
}
// Skip only the empty buckets between normal samples; retain longer gaps and range edges.
export function chartLinePoints(points,bucketSeconds){
 const actual=points.filter(p=>p.value!==null);
 if(actual.length<4)return points;
 const intervals=actual.slice(1).map((p,i)=>p.time-actual[i].time).sort((a,b)=>a-b);
 const cadence=intervals[Math.floor((intervals.length-1)/2)];
 if(cadence<=bucketSeconds*1000)return points;
 const maxGap=cadence*1.5;
 let previous=null,nextIndex=0;
 return points.filter(point=>{
  if(point.value!==null){previous=point;nextIndex++;return true;}
  const next=actual[nextIndex];
  return !previous||!next||next.time-previous.time>maxGap;
 });
}
export function toCsv(rows,keys){
 const escape=v=>'"'+String(v??'').replaceAll('"','""')+'"';
 return ['time,'+keys.join(','),...rows.map(r=>[r.time,...keys.map(k=>r[k])].map(escape).join(','))].join('\r\n');
}
