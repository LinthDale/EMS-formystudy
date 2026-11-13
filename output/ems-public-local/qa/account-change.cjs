const {request}=require('C:/Users/User/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
(async()=>{
 const privateDir=path.resolve(__dirname,'../../../.local');
 const current=JSON.parse(fs.readFileSync(path.join(privateDir,'ems-preview-login.json'),'utf8'));
 const previous=JSON.parse(fs.readFileSync(path.join(privateDir,'ems-preview-login.before-demo.json'),'utf8'));
 assert.equal(current.username,'demo');
 for(const [base,prefix] of [['http://127.0.0.1:4178',''],['https://synaiq-ai.com','/ems']]){
  const api=await request.newContext({baseURL:base,extraHTTPHeaders:{Origin:base}});
  try{
   assert.equal((await api.post(prefix+'/api/auth/login',{data:previous})).status(),401,'old account disabled');
   const login=await api.post(prefix+'/api/auth/login',{data:current});assert.equal(login.status(),200);
   const data=await login.json();assert.equal(data.username,'demo');assert.equal(data.role,'ops');
   const localHeaders=base.startsWith('http:')?{Cookie:login.headers()['set-cookie'].split(';')[0]}:{};
   assert.equal((await api.get(prefix+'/api/devices',{headers:localHeaders})).status(),200);
   assert.equal((await api.post(prefix+'/api/auth/logout',{headers:localHeaders})).status(),204);
   assert.equal((await api.get(prefix+'/api/auth/session')).status(),401);
   console.log('PASS demo login and old account rejected:',base);
  }finally{await api.dispose();}
 }
 const release=path.resolve(__dirname,'../releases/20260923-local-v3/public');
 function scan(dir){for(const e of fs.readdirSync(dir,{withFileTypes:true})){const p=path.join(dir,e.name);if(e.isDirectory())scan(p);else assert.ok(!fs.readFileSync(p).includes(Buffer.from(current.password)),'Secret must not appear in public files');}}
 scan(release);console.log('PASS no password in published files');
})().catch(e=>{console.error(e);process.exit(1)});

