const apiRoot=new URL('../api/',import.meta.url);
const messages={
 telegram_not_configured:'尚未設定 Telegram 通知，請聯絡管理者。',
 demo_alarm_cooldown:'請等待冷卻結束後再觸發。',
 demo_alarm_in_progress:'這則警報仍在發送中，請稍候重新連接查看結果。',
 telegram_delivery_failed:'Telegram 未確認發送成功。請檢查 Bot 設定或稍後再試。',
 telegram_delivery_unknown:'發送結果尚未確認。請先查看 Telegram，避免重複觸發。'
};
function element(tag,text,attributes={}){
 const node=document.createElement(tag);if(text!==null)node.textContent=text;
 for(const[key,value]of Object.entries(attributes))node.setAttribute(key,value);
 return node;
}
async function api(path,body){
 const response=await fetch(new URL(path,apiRoot),{method:body?'POST':'GET',credentials:'same-origin',headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined,signal:AbortSignal.timeout(12000)});
 const data=await response.json().catch(()=>({}));
 if(!response.ok){const error=Error(messages[data.detail]||'暫時無法完成操作，請稍後再試。');error.status=response.status;error.retry=Number(response.headers.get('Retry-After'))||0;throw error;}
 return data;
}
function mount(root){
 root.className='alarm-demo';root.setAttribute('aria-labelledby','alarm-demo-title');
 const top=element('div',null,{class:'alarm-demo-top'}),intro=element('div',null);
 const title=element('h2','Telegram 警報示範',{id:'alarm-demo-title'});title.append(element('span','DEMO',{class:'alarm-demo-badge'}));
 intro.append(title,element('p','發送一則標示「無需處置」的測試訊息到已設定的 Telegram 接收對象。'));
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
 const history=element('div',null,{class:'alarm-demo-history',hidden:''});
 const list=element('ul',null,{id:'alarm-demo-recent'});history.append(element('h3','最近示範警報'),list);
 root.append(top,status,form,refresh,history);
 let ready=false,busy=false,deadline=0,recent=[];
 const countdown=()=>{const seconds=Math.max(0,Math.ceil((deadline-Date.now())/1000));trigger.disabled=!ready||busy||seconds>0;trigger.textContent=busy?'發送中…':seconds>0?`觸發警報（${seconds} 秒）`:'觸發警報';};
 const note=(text,kind='')=>{status.textContent=text;status.dataset.kind=kind;};
 function showHistory(items){
  recent=items.slice(0,10);list.replaceChildren();history.hidden=recent.length===0;
  for(const item of recent){
   const row=element('li',null),time=element('time',new Date(item.sent_at).toLocaleString('zh-TW',{hour12:false}),{datetime:item.sent_at});
   row.append(element('span','Telegram 已接收',{class:'alarm-demo-sent'}),time,element('code','DEMO · '+String(item.event_id).slice(0,8)));list.append(row);
  }
 }
 async function connect(keepMessage=false){
  try{
   const data=await api('alarms/demo');ready=data.configured;deadline=Date.now()+data.cooldown_seconds*1000;form.hidden=true;refresh.hidden=true;
   showHistory(data.recent||[]);if(!keepMessage)note(ready?'已連接 Telegram，可以觸發示範警報。':'尚未設定 Telegram 通知，請聯絡管理者。',ready?'ready':'error');
  }catch(error){
   ready=false;form.hidden=error.status!==401;refresh.hidden=error.status===401;
   note(error.status===401?'請登入 EMS 後觸發示範警報。':error.status===403?'此帳號沒有發送示範警報的權限。':'無法連接通知服務，請重新連接。','error');
  }finally{countdown();}
 }
 form.addEventListener('submit',async event=>{
  event.preventDefault();if(login.disabled)return;login.disabled=true;note('正在登入…');
  try{await api('auth/login',{username:username.value,password:password.value});password.value='';await connect();}
  catch(error){password.value='';note(error.status===401?'帳號或密碼不正確。':error.status===429?'登入嘗試過於頻繁，請稍後再試。':'暫時無法登入，請稍後再試。','error');}
  finally{login.disabled=false;}
 });
 trigger.addEventListener('click',async()=>{
  if(trigger.disabled||busy)return;busy=true;countdown();note('正在發送示範警報…');
  try{
   const data=await api('alarms/demo',{request_id:crypto.randomUUID()});
   if(data.status!=='sent')throw Error('Invalid acknowledgement');
   deadline=Date.now()+data.cooldown_seconds*1000;showHistory([data,...recent.filter(x=>x.event_id!==data.event_id)]);
   note('已發送至 Telegram。這是 DEMO 訊息，無需處置。','sent');
  }catch(error){
   if(error.status===401||error.status===403){await connect();}
   else{deadline=Date.now()+Math.max(30,error.retry||0)*1000;note(error.status?error.message:'發送結果尚未確認，請先查看 Telegram，再重新連接。','error');refresh.hidden=false;}
  }finally{busy=false;countdown();}
 });
 refresh.addEventListener('click',()=>connect());
 const timer=setInterval(countdown,1000);window.addEventListener('pagehide',()=>clearInterval(timer),{once:true});
 connect();
}
function initialize(){const root=document.getElementById('alarm-demo');if(!root||root.closest('x-dc'))return false;if(!root.dataset.mounted){root.dataset.mounted='true';mount(root);}return true;}
if(!initialize()){const observer=new MutationObserver(()=>{if(initialize())observer.disconnect();});observer.observe(document.documentElement,{childList:true,subtree:true});}
