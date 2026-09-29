import json, os, secrets, subprocess
from pathlib import Path
root=Path('/home/dalelin/synaiq/EMS')
env=root/'.env'
text=env.read_text()
if any(line.startswith('BFF_AUTH_USERS=') and line.split('=',1)[1].strip().strip('\"\'') for line in text.splitlines()):
    raise SystemExit('Existing users found; refusing overwrite')
password=secrets.token_urlsafe(24)
hashed=subprocess.run(['docker','exec','-i','ems-bff','python','-c','import sys; from argon2 import PasswordHasher; print(PasswordHasher().hash(sys.stdin.read()))'],input=password,text=True,capture_output=True,check=True).stdout.strip()
record='local-ops:'+hashed+':ops'
lines=[line for line in text.splitlines() if not line.startswith('BFF_AUTH_USERS=')]
lines.append("BFF_AUTH_USERS='"+record+"'")
key='BFF_PUBLIC_ORIGINS='
old=next((line.split('=',1)[1].strip().strip('\"\'') for line in lines if line.startswith(key)), 'http://localhost:5173,http://localhost:8003,http://localhost:8080,http://127.0.0.1:5173,http://127.0.0.1:8003,http://127.0.0.1:8080')
origins=list(dict.fromkeys(old.split(',')+['http://localhost:4178','http://127.0.0.1:4178']))
lines=[line for line in lines if not line.startswith(key)]
lines.append(key+','.join(origins))
env.write_text('\n'.join(lines)+'\n')
private=root/'.local'
private.mkdir(exist_ok=True,mode=0o700)
cred=private/'ems-preview-login.json'
cred.write_text(json.dumps({'username':'local-ops','password':password},indent=2)+'\n')
os.chmod(cred,0o600)
ignore=root/'.gitignore'
with ignore.open('a') as f:f.write('\n# Local credentials and runtime-only user files\n.local/\n')
print('Created local-ops account; credentials saved privately; origins include localhost:4178. No secret values printed.')
