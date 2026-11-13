"""Actual v1 Telegraf/Timescale experiments in a private network-none namespace."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

from bench_ledger import FIELDS, reconcile

KINDS = {'baseline', 'duplicate', 'receiver-down', 'db-pause'}


def case_verdict(record):
    comparison = reconcile(record['expected'], record['actual'])
    sender = record.get('broker_ack') is True and record.get('pending_end') == 0
    checks = record.get('checks', {})
    ready = sender and checks.get('setup') is True and not record.get('errors', [])
    kind = record['kind']
    desired = comparison['pass']
    if kind == 'duplicate':
        reproduced = (len(record['expected']) == 1 and len(record['actual']) == 2
                      and len(comparison['duplicates']) == 1
                      and not any(comparison[k] for k in ('missing', 'extra', 'source_duplicates', 'mismatched')))
    elif kind == 'receiver-down':
        reproduced = (len(record['expected']) == 1 and not record['actual']
            and checks.get('receiver_down_at_send') is True and checks.get('receiver_restarted') is True
            and checks.get('settled_seconds', 0) >= 10)
    elif kind == 'db-pause':
        reproduced = desired and checks.get('database_paused_at_send') is True and checks.get('paused_seconds', 0) >= 10
    elif kind == 'baseline':
        reproduced = desired
    else:
        reproduced = False
    return dict(kind=kind, comparison=comparison, experiment_passed=bool(ready and reproduced),
                system_delivery_acceptance_passed=bool(ready and desired))


def suite_verdict(cases, cleanup_ok):
    kinds = [c['kind'] for c in cases]
    return dict(verification_passed=bool(cleanup_ok and len(kinds) == len(KINDS)
                and set(kinds) == KINDS and all(c.get('experiment_passed') is True for c in cases)),
                system_delivery_acceptance_passed=False,
                meaning='counterexamples reproduced and recovery checked; v1 has no durable central ACK/dedup')


SENDER = r'''
from pathlib import Path
import json,sys,time,threading,os
sys.path.insert(0,'/app')
from delta_device.delivery import Outbox,encode_line,drain
from delta_device.publisher import Publisher
req=json.load(sys.stdin)
if os.readlink('/proc/self/ns/net') != os.environ['INGEST_QA_NETNS']:
    raise RuntimeError('namespace mismatch')
box=Outbox('/evidence/'+req['kind']+'/outbox.db',1000,req['device'])
publisher=Publisher(dict(host='127.0.0.1',port=1883,client_id='sender-'+req['kind'],tls=False),req['device'])
expected,payloads=[],[]
stamp=time.time_ns()//1000*1000
for index in range(req['count']):
    snapshot=dict(voltage=230+index/10,current=5+index/100,power_kw=1+index/100,energy_kwh=1000+index/100)
    sampled=stamp+index*1000
    payload=encode_line(req['device'],snapshot,sampled)
    box.enqueue(sampled,payload,snapshot);payloads.append(payload)
    expected.append(dict(sampled_ns=sampled,**snapshot))
try:
    publisher.start()
    if not publisher.ready.wait(10):raise TimeoutError('publisher startup')
    deadline=time.monotonic()+30
    while box.pending_count() and time.monotonic()<deadline:
        drain(box,publisher.publish,100,threading.Event())
    ack=box.pending_count()==0
    if req.get('repeat'):
        ack=publisher.publish(payloads[0]) and ack
    result=dict(expected=expected,payloads=payloads,broker_ack=ack,pending_end=box.pending_count())
    Path('/evidence/'+req['kind']+'/sender.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result))
finally:publisher.close()
'''


class Experiment:
    def __init__(self, output):
        self.output = output
        self.owned = []
        self.db = self.ingest = self.worker = self.anchor = None
        self.paused = False
        self.events = []

    def call(self, args, timeout=25, input_text=None):
        done = subprocess.run(args, capture_output=True, text=True, timeout=timeout, input=input_text)
        if done.returncode:
            raise RuntimeError('private experiment command failed')
        return done.stdout.strip()

    def event(self, name, **data):
        self.events.append(dict(event=name, utc=datetime.now(timezone.utc).isoformat(),
                                monotonic=time.monotonic(), **data))
        (self.output / 'events.json').write_text(json.dumps(self.events, indent=2))

    def create(self, name, image, command, extra):
        args = ['docker', 'create', '--label', 'ems.qa.run=ingest-20261112',
                '--cpus', '.5', '--memory', '512m' if name == 'database' else '128m',
                '--pids-limit', '128'] + extra + [image] + command
        cid = self.call(args)
        self.owned.append((name, cid))
        (self.output / (name + '-command.json')).write_text(json.dumps(args, indent=2))
        self.call(['docker', 'start', cid])
        return cid

    def wait(self, predicate, seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(.15)
        raise TimeoutError('private experiment observation deadline')

    def setup(self, root):
        images = {name: self.call(['docker', 'image', 'inspect', name, '--format', '{{.Id}}'])
                  for name in ('alpine', 'eclipse-mosquitto:2', 'telegraf:1.30',
                               'timescale/timescaledb:latest-pg15', 'ems-delta-test')}
        (self.output / 'images.json').write_text(json.dumps(images, indent=2))
        source = self.output / 'source'
        shutil.copytree(root / 'services/delta', source / 'delta', ignore=shutil.ignore_patterns('__pycache__'))
        config_bytes = (root / 'services/ingest/telegraf.conf').read_bytes()
        live_config = subprocess.check_output(['docker', 'exec', 'ems-ingest', 'cat', '/etc/telegraf/telegraf.conf'], timeout=10)
        (self.output / 'running-ingest-config-check.json').write_text(json.dumps(dict(
            checkout_sha256=hashlib.sha256(config_bytes).hexdigest(),
            running_sha256=hashlib.sha256(live_config).hexdigest(), identical=config_bytes == live_config), indent=2))
        if live_config != config_bytes:
            raise RuntimeError('running Telegraf config differs from source; inspect before cloning')
        (source / 'telegraf-original.conf').write_bytes(config_bytes)
        (self.output / 'schema.sql').write_bytes((root / 'infra/timescaledb/init.sql').read_bytes())
        config = config_bytes.decode().replace('tcp://mosquitto:', 'tcp://127.0.0.1:')
        config = config.replace('host=timescaledb ', 'host=127.0.0.1 ')
        (self.output / 'telegraf.conf').write_text(config)
        (self.output / 'mosquitto.conf').write_text('listener 1883 127.0.0.1\nallow_anonymous true\npersistence false\nlog_dest stdout\nlog_type all\n')
        self.anchor = self.create('anchor', images['alpine'], ['sleep', '600'], ['--network', 'none'])
        ns = self.call(['docker', 'exec', self.anchor, 'readlink', '/proc/self/ns/net'])
        network = ['--network', 'container:' + self.anchor]
        uid = f'{os.getuid()}:{os.getgid()}'
        self.create('broker', images['eclipse-mosquitto:2'], ['mosquitto', '-c', '/qa.conf'],
                    network + ['--user', uid, '-v', str(self.output / 'mosquitto.conf') + ':/qa.conf:ro'])
        self.db = self.create('database', images['timescale/timescaledb:latest-pg15'],
            ['postgres', '-c', 'shared_buffers=32MB', '-c', 'max_connections=20'],
            network + ['-e', 'POSTGRES_HOST_AUTH_METHOD=trust', '-e', 'POSTGRES_DB=ems',
                       '-e', 'PGDATA=/var/lib/postgresql/data/pgdata', '-e', 'TIMESCALEDB_TELEMETRY=off',
                       '--tmpfs', '/var/lib/postgresql/data:rw,size=256m',
                       '-v', str(self.output / 'schema.sql') + ':/docker-entrypoint-initdb.d/01-schema.sql:ro'])
        def ready():
            result = subprocess.run(['docker', 'exec', self.db, 'psql', '-U', 'postgres', '-d', 'ems',
                                     '-At', '-c', "SELECT to_regclass('public.electricity_measurements') IS NOT NULL"],
                                    capture_output=True, text=True, timeout=5)
            return result.returncode == 0 and result.stdout.strip() == 't'
        self.wait(ready, 40)
        self.worker = self.create('worker', images['ems-delta-test'], ['sleep', '600'],
            network + ['--user', uid, '-e', 'PYTHONDONTWRITEBYTECODE=1', '-e', 'INGEST_QA_NETNS=' + ns,
                       '-v', str(source / 'delta') + ':/app:ro', '-v', str(self.output) + ':/evidence'])
        self.ingest = self.create('ingest', images['telegraf:1.30'], ['telegraf', '--config', '/qa.conf'],
            network + ['--user', uid, '-e', 'POSTGRES_PASSWORD=',
                       '-v', str(self.output / 'telegraf.conf') + ':/qa.conf:ro'])
        self.wait(lambda: self.subscriptions() >= 1, 15)
        self.event('private_setup_ready', anchor=self.anchor, namespace=ns,
                   network_mode='none', host_ports=[], config_changes=['loopback endpoint substitution only'])

    def subscriptions(self):
        broker = next(cid for name, cid in self.owned if name == 'broker')
        done = subprocess.run(['docker', 'logs', broker], capture_output=True, text=True, timeout=5)
        if done.returncode:
            raise RuntimeError('private broker log query failed')
        return (done.stdout + done.stderr).count('Received SUBSCRIBE from ems-ingest')

    def database_rows(self, kind):
        if kind not in KINDS:
            raise ValueError('fixed QA case required')
        device = 'delta-ingest-qa-' + kind
        sql = ("SELECT COALESCE(json_agg(r),'[]'::json) FROM (SELECT "
               "(extract(epoch FROM time)*1000000000)::bigint AS sampled_ns,voltage,current,power_kw,energy_kwh "
               f"FROM electricity_measurements WHERE device_id='{device}' ORDER BY time) r")
        return json.loads(self.call(['docker', 'exec', self.db, 'psql', '-U', 'postgres', '-d', 'ems', '-At', '-c', sql]))

    def send(self, kind, count, repeat=False):
        (self.output / kind).mkdir()
        request = dict(kind=kind, device='delta-ingest-qa-' + kind, count=count, repeat=repeat)
        raw = self.call(['docker', 'exec', '-i', self.worker, 'python', '-c', SENDER],
                        timeout=45, input_text=json.dumps(request))
        return json.loads(raw)

    def measure(self):
        cases = []
        for kind in ('baseline', 'duplicate', 'receiver-down', 'db-pause'):
            self.event('case_start', kind=kind)
            checks = dict(setup=True)
            if kind == 'receiver-down':
                subscriptions = self.subscriptions()
                self.call(['docker', 'stop', '-t', '10', self.ingest])
                checks['receiver_down_at_send'] = self.call(['docker', 'inspect', self.ingest, '--format', '{{.State.Running}}']) == 'false'
            if kind == 'db-pause':
                self.call(['docker', 'pause', self.db])
                self.paused = True
                paused_at = time.monotonic()
                checks['database_paused_at_send'] = self.call(['docker', 'inspect', self.db, '--format', '{{.State.Paused}}']) == 'true'
            sent = self.send(kind, 3 if kind == 'baseline' else 10 if kind == 'db-pause' else 1,
                             repeat=kind == 'duplicate')
            self.event('sender_confirmed', kind=kind, broker_ack=sent['broker_ack'], pending=sent['pending_end'])
            if kind == 'receiver-down':
                checks['database_before_restart'] = len(self.database_rows(kind))
                self.call(['docker', 'start', self.ingest])
                self.wait(lambda: self.subscriptions() > subscriptions, 15)
                checks['receiver_restarted'] = True
                settled = time.monotonic()
                time.sleep(10)
                checks['settled_seconds'] = time.monotonic() - settled
            elif kind == 'db-pause':
                time.sleep(10)
                checks['paused_seconds'] = time.monotonic() - paused_at
                self.call(['docker', 'unpause', self.db])
                self.paused = False
                self.wait(lambda: len(self.database_rows(kind)) >= 10, 30)
            else:
                self.wait(lambda: len(self.database_rows(kind)) >= (2 if kind == 'duplicate' else 3), 20)
            record = dict(kind=kind, **sent, actual=self.database_rows(kind), checks=checks, errors=[])
            verdict = case_verdict(record)
            record.update(verdict)
            (self.output / kind / 'result.json').write_text(json.dumps(record, indent=2))
            cases.append(verdict)
            self.event('case_end', **verdict)
            print(json.dumps(verdict), flush=True)
            if not verdict['experiment_passed']:
                break
        if len(cases) == len(KINDS):
            # Observe a further flush window; do not accept only the first count threshold.
            time.sleep(6)
            final = []
            records = []
            for case in cases:
                record = json.loads((self.output / case['kind'] / 'result.json').read_text())
                record['actual'] = self.database_rows(case['kind'])
                verdict = case_verdict(record)
                record.update(verdict)
                records.append(record)
                final.append(verdict)
            (self.output / 'final-recheck.json').write_text(json.dumps(records, indent=2))
            return final
        return cases

    def cleanup(self):
        results = []
        if self.paused and self.db:
            try:
                self.call(['docker', 'unpause', self.db])
            except Exception:
                results.append(dict(action='unpause', passed=False))
        for name, cid in reversed(self.owned):
            try:
                logs = subprocess.run(['docker', 'logs', cid], capture_output=True, text=True, timeout=10)
                if logs.returncode:
                    raise RuntimeError('log query failed')
                (self.output / (name + '.log')).write_text(logs.stdout + logs.stderr)
            except Exception:
                results.append(dict(action='logs', name=name, passed=False))
            try:
                self.call(['docker', 'rm', '-f', cid], timeout=15)
                results.append(dict(action='remove', name=name, container=cid, passed=True))
            except Exception:
                results.append(dict(action='remove', name=name, container=cid, passed=False))
        return results


def run(output):
    output.mkdir(parents=True, exist_ok=False)
    root = Path(__file__).resolve().parents[3]
    experiment = Experiment(output)
    state = dict(started_utc=datetime.now(timezone.utc).isoformat(), scope='private actual v1 ingest clone, not shared DB fault injection')
    cases = []
    source_hashes = {}
    for folder in ('delta_device', 'tools'):
        for path in (root / 'services/delta' / folder).glob('*.py'):
            source_hashes[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    (output / 'source-sha256.json').write_text(json.dumps(source_hashes, indent=2))
    (output / 'containers-before.jsonl').write_text(subprocess.check_output(['docker', 'ps', '--format', 'json'], text=True))
    try:
        experiment.setup(root)
        cases = experiment.measure()
    except Exception as exc:
        state['error_kind'] = type(exc).__name__
    finally:
        cleanup = experiment.cleanup()
        unchanged = all(hashlib.sha256((root / p).read_bytes()).hexdigest() == h for p, h in source_hashes.items())
        state.update(suite_verdict(cases, bool(cleanup) and all(c['passed'] for c in cleanup)))
        state.update(cases=cases, cleanup=cleanup, sources_unchanged=unchanged,
                     finished_utc=datetime.now(timezone.utc).isoformat())
        state['verification_passed'] = state['verification_passed'] and unchanged and 'error_kind' not in state
        (output / 'result.json').write_text(json.dumps(state, indent=2))
    return state


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    outcome = run(parser.parse_args().output.resolve())
    print(json.dumps(outcome))
    raise SystemExit(0 if outcome['verification_passed'] else 1)
