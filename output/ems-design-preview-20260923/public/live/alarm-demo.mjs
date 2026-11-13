const apiRoot=new URL('../api/',import.meta.url);
const messages={
 telegram_not_configured:'尚未設定 Telegram 通知，請聯絡管理者。',
 demo_alarm_cooldown:'請等待冷卻結束後再觸發。',
 demo_alarm_in_progress:'這則警報仍在發送中，請稍候重新連接查看結果。',
 telegram_delivery_failed:'Telegram 未確認發送成功。請檢查 Bot 設定或稍後再試。',
 telegram_delivery_unknown:'發送結果尚未確認。請先查看 Telegram，避免重複觸發。'
};
// PRD-0024 booth QR binding. Shown only when GET /api/alarms/demo returns a `binding` object; null or absent keeps the PRD-0019 panel.
const POLL_MS=4000,STALE_MS=120000,PAGE_ROWS=5,MAX_ROWS=10;
const DEEP_LINK=/^https:\/\/t\.me\/[A-Za-z0-9_]{5,32}\?start=[A-Za-z0-9_-]{1,64}$/;
const INVISIBLE=/[\p{Cc}\p{Cf}\p{Zl}\p{Zp}]/gu;
const intros={
 legacy:'發送一則標示「無需處置」的測試訊息到已設定的 Telegram 接收對象。',
 booth:'訪客用手機掃描 QR Code，並在 Telegram 按「開始」即可綁定。按下按鈕後，示範警報會傳給目前綁定的訪客；未綁定時發送至預設 Telegram 對象。訊息皆標示 DEMO，無需處置。'
};
const botNotes={
 starting:'掃碼綁定服務啟動中，QR Code 稍後顯示。',
 webhook_active:'此 Bot 已設定 Webhook，掃碼綁定暫停。',
 conflict:'另有程式正在接收此 Bot 的訊息，掃碼綁定暫停。',
 unauthorized:'Bot 授權失效，掃碼綁定已停止，請聯絡管理者。',
 unavailable:'掃碼綁定暫時無法使用。'
};
const qrNotes={broken:'QR Code 暫時無法顯示。',stale:'QR Code 暫時無法更新，請重新連接。'};
let qrModule=null;
const loadQr=()=>qrModule||(qrModule=import('./qr-svg.mjs').catch(error=>{qrModule=null;throw error;}));
function element(tag,text,attributes={}){
 const node=document.createElement(tag);if(text!==null)node.textContent=text;
 for(const[key,value]of Object.entries(attributes))node.setAttribute(key,value);
 return node;
}
const setText=(node,text)=>{if(node.textContent!==text)node.textContent=text;};
async function api(path,body){
 const response=await fetch(new URL(path,apiRoot),{method:body?'POST':'GET',credentials:'same-origin',headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined,signal:AbortSignal.timeout(12000)});
 const data=await response.json().catch(()=>({}));
 if(!response.ok){const error=Error(messages[data.detail]||'暫時無法完成操作，請稍後再試。');error.status=response.status;error.retry=Number(response.headers.get('Retry-After'))||0;throw error;}
 return data;
}
// The binding block is untrusted input: keep only a validated deep link, a cleaned masked display (never a raw username) and plain numbers.
function readBinding(raw,now){
 if(!raw||typeof raw!=='object')return null;
 const state=raw.state==='ready'||Object.hasOwn(botNotes,raw.state)?raw.state:'unavailable';
 const link=state==='ready'&&typeof raw.deep_link==='string'&&DEEP_LINK.test(raw.deep_link)?raw.deep_link:'';
 const current=raw.current&&typeof raw.current==='object'?raw.current:null,seconds=Number(current?.expires_in_seconds);
 const bound=Boolean(current)&&!(Number.isFinite(seconds)&&seconds<=0),count=raw.today?.visitor_count;
 const display=bound?Array.from((typeof current.display==='string'?current.display:'').replace(INVISIBLE,'').trim()).slice(0,24).join('')||'Telegram 訪客':'';
 return Object.freeze({state,link,display,until:bound&&Number.isFinite(seconds)?now+Math.min(seconds,86400)*1000:0,count:Number.isInteger(count)&&count>=0?count:null});
}
function bindingText(binding,now){
 const left=binding.until?Math.ceil((binding.until-now)/1000):0;
 if(!binding.display||(binding.until&&left<=0))return '目前綁定：無（將發送至預設對象）';
 return binding.until?`目前綁定：${binding.display}（剩 ${Math.floor(left/60)}:${String(left%60).padStart(2,'0')}）`:`目前綁定：${binding.display}`;
}
const visitorNumber=item=>Number.isInteger(item.visitor_number)&&item.visitor_number>0?item.visitor_number:0;
const targetLabel=item=>item.target==='visitor'?(visitorNumber(item)?`訪客 #${visitorNumber(item)}`:'訪客'):item.target==='default'?'預設對象':'';
function sentText(data){
 if(data.target==='visitor')return visitorNumber(data)?`已發送給目前綁定的訪客（今天第 ${visitorNumber(data)} 位）。`:'已發送給目前綁定的訪客。';
 return data.target==='default'?'已發送至預設 Telegram 對象。':'已發送至 Telegram。這是 DEMO 訊息，無需處置。';
}
// QR + binding facts. render() is cheap and idempotent; the SVG is rebuilt only when the deep link changes.
function createBooth(){
 const node=element('div',null,{id:'alarm-demo-booth',class:'alarm-demo-booth',hidden:''});
 const qrBox=element('figure',null,{id:'alarm-demo-qr',class:'alarm-demo-qr',hidden:''}),caption=element('figcaption','用手機掃描，在 Telegram 按「開始」綁定');
 const facts=element('div',null,{class:'alarm-demo-facts'}),current=element('p','',{id:'alarm-demo-binding',class:'alarm-demo-binding'});
 const today=element('p','',{id:'alarm-demo-today',class:'alarm-demo-today'}),botNote=element('p','',{id:'alarm-demo-bot-note',class:'alarm-demo-bot-note',hidden:''});
 qrBox.append(caption);facts.append(current,today,botNote);node.append(qrBox,facts);
 let shown='',pending='',failed='',last={binding:null,fresh:false};
 function draw(link){
  pending=link;
  loadQr().then(({createQrSvg})=>{if(pending===link){qrBox.replaceChildren(createQrSvg(document,link),caption);shown=link;}})
   .catch(()=>{if(pending===link)failed=link;})
   .finally(()=>{if(pending===link){pending='';render(last.binding,last.fresh);}});
 }
 function render(binding,fresh,now=Date.now()){
  last={binding,fresh};node.hidden=!binding;
  if(!binding){qrBox.hidden=true;return;}
  const want=binding.state==='ready'&&fresh?binding.link:'';
  if(want&&want!==shown&&want!==pending&&want!==failed)draw(want);
  qrBox.hidden=!want||want!==shown;
  const broken=binding.state==='ready'&&(!binding.link||binding.link===failed);
  const text=binding.state!=='ready'?botNotes[binding.state]:broken?qrNotes.broken:fresh?'':qrNotes.stale;
  setText(botNote,text);botNote.hidden=!text;
  setText(current,bindingText(binding,now));
  today.hidden=binding.count===null;setText(today,`今日已觸發：${binding.count??0} 位客人`);
 }
 return {node,render};
}
// Recent sends: 5 rows by default, the rest (up to 10) behind 「展開全部（N）」/「收合」.
function createHistory(){
 const node=element('div',null,{class:'alarm-demo-history',hidden:''}),list=element('ul',null,{id:'alarm-demo-recent'});
 const toggle=element('button','',{id:'alarm-demo-toggle',type:'button',class:'alarm-demo-toggle','aria-controls':'alarm-demo-recent','aria-expanded':'false',hidden:''});
 node.append(element('h3','最近示範警報'),list,toggle);
 let items=[],expanded=false,drawn='';
 function fold(){
  const extra=items.length>PAGE_ROWS;
  toggle.hidden=!extra;toggle.setAttribute('aria-expanded',String(extra&&expanded));
  setText(toggle,expanded?'收合':`展開全部（${items.length}）`);
  Array.from(list.children).forEach((row,index)=>{row.hidden=!expanded&&index>=PAGE_ROWS;});
 }
 function row(item){
  const node=element('li',null),label=targetLabel(item);
  node.append(element('span','Telegram 已接收',{class:'alarm-demo-sent'}));
  if(label)node.append(element('span',label,{class:'alarm-demo-target'}));
  node.append(element('time',new Date(item.sent_at).toLocaleString('zh-TW',{hour12:false}),{datetime:item.sent_at}),element('code','DEMO · '+String(item.event_id).slice(0,8)));
  return node;
 }
 // Polls repeat the same list every 4 s; rows are rebuilt only when it changed.
 function show(next){
  items=next.slice(0,MAX_ROWS);node.hidden=items.length===0;
  const key=JSON.stringify(items);if(key!==drawn){drawn=key;list.replaceChildren(...items.map(row));}
  fold();
 }
 toggle.addEventListener('click',()=>{expanded=!expanded;fold();});
 return {node,show,items:()=>items};
}
function mount(root){
 root.className='alarm-demo';root.setAttribute('aria-labelledby','alarm-demo-title');
 const top=element('div',null,{class:'alarm-demo-top'}),intro=element('div',null);
 const title=element('h2','Telegram 警報示範',{id:'alarm-demo-title'});title.append(element('span','DEMO',{class:'alarm-demo-badge'}));
 const lead=element('p',intros.legacy);intro.append(title,lead);
 const trigger=element('button','觸發警報',{id:'alarm-demo-trigger',type:'button',class:'alarm-demo-trigger',disabled:''});
 top.append(intro,trigger);
 const status=element('p','正在連接通知服務…',{id:'alarm-demo-status',role:'status','aria-live':'polite',class:'alarm-demo-status'});
 const form=element('form',null,{id:'alarm-demo-login',class:'alarm-demo-login',hidden:''});
 const userLabel=element('label','帳號'),passLabel=element('label','密碼');
 const username=element('input',null,{name:'username',id:'alarm-demo-username',autocomplete:'username',required:'',maxlength:'64'});username.value='demo';
 const password=element('input',null,{name:'password',id:'alarm-demo-password',type:'password',autocomplete:'current-password',required:'',maxlength:'256'});
 userLabel.append(username);passLabel.append(password);
 const login=element('button','登入',{type:'submit'});form.append(userLabel,passLabel,login);
 const refresh=element('button','重新連接',{type:'button',class:'alarm-demo-refresh',hidden:''});
 const booth=createBooth(),history=createHistory();
 root.append(top,status,booth.node,form,refresh,history.node);
 // connects: only the newest connect() may apply its answer. epoch: a connect or a send invalidates any poll still in flight.
 let ready=false,busy=false,deadline=0,binding=null,lastOk=0,connects=0,epoch=0,pollTimer=0,polling=false,stopped=false;
 const countdown=()=>{const seconds=Math.max(0,Math.ceil((deadline-Date.now())/1000));trigger.disabled=!ready||busy||seconds>0;trigger.textContent=busy?'發送中…':seconds>0?`觸發警報（${seconds} 秒）`:'觸發警報';};
 const note=(text,kind='')=>{status.textContent=text;status.dataset.kind=kind;};
 const paint=(now=Date.now())=>{setText(lead,binding?intros.booth:intros.legacy);booth.render(binding,now-lastOk<=STALE_MS,now);};
 // A poll never shortens a local cooldown (e.g. the 30 s wait after an unconfirmed send) and never rewrites the status line.
 function apply(data,fromPoll){
  const now=Date.now(),until=now+(Number(data.cooldown_seconds)||0)*1000;
  ready=data.configured;deadline=fromPoll?Math.max(deadline,until):until;binding=readBinding(data.binding,now);lastOk=now;
  history.show(data.recent||[]);paint(now);
 }
 function fail(error){
  ready=false;binding=null;paint();form.hidden=error.status!==401;refresh.hidden=error.status===401;
  note(error.status===401?'請登入 EMS 後觸發示範警報。':error.status===403?'此帳號沒有發送示範警報的權限。':'無法連接通知服務，請重新連接。','error');
 }
 async function connect(keepMessage=false){
  const ticket=++connects;epoch++;
  try{
   const data=await api('alarms/demo');if(ticket!==connects)return;
   form.hidden=true;refresh.hidden=true;apply(data,false);
   if(!keepMessage)note(ready?'已連接 Telegram，可以觸發示範警報。':'尚未設定 Telegram 通知，請聯絡管理者。',ready?'ready':'error');
  }catch(error){if(ticket===connects)fail(error);}
  finally{countdown();schedulePoll();}
 }
 // Poll every 4 s only while a binding block exists and the page is visible; 401/403 ends polling like a failed connect.
 function schedulePoll(delay=POLL_MS){clearTimeout(pollTimer);pollTimer=binding&&!stopped&&document.visibilityState==='visible'?setTimeout(poll,delay):0;}
 async function poll(){
  if(polling||busy){schedulePoll();return;}
  polling=true;const ticket=epoch;
  try{const data=await api('alarms/demo');if(ticket===epoch)apply(data,true);}
  catch(error){if(ticket===epoch&&(error.status===401||error.status===403))fail(error);}
  finally{polling=false;countdown();schedulePoll();}
 }
 form.addEventListener('submit',async event=>{
  event.preventDefault();if(login.disabled)return;login.disabled=true;note('正在登入…');
  try{await api('auth/login',{username:username.value,password:password.value});password.value='';await connect();}
  catch(error){password.value='';note(error.status===401?'帳號或密碼不正確。':error.status===429?'登入嘗試過於頻繁，請稍後再試。':'暫時無法登入，請稍後再試。','error');}
  finally{login.disabled=false;}
 });
 trigger.addEventListener('click',async()=>{
  if(trigger.disabled||busy)return;busy=true;epoch++;countdown();note('正在發送示範警報…');
  try{
   const data=await api('alarms/demo',{request_id:crypto.randomUUID()});
   if(data.status!=='sent')throw Error('Invalid acknowledgement');
   deadline=Date.now()+data.cooldown_seconds*1000;history.show([data,...history.items().filter(x=>x.event_id!==data.event_id)]);
   note(sentText(data),'sent');
   if(binding)schedulePoll(0);
  }catch(error){
   if(error.status===401||error.status===403){await connect();}
   else{deadline=Date.now()+Math.max(30,error.retry||0)*1000;note(error.status?error.message:'發送結果尚未確認，請先查看 Telegram，再重新連接。','error');refresh.hidden=false;}
  }finally{busy=false;countdown();}
 });
 refresh.addEventListener('click',()=>connect());
 const tick=()=>{countdown();if(binding)paint();};
 let timer=setInterval(tick,1000);
 document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible')schedulePoll(0);else{clearTimeout(pollTimer);pollTimer=0;}});
 window.addEventListener('pagehide',()=>{stopped=true;clearInterval(timer);clearTimeout(pollTimer);pollTimer=0;});
 window.addEventListener('pageshow',event=>{if(!event.persisted)return;stopped=false;clearInterval(timer);timer=setInterval(tick,1000);schedulePoll(0);});
 connect();
}
function initialize(){const root=document.getElementById('alarm-demo');if(!root||root.closest('x-dc'))return false;if(!root.dataset.mounted){root.dataset.mounted='true';mount(root);}return true;}
if(!initialize()){const observer=new MutationObserver(()=>{if(initialize())observer.disconnect();});observer.observe(document.documentElement,{childList:true,subtree:true});}
