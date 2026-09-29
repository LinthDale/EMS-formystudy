'use strict';
const pages={Main:{title:'能源總覽',height:900},Monitor:{title:'即時監控',height:1180,live:true},Demand:{title:'需量管理',height:1080},Storage:{title:'儲能管理',height:1240},Alarms:{title:'警報中心',height:1120},Devices:{title:'設備分析',height:1200},Reports:{title:'報表中心',height:1120}};
const frame=document.getElementById('screen'),stage=document.getElementById('stage'),viewport=document.getElementById('viewport'),status=document.getElementById('status');
let current=null,poll=null,observer=null;
let resizeFrame=null,chartObserver=null,plotWidth=null;
const chartOffsets={Main:60,Demand:70,Storage:130,Reports:72};
function fitChart(){
 const win=frame.contentWindow,chart=win.document.querySelector('.ems-chart');
 if(!chart||!Object.hasOwn(chartOffsets,current))return;
 const width=Math.max(140,Math.floor(chart.getBoundingClientRect().width-chartOffsets[current]));
 if(width===plotWidth)return;
 plotWidth=width;const props={showSketch:true,plotWidth:width};
 if(current==='Main')props.alarmState='normal';if(current==='Storage')props.mode='GRID_TIE';
 win.__dcSetProps(current,props);
}
function resize(){
 if(resizeFrame!==null)return;
 resizeFrame=requestAnimationFrame(()=>{
  resizeFrame=null;if(!current)return;
  const doc=frame.contentDocument;
  doc?.documentElement.style.setProperty('--app-viewport-height',window.innerHeight+'px');
  frame.style.width='100%';frame.style.transform='none';stage.style.width='100%';
  const height=Math.max(window.innerHeight,Math.ceil(doc?.body?.getBoundingClientRect().height||0));
  frame.style.height=height+'px';stage.style.height=height+'px';
 });
}
function navigate(name){
 if(!Object.hasOwn(pages,name))name='Main';
 clearInterval(poll);observer?.disconnect();chartObserver?.disconnect();plotWidth=null;current=name;
 frame.title='EMS '+pages[name].title;document.title=pages[name].title+'｜tAIstro EMS';
 status.textContent='正在載入'+pages[name].title+'…';delete status.dataset.error;
 if(location.hash!=='#'+name)history.replaceState(null,'','#'+name);
 const source=pages[name].live?'live/Monitor.html':'boards/'+name+'.dc.html';
 frame.contentWindow.location.replace(new URL(source,document.baseURI).href);resize();
}
frame.addEventListener('load',()=>{
 const name=frame.contentWindow.location.pathname.split('/').pop().replace('.dc.html','').replace('.html','');
 if(name!==current)return;
 clearInterval(poll);observer?.disconnect();
 frame.contentDocument.addEventListener('click',event=>{
  if(event.defaultPrevented||event.button!==0||event.ctrlKey||event.metaKey||event.shiftKey||event.altKey)return;
  const link=event.target.closest?.('a[href]');if(!link||link.target==='_blank'||link.hasAttribute('download'))return;
  const url=new URL(link.href);if(url.origin!==location.origin)return;
  const target=url.pathname.split('/').pop().replace('.dc.html','').replace('.html','');
  if(!Object.hasOwn(pages,target))return;
  event.preventDefault();if(target!==current)location.hash=target;
 });
 observer=new ResizeObserver(resize);observer.observe(frame.contentDocument.body);
 if(pages[name].live){status.textContent='即時監控已載入';resize();return;}
 let tries=0;
 poll=setInterval(()=>{
  const win=frame.contentWindow;
  if(win.__dcRootName?.()===name&&win.__dcRegistry?.[name]?.Logic){
   clearInterval(poll);const props={showSketch:true};if(name==='Main')props.alarmState='normal';if(name==='Storage')props.mode='GRID_TIE';
   win.__dcSetProps(win.__dcRootName(),props);if(window.innerWidth<=900)win.document.querySelector('.ems-sidebar a[href$='+JSON.stringify(name+'.dc.html')+']')?.scrollIntoView({block:'nearest',inline:'center'});const chart=win.document.querySelector('.ems-chart');if(chart){chartObserver=new ResizeObserver(fitChart);chartObserver.observe(chart);fitChart();}status.textContent=pages[name].title+'已載入';resize();
  }else if(++tries>=100){clearInterval(poll);status.dataset.error='true';status.textContent='畫面載入未完成，請重新整理。';}
 },100);
});
window.addEventListener('resize',resize);
window.addEventListener('hashchange',()=>{const name=location.hash.slice(1);if(name!==current)navigate(name);});
navigate(location.hash.slice(1)||'Main');


