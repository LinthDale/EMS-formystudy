from pathlib import Path
import json, subprocess, re
root=Path('/home/dalelin/synaiq/EMS')
private=root/'.local'
credential=private/'ems-preview-login.json'
credential.chmod(0o600)
(private/'ems-preview-login.before-demo.json').chmod(0o600)
data=json.loads(credential.read_text(encoding='utf-8-sig'))
assert re.fullmatch(r'[a-zA-Z0-9_.-]{1,64}',data['username'])
assert data['username']=='demo'
script='import sys,json; from argon2 import PasswordHasher; c=json.load(sys.stdin); sys.stdout.write(PasswordHasher().hash(c["password"]))'
result=subprocess.run(['docker','exec','-i','ems-bff','python','-c',script],input=json.dumps(data),text=True,capture_output=True,check=True)
phc=result.stdout.strip()
assert phc.startswith('$argon2id$') and len(phc.split('$'))==6
env=root/'.env'
backup=private/'env-before-demo-login-20260923'
if not backup.exists(): backup.write_bytes(env.read_bytes()); backup.chmod(0o600)
lines=env.read_text().splitlines()
key='BFF_AUTH_USERS='
assert sum(line.startswith(key) for line in lines)==1
raw=next(line[len(key):].strip().strip('\"\'') for line in lines if line.startswith(key))
records=[r for r in raw.split(';') if r and r.split(':',1)[0] not in {'local-ops','demo'}]
records.append(data['username']+':'+phc+':ops')
replacement=key+"'"+';'.join(records)+"'"
env.write_text('\n'.join(replacement if line.startswith(key) else line for line in lines)+'\n')
print('Updated demo credentials with Argon2id; local-ops removed; secrets not printed')
