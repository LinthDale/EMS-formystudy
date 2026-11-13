import {METRICS,isState,displayValue,chartPoints,chartLinePoints,fmt} from './history-model.mjs';
const instances=new Map();
const when=t=>new Date(t).toLocaleString('zh-TW',{hour12:false});
const observer=new ResizeObserver(entries=>{for(const entry of entries)instances.get(entry.target.dataset.signal)?.chart.resize();});
export function clearCharts(){for(const{chart,el}of instances.values()){observer.unobserve(el);chart.dispose();}instances.clear();document.getElementById('chart-grid').replaceChildren();}
export function renderCharts(data,{reset=false}={}){
 const keys=Object.keys(METRICS).filter(k=>data.series.some(r=>r.signal===k));
 if(reset||[...instances.keys()].join()!==keys.join())clearCharts();
 for(const key of keys){
  const [label,unit,color]=METRICS[key];let item=instances.get(key);
  if(!item){
   const panel=document.createElement('section');panel.className='trend-panel';
   const head=document.createElement('div');head.className='trend-title';
   const title=document.createElement('h3');title.textContent=label;
   const sub=document.createElement('span');head.append(title,sub);
   const el=document.createElement('div');el.className='trend';el.dataset.signal=key;el.setAttribute('role','img');el.setAttribute('aria-label',label+'歷史趨勢 '+unit);
   panel.append(head,el);document.getElementById('chart-grid').append(panel);
   const chart=echarts.init(el,null,{renderer:'canvas'});chart.group='ems-history';item={el,chart,sub};instances.set(key,item);observer.observe(el);
  }
  const pts=chartPoints(data,key);const linePts=chartLinePoints(pts,data.bucket_seconds);const actual=pts.filter(p=>p.value!==null);
  const min=actual.length?Math.min(...actual.map(p=>p.min)):null,max=actual.length?Math.max(...actual.map(p=>p.max)):null;
  item.sub.textContent=isState(key)?'桶末狀態 · 0 關閉 / 1 開啟':'最低 '+fmt(min)+' · 最高 '+fmt(max)+' '+unit;
  const state=isState(key);
  const line=(name,field,extra={})=>({name,type:'line',showSymbol:field==='value',symbol:'circle',symbolSize:2,emphasis:{scale:false},connectNulls:false,data:linePts.map(p=>[p.time,p[field]]),lineStyle:{width:2,color},itemStyle:{color,borderWidth:0},...extra});
  const series=[line(state?'桶末狀態':key==='energy_kwh'?'桶末讀值':'平均值','value',{step:state?'end':false,areaStyle:state?{opacity:.08,color}:undefined})];
  if(!state&&key!=='energy_kwh')series.push(line('最低','min',{lineStyle:{color,width:1,type:'dashed',opacity:.45}}),line('最高','max',{lineStyle:{color,width:1,type:'dashed',opacity:.45}}));
  const oldZoom=item.chart.getOption()?.dataZoom?.[0];
  item.chart.setOption({
   animation:false,backgroundColor:'transparent',textStyle:{fontFamily:'Microsoft JhengHei, sans-serif',color:'#64645e'},
   grid:{left:62,right:22,top:26,bottom:70},
   tooltip:{trigger:'axis',confine:true,renderMode:'richText',formatter:params=>{
    const t=params?.[0]?.value?.[0];if(t===undefined)return '';
    const point=pts.find(p=>p.time===t);if(!point)return '';
    let text=when(t)+'\n'+label+'：'+displayValue(key,point.value)+(unit?' '+unit:'');
    if(state&&point.min!==point.max&&point.min!==null)text+='\n此時段包含開啟與關閉';
    if(!state&&point.samples)text+='\n最低 '+fmt(point.min)+' / 最高 '+fmt(point.max);
    return text+'\n樣本 '+point.samples+' 筆';
   }},
   xAxis:{type:'time',min:Date.parse(data.since),max:Date.parse(data.until),splitNumber:4,axisLine:{lineStyle:{color:'#d5d5ce'}},axisLabel:{hideOverlap:true,fontSize:11}},
   yAxis:{type:'value',name:state?'狀態':unit,scale:!state,min:state?0:undefined,max:state?1:undefined,interval:state?1:undefined,axisLabel:{formatter:state?(v=>v===1?'開':'關'):undefined,fontSize:11},splitLine:{lineStyle:{color:'#e6e7df'}}},
   dataZoom:[{type:'slider',height:18,bottom:10,borderColor:'#d5d5ce',fillerColor:'rgba(100,121,86,.14)',handleStyle:{color:'#647956'},start:reset?0:oldZoom?.start??0,end:reset?100:oldZoom?.end??100},{type:'inside',zoomOnMouseWheel:'ctrl'}],
   series,aria:{enabled:true}
  },{notMerge:true});
 }
 echarts.connect('ems-history');
 return keys;
}
