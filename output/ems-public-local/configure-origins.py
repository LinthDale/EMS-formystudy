from pathlib import Path
import os
root=Path('/home/dalelin/synaiq/EMS')
env=root/'.env'
backup=root/'.local/env-before-public-ems-20260923'
if not backup.exists():
    backup.write_bytes(env.read_bytes())
    backup.chmod(0o600)
lines=env.read_text().splitlines()
key='BFF_PUBLIC_ORIGINS='
existing=next((l[len(key):].strip('"\'') for l in lines if l.startswith(key)),None)
if existing is None:
    raise SystemExit('Expected explicit BFF_PUBLIC_ORIGINS; inspect before changing')
origins=existing.split(',')
for origin in ['https://synaiq-ai.com','http://127.0.0.1:4179']:
    if origin not in origins: origins.append(origin)
env.write_text('\n'.join(key+','.join(origins) if l.startswith(key) else l for l in lines)+'\n')
print('Added public and staging origins; other environment values preserved')
