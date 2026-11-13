from html.parser import HTMLParser
from pathlib import Path
import re
base=Path('/home/dalelin/synaiq/EMS/output/ems-design-preview-20260923/public')
VOID={'meta','link','img','input','br','hr','source','wbr','area','base','embed','param','col'}
class Node:
    def __init__(self,tag,attrs,start,raw,parent=None):
        self.tag=tag;self.attrs=dict(attrs);self.start=start;self.raw=raw;self.parent=parent;self.children=[];self.classes=[];self.vars={}
class Parser(HTMLParser):
    def __init__(self,text):
        super().__init__(convert_charrefs=False);self.offsets=[0];self.stack=[];self.nodes=[]
        for line in text.splitlines(True):self.offsets.append(self.offsets[-1]+len(line))
        self.feed(text)
    def handle_starttag(self,tag,attrs):
        line,col=self.getpos();n=Node(tag,attrs,self.offsets[line-1]+col,self.get_starttag_text(),self.stack[-1] if self.stack else None)
        if n.parent:n.parent.children.append(n)
        self.nodes.append(n)
        if tag not in VOID:self.stack.append(n)
    def handle_startendtag(self,tag,attrs):
        self.handle_starttag(tag,attrs)
        if tag not in VOID:self.stack.pop()
    def handle_endtag(self,tag):
        for i in range(len(self.stack)-1,-1,-1):
            if self.stack[i].tag==tag:self.stack=self.stack[:i];break
for file in (base/'boards').glob('*.dc.html'):
    text=file.read_text();page=file.name.split('.')[0].lower()
    if 'ems-board' in text:continue
    parser=Parser(text)
    board=next(n for n in parser.nodes if n.tag=='div' and 'width: 1440px' in n.attrs.get('style',''))
    board.classes=['ems-board','ems-page-'+page]
    header=next(n for n in board.children if n.tag=='header');header.classes=['ems-header']
    header.children[0].classes.append('ems-brand');header.children[-1].classes.append('ems-header-actions')
    nav=next(n for n in board.children if n.tag=='nav');nav.classes=['ems-sidebar'];nav.children[0].classes.append('ems-nav-items');nav.children[-1].classes.append('ems-sidebar-footer')
    main=next(n for n in board.children if n.tag=='main');main.classes=['ems-main']
    for node in main.children:
        style=node.attrs.get('style','')
        sections=[n for n in node.children if n.tag=='section']
        if node.tag=='div' and sections:
            node.classes.append('ems-panel-row')
            if page=='main':
                node.classes.append('ems-overview-top' if sections[0].attrs.get('aria-labelledby')=='flowTitle' else 'ems-overview-bottom' if sections[0].attrs.get('aria-labelledby')=='trendTitle' else 'ems-overview-metrics')
            elif 'repeat(3' in style:node.classes.append('ems-three-panels')
        elif node.tag=='div':node.classes.append('ems-page-heading')
        if node.tag=='section' and 'grid-template-columns:' in style:
            node.classes.append('ems-summary')
            if 'repeat(6' in style:node.classes.append('ems-summary-six')
        if node.attrs.get('aria-label')=='報表條件':node.classes.append('ems-report-filters')
    for node in parser.nodes:
        if node.tag=='section':
            node.classes.append('ems-panel')
            height=re.search(r'(?:^|;)\s*height:\s*(\d+)px',node.attrs.get('style',''))
            if height:node.vars['--ems-panel-min']=height[1]+'px'
        if node.attrs.get('role')=='table':node.classes.append('ems-data-table')
        label=node.attrs.get('aria-labelledby')
        if label=='flowTitle':
            canvas=node.children[-1];canvas.classes.append('ems-energy-flow')
            cards=[c for c in canvas.children if c.tag=='div']
            for card,kind in zip(cards,['grid','solar','load','battery']):card.classes+=['ems-energy-node','ems-energy-'+kind]
        if label=='modeTitle':node.children[1].classes.append('ems-mode-diagram')
        if label=='socTitle':node.children[1].classes.append('ems-soc-content')
        if label=='demandTitle':node.children[1].classes.append('ems-demand-summary')
    edits=[]
    for n in parser.nodes:
        raw=n.raw
        if n.classes:
            classes=' '.join(n.classes)
            if 'class' in n.attrs:raw=re.sub(r'class="([^"]*)"',lambda m:'class="'+m[1]+' '+classes+'"',raw,count=1)
            else:raw=raw[:-1]+' class="'+classes+'">'
        if n.vars:
            suffix=';'+''.join(k+':'+v+';' for k,v in n.vars.items())
            raw=re.sub(r'style="([^"]*)"',lambda m:'style="'+m[1]+suffix+'"',raw,count=1)
        if raw!=n.raw:edits.append((n.start,n.start+len(n.raw),raw))
    for start,end,replacement in sorted(edits,reverse=True):text=text[:start]+replacement+text[end:]
    text=text.replace('<meta charset="utf-8">','<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">\n<link rel="stylesheet" href="../responsive.css">',1)
    file.write_text(text)
    print('Responsive layout hooks:',file.name)
