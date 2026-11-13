import http from 'node:http';
import {readFile,realpath,stat} from 'node:fs/promises';
import {openSync,writeSync,closeSync,readdirSync,statSync,mkdirSync,unlinkSync} from 'node:fs';
import {resolve,dirname,extname,sep} from 'node:path';
import {fileURLToPath} from 'node:url';
const base=dirname(fileURLToPath(import.meta.url)),logDir=resolve(base,'logs');
const stamp=()=>{const d=new Date(),o=-d.getTimezoneOffset(),a=Math.abs(o);return new Date(d.getTime()+o*6e4).toISOString().slice(0,23)+(o<0?'-':'+')+String(a/60|0).padStart(2,'0')+':'+String(a%60).padStart(2,'0');};
// Node owns the log: logs/server-NNNNNN.log. At logMax bytes the next number is started and only the newest logKeep files are kept.
// Files are never renamed, so viewers following them can never block a rotation. Anything printed outside log() goes to the launcher's catch-all file.
let logFd=-1,logSize=0,logMax=5242880,logKeep=20;
const logFiles=()=>{try{return readdirSync(logDir).filter(n=>/^server-\d{6}\.log$/.test(n)).sort();}catch{return[];}};
function logOpen(next){
 if(logFd>=0)try{closeSync(logFd);}catch{}
 logFd=-1;mkdirSync(logDir,{recursive:true});
 const last=logFiles().at(-1),name=!next&&last&&statSync(resolve(logDir,last)).size<logMax?last:`server-${String((last?+last.slice(7,13):0)+1).padStart(6,'0')}.log`;
 logFd=openSync(resolve(logDir,name),'a');logSize=statSync(resolve(logDir,name)).size;
 for(const old of logFiles().slice(0,-logKeep))try{unlinkSync(resolve(logDir,old));}catch{}
}
const log=(level,text)=>{const t=stamp(),lines=String(text).split(/\r?\n/).map(line=>`${t} ${level} ${line}`).join('\n')+'\n';
 try{if(logFd<0||logSize>=logMax)logOpen(logFd>=0);logSize+=writeSync(logFd,lines);}catch{process.stderr.write(lines);}};
process.on('uncaughtException',(e,origin)=>{log('ERROR',`fatal ${origin}: ${e?.stack||e}`);process.exit(1);});
process.on('exit',code=>log(code?'ERROR':'INFO',`exit code ${code}`));
const config=JSON.parse(await readFile(resolve(base,process.argv[2]||'server-config.json'),'utf8'));
logMax=config.logMaxBytes||logMax;logKeep=config.logKeep||logKeep;
log('INFO',`start pid ${process.pid} node ${process.version} release ${config.release} listen 127.0.0.1,${config.tailscaleAddress} port ${config.port}`);
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
const action=Symbol('action'),reason=Symbol('reason'),assets=/\.(?:css|js|mjs|png|svg|json|txt)$/;
const clientIp=req=>{const peer=req.socket.remoteAddress;return peer==='100.64.84.58'?String(req.headers['x-real-ip']||peer).slice(0,64):peer;};
const answer=(res,code,detail)=>{res[reason]=detail;res.writeHead(code,{'Content-Type':'application/json; charset=utf-8'});res.end(JSON.stringify({detail}));};
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
  const chunks=[];let size=0;
  for await(const chunk of req){size+=chunk.length;if(size>8192){answer(res,413,'body too large');return;}chunks.push(chunk);}
  // Only the account name of a login is kept for the access log (clipped, control characters removed); never the password.
  if(pathname==='/api/auth/login'){let user='?';try{const u=JSON.parse(Buffer.concat(chunks)).username;if(typeof u==='string')user=u.slice(0,64).replace(/[\x00-\x1f\x7f-\x9f\u2028\u2029]/g,'');}catch{}res[action]='login user='+user;}
  else if(pathname==='/api/auth/logout')res[action]='logout';
  const ip=clientIp(req);
  if(!consume(ip,'api',120)||(pathname==='/api/auth/login'&&!consume(ip,'login',5))){res.setHeader('Retry-After','60');answer(res,429,'too many requests');return;}
  if(active>=4){res.setHeader('Retry-After','3');answer(res,503,'busy, retry shortly');return;}
  active++;res.once('close',()=>{active--;});
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
// Access log, written once the response is finished or aborted: every API call, page and rejection; successful static assets are skipped.
// Fields: client ip, method, path (with query, clipped), status, duration, bytes sent, then login/logout and the rejection reason.
function access(req,res,t0,sock,sent,ip){
 const code=res.headersSent?res.statusCode:0,done=res.writableFinished,path=String(req.url).slice(0,200).replace(/[^\x21-\x7e]/g,'?');
 if(done&&code&&code<400&&assets.test(path.split('?')[0]))return;
 const note=[res[action]&&`${res[action]} -> ${code||'-'}`,res[reason],!done&&'aborted'].filter(Boolean).join(' ');
 log(code>=500?'WARN':'INFO',`${String(ip??'-').replace(/[^\x21-\x7e]/g,'?')} ${req.method} ${path} ${code||'-'} ${Date.now()-t0}ms ${sock.bytesWritten-sent}B${note?' '+note:''}`);
}
const onRequest=(req,res)=>{const t0=Date.now(),sock=req.socket,sent=sock.bytesWritten,ip=clientIp(req);
 res.once('close',()=>{try{access(req,res,t0,sock,sent,ip);}catch(e){log('WARN',`access log failed: ${e.message}`);}});
 handle(req,res).catch(()=>{if(!res.headersSent)answer(res,500,'request failed');else res.destroy();});};
// A listener that fails before it was ever up is fatal (start-public.ps1 reports it); after that it is closed and re-bound every 5s.
for(const address of ['127.0.0.1',config.tailscaleAddress]){
 const name=`${address}:${config.port}`;let ready=false,down=0,tries=0,last='';
 const open=()=>{
  const server=http.createServer(onRequest);let failed=false;
  server.headersTimeout=10000;server.requestTimeout=20000;
  server.once('listening',()=>{log('INFO',down?`listener ${name} recovered after ${Math.round((Date.now()-down)/1000)}s (${tries} retries)`:`EMS publication listener ${name}/ems/`);ready=true;down=tries=0;last='';});
  server.on('error',e=>{if(failed)return;failed=true;const why=e.code||e.message;
   if(!ready){log('ERROR',`listener ${name} failed at startup: ${e.message}`);process.exit(1);}
   server.close();
   if(!down){down=Date.now();log('ERROR',`listener ${name} lost: ${e.message}; closed, retrying every 5s`);}
   else if(why!==last||tries%120===0)log('WARN',`listener ${name} still down, retry ${tries}: ${e.message}`);
   last=why;tries++;setTimeout(open,5000);});
  server.listen(config.port,address);
 };
 open();
}
