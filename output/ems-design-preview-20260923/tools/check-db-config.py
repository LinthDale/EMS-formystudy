import subprocess,json
containers={}
for name in ['ems-device-service-mcp','ems-device-service']:
 data=json.loads(subprocess.run(['docker','inspect',name],capture_output=True,text=True,check=True).stdout)[0]
 containers[name]=dict(x.split('=',1) for x in data['Config']['Env'] if '=' in x)
for key in ['DB_AI_PASSWORD','DB_OPS_PASSWORD']:
 print(key,'same_in_working_and_new=',containers['ems-device-service-mcp'].get(key)==containers['ems-device-service'].get(key))
script='''import asyncio,os,asyncpg
async def main():
 for role,key in [('device_service_ai','DB_AI_PASSWORD'),('device_service_ops','DB_OPS_PASSWORD')]:
  try:
   c=await asyncpg.connect(host='timescaledb',database='ems',user=role,password=os.environ.get(key),timeout=5)
   await c.fetchval('SELECT 1');await c.close();print(role+': verified')
  except Exception as e:print(role+': '+type(e).__name__)
asyncio.run(main())'''
r=subprocess.run(['docker','exec','-i','ems-device-service-mcp','python','-'],input=script,capture_output=True,text=True)
print(r.stdout)
