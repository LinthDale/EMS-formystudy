import http from 'node:http';
import {readFile,realpath,stat} from 'node:fs/promises';
import {resolve,dirname,extname,sep} from 'node:path';
import {fileURLToPath} from 'node:url';
const base=dirname(fileURLToPath(import.meta.url));
const config=JSON.parse(await readFile(resolve(base,process.argv[2]||'server-config.json'),'utf8'));
const root=await realpath(resolve(base,config.release,'public'));
const origins=new Set(['https://synaiq-ai.com',`http://127.0.0.1:${config.port}`]);
const hosts=new Set(['synaiq-ai.com',`127.0.0.1:${config.port}`]);
const allowedPeers=new Set(['127.0.0.1','100.64.84.58']);
const allowedGet=/^\/api\/(?:auth\/session|alarms\/demo|devices(?:\/[A-Za-z0-9_-]{1,64}(?:\/(?:measurements|history|records))?)?)$/;
const allowedPost=/^\/api\/(?:auth\/(?:login|logout)|alarms\/demo)$/;
const target=new URL(config.bffTarget);
if(target.hostname!=='127.0.0.1')throw Error('BFF target must be loopback');
const manifest=JSON.parse(await readFile(resolve(base,config.release,'manifest.json'),'utf8'));
const published=new Set(manifest.files.map(f=>'/'+f.path));
const types={'.html':'text/html; charset=utf-8','.css':'text/css; charset=utf-8','.js':'text/javascript; charset=utf-8','.mjs':'text/javascript; charset=utf-8','.json':'application/json; charset=utf-8','.svg':'image/svg+xml','.png':'image/png','.txt':'text/plain; charset=utf-8'};
const buckets=new Map();let active=0;
function consume(ip,kind,limit){const now=Date.now(),key=ip+':'+kind;let b=buckets.get(key);if(!b||now>b.until){b={count:0,until:now+60000};buckets.set(key,b);}return ++b.count<=limit;}
setInterval(()=>{const now=Date.now();for(const[k,v]of buckets)if(now>v.until)buckets.delete(k);},60000).unref();
const answer=(res,code,detail)=>{res.writeHead(code,{'Content-Type':'application/json; charset=utf-8'});res.end(JSON.stringify({detail}));};
async function handle(req,res){
 res.setHeader('Cache-Control','no-store');res.setHeader('X-Content-Type-Options','nosniff');res.setHeader('Referrer-Policy','no-referrer');res.setHeader('X-Frame-Options','SAMEORIGIN');res.setHeader('X-Robots-Tag','noindex, nofollow');
 const peer=req.socket.remoteAddress;
 if(!allowedPeers.has(peer)||!hosts.has(req.headers.host)){answer(res,403,'not allowed');return;}
 let url;try{url=new URL(req.url,'http://'+req.headers.host);}catch{answer(res,400,'invalid URL');return;}
 if(!url.pathname.startsWith('/ems/')){answer(res,404,'not found');return;}
 const pathname=url.pathname.slice(4);
 if(pathname.startsWith('/api/')){
  res.setHeader('Content-Security-Policy',"default-src 'none'; frame-ancestors 'none'");
  if(!(req.method==='GET'&&allowedGet.test(pathname))&&!(req.method==='POST'&&allowedPost.test(pathname))){answer(res,404,'unsupported route');return;}
  if(req.method==='POST'&&!origins.has(req.headers.origin)){answer(res,403,'origin check failed');return;}
  const ip=peer==='100.64.84.58'?String(req.headers['x-real-ip']||peer).slice(0,64):peer;
  if(!consume(ip,'api',120)||(pathname==='/api/auth/login'&&!consume(ip,'login',5))){res.setHeader('Retry-After','60');answer(res,429,'too many requests');return;}
  if(active>=4){res.setHeader('Retry-After','3');answer(res,503,'busy, retry shortly');return;}
  active++;res.once('close',()=>{active--;});
  const chunks=[];let size=0;
  for await(const chunk of req){size+=chunk.length;if(size>8192){answer(res,413,'body too large');return;}chunks.push(chunk);}
  const headers={accept:'application/json'};
  for(const name of ['content-type','origin'])if(req.headers[name])headers[name]=req.headers[name];
  const session=String(req.headers.cookie||'').split(';').map(s=>s.trim()).find(s=>s.startsWith('ems_bff_session='));if(session)headers.cookie=session;
  if(size)headers['content-length']=size;
  const upstream=http.request(new URL(pathname+url.search,target),{method:req.method,headers,timeout:15000},reply=>{
   res.statusCode=reply.statusCode;
   for(const name of ['content-type','retry-after'])if(reply.headers[name])res.setHeader(name,reply.headers[name]);
   if(reply.headers['set-cookie'])res.setHeader('Set-Cookie',reply.headers['set-cookie'].filter(c=>c.startsWith('ems_bff_session=')).map(c=>c.replace(/;\s*Path=\/([;]|$)/i,'; Path=/ems/$1')));
   reply.on('error',()=>res.destroy());reply.pipe(res);
  });
  upstream.on('timeout',()=>upstream.destroy(Error('timeout')));
  upstream.on('error',()=>{if(!res.headersSent)answer(res,502,'EMS backend unavailable');else res.destroy();});
  res.once('close',()=>upstream.destroy());upstream.end(Buffer.concat(chunks));return;
 }
 if(!['GET','HEAD'].includes(req.method)){answer(res,405,'method not allowed');return;}
 const relative=pathname==='/'?'/index.html':pathname;
 if(!published.has(relative)){answer(res,404,'not found');return;}
 try{
  const file=await realpath(resolve(root,'.'+relative));
  if(!file.startsWith(root+sep)||!(await stat(file)).isFile()||!types[extname(file)]){answer(res,404,'not found');return;}
  res.setHeader('Content-Type',types[extname(file)]);
  if(extname(file)==='.html')res.setHeader('Content-Security-Policy',"default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; frame-src 'self'; frame-ancestors 'self'; base-uri 'self'; form-action 'self'; object-src 'none'");
  if(req.method==='HEAD')res.end();else res.end(await readFile(file));
 }catch{answer(res,404,'not found');}
}
for(const address of ['127.0.0.1',config.tailscaleAddress]){
 const server=http.createServer((req,res)=>handle(req,res).catch(()=>{if(!res.headersSent)answer(res,500,'request failed');else res.destroy();}));
 server.headersTimeout=10000;server.requestTimeout=20000;
 server.on('error',e=>{console.error(e.message);process.exit(1);});
 server.listen(config.port,address,()=>console.log(`EMS publication listener ${address}:${config.port}/ems/`));
}
