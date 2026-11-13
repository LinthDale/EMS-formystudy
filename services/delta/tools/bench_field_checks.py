"""Isolated real TLS and injected-clock checks; no shared broker, COM or OS clock changes."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET

SERVICE = Path(__file__).resolve().parents[1]
EXPECTED_CASES = 12


def require_private_namespace(expected, actual):
    if not expected or expected != actual:
        raise ValueError('private network-none broker namespace required')


def assess_junit(xml, returncode):
    root = ET.fromstring(xml)
    suites = list(root.iter('testsuite'))
    cases = list(root.iter('testcase'))
    counts = {key: sum(int(s.get(key, '0')) for s in suites)
              for key in ('tests', 'failures', 'errors', 'skipped')}
    identities = {(c.get('classname'), c.get('name')) for c in cases}
    passed = (returncode == 0 and counts['tests'] == len(cases) == len(identities) == EXPECTED_CASES
              and all(counts[key] == 0 for key in ('failures', 'errors', 'skipped'))
              and not any(c.find(tag) is not None for c in cases for tag in ('failure','error','skipped')))
    return dict(passed=passed, returncode=returncode, **counts)


def call(args, *, timeout=30, **kwargs):
    completed = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, timeout=timeout, **kwargs)
    if completed.returncode:
        # Never include argv: disposable passwords may be passed to mosquitto_passwd.
        raise RuntimeError('private setup command failed')
    return completed.stdout.strip()


def cleanup_owned(worker, broker, output):
    """Log collection must never prevent either owned container removal."""
    errors = []
    if broker:
        try:
            logs = subprocess.run(['docker','logs',broker],capture_output=True,text=True,timeout=10)
            if logs.returncode:
                raise RuntimeError('private broker log query failed')
            (output/'broker.log').write_text(logs.stdout+logs.stderr)
        except Exception as exc:
            errors.append(type(exc).__name__)
    cleanup = []
    for container in (worker, broker):
        if container:
            try:
                call(['docker','rm','-f',container],timeout=15)
                cleanup.append(dict(container=container,removed=True))
            except Exception:
                cleanup.append(dict(container=container,removed=False))
    return cleanup, errors


def pki(directory):
    def openssl(*args):
        return call(['openssl', *args], cwd=directory)
    for ca in ('ca', 'rogue-ca'):
        openssl('req','-x509','-newkey','rsa:2048','-nodes','-sha256','-days','2',
                '-subj',f'/CN=EMS-QA-{ca}','-addext','basicConstraints=critical,CA:TRUE',
                '-addext','keyUsage=critical,keyCertSign,cRLSign','-keyout',ca+'.key','-out',ca+'.crt')
    for name, cn, usage, signer in [
        ('server','localhost','serverAuth','ca'),
        ('wrong-host','wrong-host.invalid','serverAuth','ca'),
        ('expired','localhost','serverAuth','ca'),
        ('client','qa-edge','clientAuth','ca'),
        ('rogue-client','qa-edge','clientAuth','rogue-ca'),
    ]:
        openssl('req','-new','-newkey','rsa:2048','-nodes','-subj',f'/CN={cn}',
                '-keyout',name+'.key','-out',name+'.csr')
        ext = 'basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage='+usage+'\n'
        if usage == 'serverAuth':
            ext += 'subjectAltName=' + ('DNS:wrong-host.invalid' if name=='wrong-host'
                                       else 'DNS:localhost,IP:127.0.0.1') + '\n'
        (directory/(name+'.ext')).write_text(ext)
        if name == 'expired':
            (directory/'index.txt').touch()
            (directory/'serial').write_text('1000\n')
            (directory/'newcerts').mkdir()
            (directory/'ca.conf').write_text('[ca]\ndefault_ca=local\n[local]\n'
                'database=index.txt\nserial=serial\nnew_certs_dir=newcerts\n'
                'certificate=ca.crt\nprivate_key=ca.key\ndefault_md=sha256\n'
                'policy=policy\n[policy]\ncommonName=supplied\n')
            openssl('ca','-batch','-notext','-config','ca.conf','-in',name+'.csr',
                    '-out',name+'.crt','-extfile',name+'.ext',
                    '-startdate','20200101000000Z','-enddate','20200102000000Z')
        else:
            openssl('x509','-req','-in',name+'.csr','-CA',signer+'.crt',
                    '-CAkey',signer+'.key','-CAcreateserial','-days','2','-sha256',
                    '-extfile',name+'.ext','-out',name+'.crt')
    for key in directory.glob('*.key'):
        key.chmod(0o600)


def run(output):
    output.mkdir(parents=True, exist_ok=False)
    state = dict(passed=False, scope='private broker TLS + production edge with injected clock; not field/4G/DB ACK',
                 started_utc=datetime.now(timezone.utc).isoformat())
    broker = worker = None
    source = {str(p.relative_to(SERVICE)): hashlib.sha256(p.read_bytes()).hexdigest()
              for parent in ('delta_device','tests/field_checks') for p in (SERVICE/parent).rglob('*.py')}
    for name in ('tools/bench_field_checks.py','tools/bench_network.py','pytest.ini'):
        source[name] = hashlib.sha256((SERVICE/name).read_bytes()).hexdigest()
    (output/'source-sha256.json').write_text(json.dumps(source,indent=2)+'\n')
    for name in source:
        target = output/'source'/name
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(SERVICE/name,target)
    with tempfile.TemporaryDirectory(prefix='ems-private-field-') as temp:
        private = Path(temp)
        try:
            broker_image = call(['docker','image','inspect','eclipse-mosquitto:2','--format','{{.Id}}'])
            worker_image = call(['docker','image','inspect','ems-delta-test','--format','{{.Id}}'])
            pki(private)
            public_certificates = {}
            for cert in private.glob('*.crt'):
                public_certificates[cert.name] = call(['openssl','x509','-in',str(cert),'-noout',
                    '-fingerprint','-sha256','-subject','-issuer','-dates'])
            (output/'certificate-metadata.json').write_text(json.dumps(public_certificates,indent=2)+'\n')
            password = secrets.token_urlsafe(24)
            user = f'{os.getuid()}:{os.getgid()}'
            call(['docker','run','--rm','--network','none','--user',user,'-v',f'{private}:/qa',
                  broker_image,'mosquitto_passwd','-b','-c','/qa/passwords','qa-edge',password])
            (private/'acl').write_text('user qa-edge\ntopic readwrite ems/devices/#\n')
            config = 'per_listener_settings true\npersistence false\nlog_dest stdout\nlog_type all\n'
            for port, cert in [(1883,'server'),(8884,'wrong-host'),(8885,'expired'),(8886,'server')]:
                config += f'listener {port} 127.0.0.1\nallow_anonymous false\nacl_file /qa/acl\n'
                config += f'cafile /qa/ca.crt\ncertfile /qa/{cert}.crt\nkeyfile /qa/{cert}.key\n'
                config += ('require_certificate true\nuse_identity_as_username true\n' if port==8886
                           else 'password_file /qa/passwords\n')
            (private/'mosquitto.conf').write_text(config)
            (output/'broker-config.txt').write_text(config)
            broker = call(['docker','create','--network','none','--user',user,
                '--cpus','.25','--memory','64m','--pids-limit','32','-v',f'{private}:/qa:ro',
                broker_image,'mosquitto','-c','/qa/mosquitto.conf'])
            call(['docker','start',broker])
            namespace = call(['docker','exec',broker,'readlink','/proc/self/ns/net'])
            (private/'worker.env').write_text(f'FIELD_QA_NETNS={namespace}\nFIELD_QA_USER=qa-edge\nFIELD_QA_PASSWORD={password}\n')
            (private/'worker.env').chmod(0o600)
            state.update(broker_id=broker, broker_image=broker_image, worker_image=worker_image,
                         network='none', host_ports=[], namespace=namespace)
            worker = call(['docker','create','--network',f'container:{broker}','--user',user,
                '--cpus','.5','--memory','256m','--pids-limit','128',
                '--env-file',str(private/'worker.env'),'-e','PYTHONDONTWRITEBYTECODE=1',
                '-v',f'{SERVICE}:/app:ro','-v',f'{output}:/evidence','-v',f'{private}:/qa:ro','-w','/app',
                worker_image,'python','-m','pytest','tests/field_checks','-q','-p','no:cacheprovider',
                '--junitxml=/evidence/junit.xml'])
            with (output/'pytest.log').open('w') as log:
                ran = subprocess.run(['docker','start','-a',worker],stdout=log,stderr=subprocess.STDOUT,timeout=180)
            # docker start -a status is cross-checked with the actual container exit.
            exitcode = int(call(['docker','inspect',worker,'--format','{{.State.ExitCode}}']))
            state['assessment'] = assess_junit((output/'junit.xml').read_text(), exitcode)
            state['docker_attach_exit'] = ran.returncode
            records = json.loads((output/'cases.json').read_text())
            state['case_records'] = len(records)
            state['sources_unchanged'] = all(hashlib.sha256((SERVICE/name).read_bytes()).hexdigest()==h
                                             for name,h in source.items())
            state['tests_passed'] = (state['assessment']['passed'] and ran.returncode==0
                and len(records)==EXPECTED_CASES and len({c['case'] for c in records})==EXPECTED_CASES
                and all(c['passed'] is True for c in records) and state['sources_unchanged'])
        except Exception as exc:
            state['error_kind'] = type(exc).__name__
        finally:
            cleanup, log_errors = cleanup_owned(worker,broker,output)
            state['cleanup'] = cleanup
            state['log_errors'] = log_errors
            state['passed'] = (state.get('tests_passed',False) and bool(broker) and bool(worker)
                               and len(cleanup)==2 and all(c['removed'] for c in cleanup) and not log_errors)
            state['finished_utc'] = datetime.now(timezone.utc).isoformat()
            (output/'result.json').write_text(json.dumps(state,indent=2)+'\n')
    return state


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.output.resolve())
    print(json.dumps(result))
    raise SystemExit(0 if result['passed'] else 1)
