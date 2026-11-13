import http from 'node:http';
import {readFile,stat,realpath} from 'node:fs/promises';
import {resolve,extname,sep,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
const base=dirname(fileURLToPath(import.meta.url));
const config=JSON.parse(await readFile(resolve(base,'server-config.json'),'utf8'));
const root=await realpath(resolve(base,'public'));
const origins=new Set([`http://127.0.0.1:${config.port}`,`http://localhost:${config.port}`]);
const hosts=new Set([...origins].map(o=>new URL(o).host));
const target=new URL(config.bffTarget);
if(!['127.0.0.1','localhost','[::1]'].includes(target.hostname))throw Error('BFF target must be loopback');
const allowedGet=/^\/api\/(?:auth\/session|alarms\/demo|devices(?:\/[A-Za-z0-9_-]{1,64}(?:\/(?:measurements|history|records))?)?)$/;
const allowedPost=/^\/api\/(?:auth\/(?:login|logout)|alarms\/demo)$/;
const types={'.html':'text/html; charset=utf-8','.css':'text/css; charset=utf-8','.js':'text/javascript; charset=utf-8','.mjs':'text/javascript; charset=utf-8','.json':'application/json; charset=utf-8','.svg':'image/svg+xml','.png':'image/png'};
const answer=(res,code,body)=>{res.writeHead(code,{'Content-Type':'application/json; charset=utf-8'});res.end(JSON.stringify({detail:body}));};
const server=http.createServer(async(req,res)=>{
 res.setHeader('Cache-Control','no-store');res.setHeader('X-Content-Type-Options','nosniff');res.setHeader('Referrer-Policy','no-referrer');res.setHeader('X-Frame-Options','SAMEORIGIN');
 if(!hosts.has(req.headers.host)){answer(res,403,'host not allowed');return;}
 let url;try{url=new URL(req.url,'http://'+req.headers.host);}catch{answer(res,400,'invalid URL');return;}
 if(url.pathname.startsWith('/api/')){
  if(!(req.method==='GET'&&allowedGet.test(url.pathname))&&!(req.method==='POST'&&allowedPost.test(url.pathname))){answer(res,404,'unsupported preview route');return;}
  if(req.method==='POST'&&!origins.has(req.headers.origin)){answer(res,403,'origin check failed');return;}
  const chunks=[];let size=0;
  for await(const chunk of req){size+=chunk.length;if(size>config.maxBodyBytes){answer(res,413,'body too large');return;}chunks.push(chunk);}
  const headers={accept:'application/json'};
  for(const name of ['cookie','content-type','origin'])if(req.headers[name])headers[name]=req.headers[name];
  if(size)headers['content-length']=size;
  const upstream=http.request(new URL(url.pathname+url.search,target),{method:req.method,headers,timeout:config.timeoutMs},reply=>{
   res.statusCode=reply.statusCode;
   for(const name of ['content-type','set-cookie','retry-after'])if(reply.headers[name])res.setHeader(name,reply.headers[name]);
   reply.on('error',()=>res.destroy());reply.pipe(res);
  });
  upstream.on('timeout',()=>upstream.destroy(Error('timeout')));
  upstream.on('error',()=>{if(!res.headersSent)answer(res,502,'BFF unavailable');else res.destroy();});
  req.on('aborted',()=>upstream.destroy());upstream.end(Buffer.concat(chunks));return;
 }
 if(!['GET','HEAD'].includes(req.method)){answer(res,405,'method not allowed');return;}
 try{
  const relative=decodeURIComponent(url.pathname==='/'?'/index.html':url.pathname);
  const path=await realpath(resolve(root,'.'+relative));
  if(!path.startsWith(root+sep)||!(await stat(path)).isFile()||!types[extname(path)]){answer(res,404,'not found');return;}
  res.setHeader('Content-Type',types[extname(path)]);
  if(req.method==='HEAD')res.end();else res.end(await readFile(path));
 }catch{answer(res,404,'not found');}
});
server.listen(config.port,'127.0.0.1',()=>console.log(`EMS preview: http://127.0.0.1:${config.port}/`));
