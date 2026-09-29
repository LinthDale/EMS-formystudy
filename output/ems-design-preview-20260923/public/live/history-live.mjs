import {METRICS,isState,fmt,displayValue,deviceLabel,rangeFor,latestSignals,toCsv} from './history-model.mjs';
import {clearCharts,renderCharts} from './charts.mjs';
const $=id=>document.getElementById(id),PAGE_SIZE=100;
let session=null,devices=[],history=null,raw=[],offset=0,activeRange=null,timer=null,controller=null,epoch=0;
const date=t=>new Date(t).toLocaleString('zh-TW',{hour12:false});
function text(tag,value,cls){const e=document.createElement(tag);e.textContent=value;if(cls)e.className=cls;return e;}
function state(kind,label,message){$('connection').dataset.state=kind;$('connection').textContent=label;$('message').textContent=message;$('message').dataset.error=kind==='error';document.body.classList.toggle('outdated',kind==='error'||kind==='stale');}
async function request(path,{method='GET',body,signal}={}){
 const timeout=AbortSignal.timeout(15000);
 const res=await fetch(path,{method,credentials:'same-origin',cache:'no-store',headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined,signal:signal?AbortSignal.any([signal,timeout]):timeout});
 if(!res.ok){const e=Error('HTTP '+res.status);e.status=res.status;throw e;}return res.status===204?null:res.json();
}
function clearData(){
 history=null;raw=[];clearCharts();$('cards').replaceChildren();$('table-head').replaceChildren();$('table-body').replaceChildren();
 $('chart-empty').hidden=false;$('chart-empty').textContent='此範圍尚未載入圖表。';$('chart-note').hidden=true;
 $('records-empty').hidden=false;$('records-empty').textContent='尚未載入紀錄';
 $('export').disabled=true;$('previous').disabled=true;$('next').disabled=true;$('page-label').textContent='0 筆';$('resolution').textContent='—';$('updated').textContent='尚未取得量測';
}
function signedOut(){session=null;devices=[];clearData();$('login-panel').hidden=false;$('logout').hidden=true;$('session-name').textContent='尚未登入';$('session-role').textContent='帳號';$('header-login').hidden=false;$('device').replaceChildren(new Option('等待設備清單',''));$('device').disabled=true;}
function errorState(e){
 if(e.status===401){signedOut();state('auth','尚未登入','請登入自建 EMS 的 OPS 帳號。');}
 else {clearData();state('error',e.status===403?'權限不足':'查詢未完成',e.status===403?'此帳號需要 OPS 權限。':e.status===404?'歷史介面尚未啟用，或此設備沒有對應量測來源。':e.status===422?'查詢時間或分頁超出允許範圍，請重新選擇。':'暫時無法讀取後端。請稍後按「更新圖表」重試。');}
}
function renderCards(){
 const latest=latestSignals(history.series);$('cards').replaceChildren();
 for(const key of Object.keys(METRICS).filter(k=>latest[k])){
  const row=latest[key],card=text('div','','card');card.append(text('div',METRICS[key][0],'card-label'));
  const value=text('span',displayValue(key,row.last),'card-value');value.dataset.metric=key;
  card.append(value,text('span',METRICS[key][1],'card-unit'),text('span','區間末筆 '+new Date(row.last_time).toLocaleTimeString('zh-TW',{hour12:false}),'card-time'));$('cards').append(card);
 }
}
function renderRecords(result){
 if(!Array.isArray(result.rows)||typeof result.has_more!=='boolean')throw Error('紀錄格式錯誤');
 raw=result.rows;const keys=Object.keys(METRICS).filter(k=>history?.series.some(r=>r.signal===k)||raw.some(r=>r[k]!==null&&r[k]!==undefined));
 const head=document.createElement('tr');head.append(text('th','量測時間'));for(const key of keys)head.append(text('th',METRICS[key][0]+(METRICS[key][1]?' / '+METRICS[key][1]:'')));
 $('table-head').replaceChildren(head);$('table-body').replaceChildren();
 for(const row of raw){const tr=document.createElement('tr');tr.append(text('td',date(row.time)));for(const key of keys){const value=row[key];const label=isState(key)?value===true?'開啟':value===false?'關閉':'—':fmt(value);tr.append(text('td',label,value===null||value===undefined?'null':''));}$('table-body').append(tr);}
 $('records-empty').hidden=raw.length>0;$('records-empty').textContent='這段時間沒有原始紀錄。';
 $('records-range').textContent=date(activeRange.since)+' — '+date(activeRange.until)+' · 每頁 '+PAGE_SIZE+' 筆 · 缺值以 — 表示';
 $('page-label').textContent=raw.length?'第 '+(offset/PAGE_SIZE+1)+' 頁 · 第 '+(offset+1)+'–'+(offset+raw.length)+' 筆':'0 筆';
 $('previous').disabled=offset===0;$('next').disabled=!result.has_more||offset+PAGE_SIZE>1000000;$('export').disabled=!raw.length;
}
function schedule(){clearTimeout(timer);if(session&&Number($('auto').value)>0&&$('period').value!=='custom'&&offset===0)timer=setTimeout(()=>load(),Number($('auto').value));}
function cancel(){clearTimeout(timer);controller?.abort();controller=new AbortController();return {signal:controller.signal,run:++epoch};}
async function ensureSession(signal,run){
 if(!session)session=await request('/api/auth/session',{signal});
 if(run!==epoch)return false;
 if(session.role!=='ops'){const e=Error();e.status=403;throw e;}
 $('login-panel').hidden=true;$('logout').hidden=false;$('session-name').textContent=session.username;$('session-role').textContent='維運 · OPS';$('header-login').hidden=true;
 if(!devices.length){
  const data=await request('/api/devices?limit=500&offset=0&sort=device_id&order=asc',{signal});
  if(run!==epoch)return false;if(!Array.isArray(data))throw Error('設備格式錯誤');
  devices=data.filter(d=>d&&/^[A-Za-z0-9_-]{1,64}$/.test(d.device_id));
  $('device').replaceChildren(...devices.map(d=>new Option(d.device_id==='delta-sim-001'?'太陽能逆變器(delta-sim-001)':deviceLabel(d.device_id)+(d.location?' · '+d.location:''),d.device_id)));
  $('device').disabled=!devices.length;if(devices.some(d=>d.device_id==='sim-001'))$('device').value='sim-001';
 }
 return true;
}
async function load({reset=false,pageOnly=false}={}){
 const {signal,run}=cancel();
 try{
  if(!await ensureSession(signal,run))return;
  const id=$('device').value;if(!id){clearData();state('empty','沒有設備','後端設備清單為空。');return;}
  if(!pageOnly){activeRange=rangeFor($('period').value,$('from').value,$('to').value);offset=0;}
  const query=new URLSearchParams(activeRange);
  $('range').textContent=date(activeRange.since)+' — '+date(activeRange.until)+'（本機時區）';
  state('loading','查詢中','正在讀取 '+deviceLabel(id)+' 的歷史資料…');
  $('previous').disabled=true;$('next').disabled=true;
  const prefix='/api/devices/'+encodeURIComponent(id);
  const [h,r]=await Promise.all([
   pageOnly?Promise.resolve(history):request(prefix+'/history?'+query+'&points=600',{signal}),
   request(prefix+'/records?'+query+'&limit='+PAGE_SIZE+'&offset='+offset,{signal})
  ]);
  if(run!==epoch)return;
  if(!h||!Array.isArray(h.series)||!Number.isFinite(h.bucket_seconds)||h.bucket_seconds<1)throw Error('歷史格式錯誤');
  history=h;
  if(!pageOnly){
   renderCards();renderCharts(history,{reset});$('chart-empty').hidden=!!history.series.length;$('chart-empty').textContent='所選時間沒有量測資料，請調整範圍。';$('chart-note').hidden=!history.series.length;
   $('resolution').textContent='每 '+history.bucket_seconds+' 秒彙整 · 含最低／最高';
  }
  renderRecords(r);
  const last=Math.max(...history.series.map(s=>Date.parse(s.last_time)));
  const historical=$('period').value==='custom'||offset>0||$('auto').value==='0';
  if(!history.series.length)state('empty','沒有資料','所選時段未收到量測，請調整時間範圍。');
  else if(historical)state('history','歷史檢視','正在檢視固定時段；圖表為彙整值，下方為原始紀錄。');
  else if(Date.now()-last>30000||last>Date.now()+30000)state('stale','量測未更新','歷史查詢成功，但最新量測超過 30 秒未更新或設備時間異常。');
  else state('live','持續接收中',deviceLabel(id)+' · 圖表與紀錄均來自後端資料。');
  $('updated').textContent='讀取 '+new Date().toLocaleTimeString('zh-TW',{hour12:false})+(Number.isFinite(last)?' · 量測 '+new Date(last).toLocaleTimeString('zh-TW',{hour12:false}):'');
 }catch(e){if(run===epoch&&!signal.aborted)errorState(e);}finally{if(run===epoch)schedule();}
}
function resetLoad(){clearData();load({reset:true});}
$('login-form').addEventListener('submit',async e=>{
 e.preventDefault();const {run}=cancel();const button=e.submitter;button.disabled=true;
 try{const user=await request('/api/auth/login',{method:'POST',body:{username:$('username').value,password:$('password').value}});if(run!==epoch)return;session=user;devices=[];await load({reset:true});}
 catch(error){errorState(error);if(error.status===401)$('message').textContent='帳號或密碼不正確，請重試。';}
 finally{$('password').value='';button.disabled=false;}
});
$('header-login').addEventListener('click',()=>{$('header-account').open=false;$('login-panel').scrollIntoView({block:'center'});$('username').focus();});
$('logout').addEventListener('click',async()=>{$('header-account').open=false;cancel();try{await request('/api/auth/logout',{method:'POST'});signedOut();state('auth','已登出','請登入以查看圖表與歷史。');}catch(e){errorState(e);}});
$('device').addEventListener('change',resetLoad);
$('period').addEventListener('change',()=>{
 const custom=$('period').value==='custom';$('custom-range').hidden=!custom;
 if(custom){cancel();$('auto').value='0';state('history','選擇時間','選擇開始與結束時間後，按「套用時間」。');}
 else resetLoad();
});
$('custom-range').addEventListener('submit',e=>{e.preventDefault();try{rangeFor('custom',$('from').value,$('to').value);resetLoad();}catch(error){$('message').textContent=error.message;$('message').dataset.error=true;}});
$('auto').addEventListener('change',()=>{if($('period').value==='custom')$('auto').value='0';schedule();});
$('refresh').addEventListener('click',()=>{try{rangeFor($('period').value,$('from').value,$('to').value);resetLoad();}catch(e){$('message').textContent=e.message;}});
for(const [id,delta]of [['previous',-PAGE_SIZE],['next',PAGE_SIZE]])$(id).addEventListener('click',()=>{offset=Math.max(0,offset+delta);$('auto').value='0';load({pageOnly:true});});
$('export').addEventListener('click',()=>{
 const keys=Object.keys(METRICS).filter(k=>history?.series.some(r=>r.signal===k)||raw.some(r=>r[k]!==null&&r[k]!==undefined));
 const url=URL.createObjectURL(new Blob(['\ufeff'+toCsv(raw,keys)],{type:'text/csv;charset=utf-8'}));
 const a=document.createElement('a');a.href=url;a.download=$('device').value+'-history-page-'+(offset/PAGE_SIZE+1)+'.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
});
const localInput=t=>{const d=new Date(t);return new Date(d-d.getTimezoneOffset()*60000).toISOString().slice(0,16);};
$('from').value=localInput(Date.now()-3600000);$('to').value=localInput(Date.now());
window.addEventListener('pagehide',()=>{cancel();clearCharts();});
clearData();load({reset:true});
