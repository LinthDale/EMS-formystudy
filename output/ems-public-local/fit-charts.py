from pathlib import Path
import re
root=Path('/home/dalelin/synaiq/EMS/output/ems-design-preview-20260923/public')
configs=[('Main',508,'trend','PW','trendTitle',190),('Demand',694,'bars','PW','barsTitle',308),('Storage',1000,'sched','W','schedTitle',308),('Reports',700,'chart','W','repTitle',216)]
for name,old,obj,var,title,height in configs:
 p=root/'boards'/f'{name}.dc.html';s=p.read_text()
 start=s.index(f'<section aria-labelledby="{title}"');end=s.index('</section>',start)
 part=s[start:end]
 marker='<div style="position: relative; flex: 1 1 auto; min-height: 0;">'
 assert marker in part,name
 part=part.replace(marker,f'<div class="ems-chart" data-chart-height="{height}" style="position: relative; flex: 1 0 {height}px; min-height: {height}px;">',1)
 part=part.replace(f'viewBox="0 0 {old} ',f'viewBox="0 0 {{{{{obj}.width}}}} ')
 part=part.replace(f'width="{old}"',f'width="{{{{{obj}.width}}}}"')
 part=part.replace(f'width: {old}px;',f'width: {{{{{obj}.width}}}}px;')
 part=part.replace(f'H{old}"',f'H{{{{{obj}.width}}}}"')
 if name=='Storage':
  part=part.replace('left: 1068px;', 'left: {{sched.bandLeft}};')
  part=part.replace('<div style="position: absolute; left: 60px; top: 16px;', '<div class="ems-schedule-plan" style="position: absolute; left: 60px; top: 16px;')
  part=part.replace('<span style="position: absolute; left: {{sched.nowLeft}}; top: {{sched.nowLabelTop}};', '<span class="ems-schedule-now" style="position: absolute; left: {{sched.nowLeft}}; top: {{sched.nowLabelTop}};')
  part += '<p class="ems-schedule-caption">離峰充電 00:00–06:00 · 目標 SOC 95 %<br>半尖峰放電 58 kW · 夜尖峰計畫 18:00–20:00</p>\n'
 if name=='Main':
  part=part.replace('<div style="position: absolute; right: {{trend.peakLabelRight}};', '<div class="ems-chart-peak" style="position: absolute; right: {{trend.peakLabelRight}};')
 s=s[:start]+part+s[end:]
 s=s.replace(f'var {var} = {old},',f'var {var} = props.plotWidth || {old},',1)
 s=s.replace(f'var {obj} = {{',f'var {obj} = {{\n      width: {var},',1)
 if name=='Main':
  s=s.replace('BOXW = 554','BOXW = PW + 60')
  s=s.replace('[0, 16, 32, 48, 64, 80, 96].map','(PW < 420 ? [0, 24, 48, 72, 96] : [0, 16, 32, 48, 64, 80, 96]).map')
  s=s.replace('r1(BOXW - (OX + px - 14))', 'r1(Math.max(0, Math.min(BOXW - 190, BOXW - (OX + px - 14))))')
 if name=='Demand':
  s=s.replace('bw = 5, rad = 2','bw = Math.min(5, slot * 0.7), rad = Math.min(2, bw / 2)')
  s=s.replace('[0, 3, 6, 9, 12, 15, 18, 21, 24].map','(PW < 450 ? [0, 6, 12, 18, 24] : [0, 3, 6, 9, 12, 15, 18, 21, 24]).map')
 if name=='Storage':
  s=s.replace('bw = 24, PH', 'bw = Math.min(24, slot * 0.6), PH')
  s=s.replace('y = yP(v), rr = 4;', 'y = yP(v), rr = Math.min(4, bw / 2);')
  s=s.replace('width: W,','width: W, bandLeft: (68 + W) + \'px\',',1)
  s=s.replace('[0, 3, 6, 9, 12, 15, 18, 21, 24].map','(W < 450 ? [0, 6, 12, 18, 24] : [0, 3, 6, 9, 12, 15, 18, 21, 24]).map')
 if name=='Reports':
  s=s.replace('xTicks: ticks.map', 'xTicks: ticks.filter(function(t, i) { return W >= 450 || i % 2 === 0; }).map')
  s=s.replace('<div style="display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); height: 64px;', '<div class="ems-report-metrics" style="display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); height: 64px;')
 p.write_text(s)
# All chart containers are observed after render; props change only on real width changes.
p=root/'preview.js';s=p.read_text().replace('let resizeFrame=null;', '''let resizeFrame=null,chartObserver=null,plotWidth=null;
const chartOffsets={Main:60,Demand:70,Storage:130,Reports:72};
function fitChart(){
 const win=frame.contentWindow,chart=win.document.querySelector('.ems-chart');
 if(!chart||!Object.hasOwn(chartOffsets,current))return;
 const width=Math.max(140,Math.floor(chart.getBoundingClientRect().width-chartOffsets[current]));
 if(width===plotWidth)return;
 plotWidth=width;const props={showSketch:true,plotWidth:width};
 if(current==='Main')props.alarmState='normal';if(current==='Storage')props.mode='GRID_TIE';
 win.__dcSetProps(current,props);
}''')
s=s.replace('clearInterval(poll);observer?.disconnect();current=name;', 'clearInterval(poll);observer?.disconnect();chartObserver?.disconnect();plotWidth=null;current=name;')
s=s.replace("win.__dcSetProps(win.__dcRootName(),props);status.textContent", "win.__dcSetProps(win.__dcRootName(),props);const chart=win.document.querySelector('.ems-chart');if(chart){chartObserver=new ResizeObserver(fitChart);chartObserver.observe(chart);fitChart();}status.textContent")
p.write_text(s)
