const {request}=require('C:/Users/User/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
(async()=>{const root='https://synaiq-ai.com';const api=await request.newContext({baseURL:root});try{
 for(const [route,status]of [['/ems/api/auth/session',401],['/ems/api/devices',401],['/ems/api/admin',404],['/ems/.env',404],['/ems/server-config.json',404],['/ems/.local/ems-preview-login.json',404]]){
  const response=await api.get(route);assert.equal(response.status(),status,route);console.log('BOUNDARY',status,route);
 }
 assert.equal((await api.post('/ems/api/auth/login',{data:{},headers:{Origin:'https://not-allowed.invalid'}})).status(),403);
 assert.equal((await api.put('/ems/api/devices/sim-001',{data:{},headers:{Origin:root}})).status(),404);
 const credentials=JSON.parse(fs.readFileSync(path.resolve(__dirname,'../../../.local/ems-preview-login.json'),'utf8'));
 const login=await api.post('/ems/api/auth/login',{data:credentials,headers:{Origin:root}});assert.equal(login.status(),200);
 const cookies=(await api.storageState()).cookies;const session=cookies.find(c=>c.name==='ems_bff_session');
 assert.ok(session);assert.equal(session.path,'/ems/');assert.ok(session.secure&&session.httpOnly);assert.equal(session.sameSite,'Strict');
 console.log('COOKIE path=/ems/ Secure HttpOnly SameSite=Strict');
 assert.equal((await api.get('/ems/api/auth/session')).status(),200);
 assert.equal((await api.post('/ems/api/auth/logout',{headers:{Origin:root}})).status(),204);
 assert.equal((await api.get('/ems/api/auth/session')).status(),401);
 assert.ok(!(await api.storageState()).cookies.some(c=>c.name==='ems_bff_session'));
 const rejected=await api.get('http://100.114.126.85:4179/ems/',{headers:{Host:'synaiq-ai.com'}});assert.equal(rejected.status(),403);
 console.log('PASS public login/logout, cookie scope, CSRF, API allowlist, private files, non-gateway source rejection');
 }finally{await api.dispose();}})().catch(e=>{console.error(e);process.exit(1)});

