// PRD-0024 booth QR: draws a Telegram deep link as one SVG <path>, built with DOM APIs only (no HTML parsing).
// Encoder: vendored uqr 0.1.3 (MIT, assets/UQR-LICENSE.txt), error correction level M.
import {encode} from '../assets/uqr-0.1.3.mjs';
const SVG_NS='http://www.w3.org/2000/svg';
export const QR_BORDER=4; // quiet zone in modules (ISO/IEC 18004 minimum), drawn white by the page CSS
export const QR_MAX_LENGTH=256;
// Returns {size,d}: size counts modules including the quiet zone; d draws every horizontal run of dark modules as one unit-high rectangle.
export function qrPath(text){
 if(typeof text!=='string'||text.length===0||text.length>QR_MAX_LENGTH)throw TypeError(`QR text must be a string of 1-${QR_MAX_LENGTH} characters`);
 const {size,data}=encode(text,{ecc:'M',border:QR_BORDER});
 const runs=[];
 data.forEach((row,y)=>{
  for(let x=0;x<size;x++){
   if(!row[x]||row[x-1])continue;
   let end=x;while(end<size&&row[end])end++;
   runs.push(`M${x} ${y}h${end-x}v1h-${end-x}z`);
  }
 });
 return Object.freeze({size,d:runs.join('')});
}
export function createQrSvg(doc,text,label='Telegram 綁定 QR Code'){
 const {size,d}=qrPath(text),svg=doc.createElementNS(SVG_NS,'svg'),path=doc.createElementNS(SVG_NS,'path');
 const attributes={viewBox:`0 0 ${size} ${size}`,role:'img','aria-label':label,'data-link':text,'shape-rendering':'crispEdges'};
 for(const [name,value] of Object.entries(attributes))svg.setAttribute(name,value);
 path.setAttribute('d',d);path.setAttribute('fill','#000');
 svg.append(path);
 return svg;
}
