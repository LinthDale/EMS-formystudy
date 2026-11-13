"""Owned TLS probes, bounded tmpfs ENOSPC, and real guarded PG recovery."""
import hashlib
from datetime import datetime,timezone
import json
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

from private_wal import PrivateWal

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from edge_receiver.backup_preflight import inspect_archive,verify_backup

TLS_CASES=('wrong_ca','wrong_host','expired','missing_client','untrusted_client','expired_client','wrong_user','plaintext')
SECURE_OPERATIONS=frozenset(('db_cert_good','db_cert_wrong_host','db_cert_expired','wal_resume',
    'wal_full','wal_free','wal_status','wal_caught_up','recovery_matrix','db_client_probe_begin','db_client_probe_end','db_client_probe_end_expired',
    'wal_gate_plaintext','wal_gate_wrong_role',*('wal_probe_'+c for c in TLS_CASES)))


class PrivateWalSecurity(PrivateWal):
    def start_wal(self,database,port=5432,suffix=''):
        self.sql(database,"SELECT pg_create_physical_replication_slot('ems_archive_slot',true)",port)
        cid=self.create('wal-receiver'+suffix,self.image,self.network+self.client_mount()+['--user',self.uid,
            '--tmpfs','/wal:rw,size=128m,uid='+self.uid.split(':')[0]+',gid='+self.uid.split(':')[1]+',mode=0700'],['sleep','1800'])
        self.wal=cid;self.database=database
        self.launch()
        self.sql(database,"ALTER SYSTEM SET synchronous_standby_names='FIRST 1 (ems_archive)'",port)
        self.sql(database,'SELECT pg_reload_conf()',port);self.wait_sync(database,port)
        return cid

    def launch(self):
        self.call(['docker','exec',self.wal,'sh','-ec','rm -f /tmp/wal.exit'])
        command=('pg_receivewal -d "$1" -D /wal --synchronous -s 1 -S ems_archive_slot --no-loop --verbose '
                 '>> /tmp/wal.log 2>&1; result=$?; printf "%s" "$result" > /tmp/wal.exit')
        self.call(['docker','exec','-d',self.wal,'sh','-c',command,'wal-job',
                   self.connection(user='ems_wal_archive')+' application_name=ems_archive'])

    def stopped(self):
        return subprocess.run(['docker','exec',self.wal,'test','-f','/tmp/wal.exit'],capture_output=True,timeout=3).returncode==0

    def stop(self):
        self.call(['docker','exec',self.wal,'sh','-ec','if pgrep -x pg_receivewal >/dev/null; then pkill -INT -x pg_receivewal; fi'])
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            if self.stopped():return
            time.sleep(.03)
        raise TimeoutError('owned WAL child did not exit')

    def certificate(self,name):
        if name not in ('server','wrong-host','expired'):raise ValueError('invalid fixed server certificate')
        # Fixed files, no worker path/SQL/certificate material supplied.
        self.call(['docker','exec','--user','0:0',self.database,'cp','/qa-pg/'+name+'.crt','/run/pg-tls/server.crt'])
        self.call(['docker','exec','--user','0:0',self.database,'cp','/qa-pg/'+name+'.key','/run/pg-tls/server.key'])
        self.call(['docker','exec','--user','0:0',self.database,'sh','-ec',
            'chown postgres:postgres /run/pg-tls/server.crt /run/pg-tls/server.key; chmod 600 /run/pg-tls/server.key'])
        # Local operator socket permits restoring even an invalid server cert;
        # application/replication connections still require verified TLS.
        self.call(['docker','exec',self.database,'psql','-U','postgres','-d','ems','-c','SELECT pg_reload_conf()'])
        expected=self.call(['openssl','x509','-in',str(self.private/(name+'.crt')),'-noout','-fingerprint','-sha256']).split('=',1)[1].replace(':','').lower()
        stored=self.call(['openssl','x509','-noout','-fingerprint','-sha256'],
            input_text=self.call(['docker','exec',self.database,'cat','/run/pg-tls/server.crt'])).split('=',1)[1].replace(':','').lower()
        if stored!=expected:raise ValueError('container TLS certificate file did not match fixed source')
        worker=[cid for role,cid in self.owned if role=='worker']
        if len(worker)!=1:raise ValueError('owned TLS observer unavailable')
        # Inspect only the public certificate after PostgreSQL's SSLRequest;
        # no credentials or application data go over this diagnostic socket.
        code=("import socket,ssl,struct,hashlib; s=socket.create_connection(('127.0.0.1',5432),2); "
              "s.sendall(struct.pack('!II',8,80877103)); assert s.recv(1)==b'S'; "
              "c=ssl._create_unverified_context(); t=c.wrap_socket(s,server_hostname='127.0.0.1'); "
              "print(hashlib.sha256(t.getpeercert(binary_form=True)).hexdigest()); t.close()")
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            actual=self.call(['docker','exec',worker[0],'python','-c',code])
            if actual==expected:
                self.publish(self.output/'last-server-certificate.json',json.dumps(dict(name=name,expected_sha256=expected,observed_sha256=actual)))
                return
            time.sleep(.1)
        raise ValueError('PostgreSQL did not present the requested certificate after reload')

    def probe(self,kind):
        self.stop()
        if kind in ('wrong_host','expired'):self.certificate('wrong-host' if kind=='wrong_host' else 'expired')
        values=dict(host='127.0.0.1',port='5432',user='ems_wal_archive',application_name='ems_archive',
            sslmode='verify-full',sslrootcert='/pg-client/ca.crt',sslcert='/pg-client/archive.crt',sslkey='/pg-client/archive.key')
        if kind=='wrong_ca':values['sslrootcert']='/pg-client/rogue-ca.crt'
        elif kind=='missing_client':values.pop('sslcert');values.pop('sslkey')
        elif kind=='untrusted_client':values.update(sslcert='/pg-client/rogue-receiver.crt',sslkey='/pg-client/receiver.key')
        elif kind=='expired_client':values['sslcert']='/pg-client/expired-archive.crt'
        elif kind=='wrong_user':values['user']='postgres'
        elif kind=='plaintext':values['sslmode']='disable'
        connection=' '.join(k+'='+v for k,v in values.items())
        cid=self.create('wal-probe-'+kind,self.image,self.network+self.client_mount()+['--user',self.uid,
            '--tmpfs','/probe:rw,size=32m,uid='+self.uid.split(':')[0]+',gid='+self.uid.split(':')[1]+',mode=0700'],
            ['pg_receivewal','-d',connection,'-D','/probe','--synchronous','--no-loop','-S','ems_archive_slot'])
        code=self.call(['docker','wait',cid],timeout=15)
        logs=subprocess.run(['docker','logs',cid],text=True,capture_output=True,timeout=5)
        text=logs.stdout+logs.stderr
        patterns={'wrong_ca':('certificate verify failed',),'wrong_host':('does not match host name','IP address mismatch'),
            'expired':('certificate verify failed',),'missing_client':('requires a valid client certificate',),
            'untrusted_client':('unknown ca','certificate verify failed','certificate unknown'),
            'expired_client':('certificate expired','certificate has expired','certificate verify failed'),
            'wrong_user':('certificate authentication failed',),'plaintext':('pg_hba.conf rejects replication connection','no encryption')}
        if code=='0' or not any(p.lower() in text.lower() for p in patterns[kind]):
            raise ValueError('WAL TLS probe failed for an unexpected reason')
        verify_code=None
        client_verify_code=None
        if kind=='expired_client':
            checked=subprocess.run(['openssl','verify','-CAfile',str(self.private/'ca.crt'),
                str(self.private/'pg-client/expired-archive.crt')],text=True,capture_output=True,timeout=5)
            if checked.returncode==0 or 'error 10 at' not in checked.stdout+checked.stderr:
                raise ValueError('client certificate was not independently verified expired')
            client_verify_code=10
        if kind in ('wrong_ca','wrong_host','expired'):
            worker=[cid for name,cid in self.owned if name=='worker'][0]
            ca='/qa/pg-client/rogue-ca.crt' if kind=='wrong_ca' else '/qa/pg-client/ca.crt'
            script=("import socket,ssl,struct,json\n"
                "s=socket.create_connection(('127.0.0.1',5432),2); s.sendall(struct.pack('!II',8,80877103)); assert s.recv(1)==b'S'\n"
                f"c=ssl.create_default_context(cafile='{ca}'); c.load_cert_chain('/qa/pg-client/archive.crt','/qa/pg-client/archive.key')\n"
                "try:\n c.wrap_socket(s,server_hostname='127.0.0.1'); raise AssertionError('TLS unexpectedly accepted')\n"
                "except ssl.SSLCertVerificationError as e:\n print(json.dumps(dict(verify_code=e.verify_code)))\n")
            verify_code=json.loads(self.call(['docker','exec',worker,'python','-c',script]))['verify_code']
            if verify_code not in {'wrong_ca':(19,20,21),'wrong_host':(62,64),'expired':(10,)}[kind]:
                raise ValueError('independent TLS verification did not confirm the intended reason')
        return dict(kind=kind,exit_code=int(code),reason_verified=True,container_id=cid,
                    replication_peer_absent=True,tls_verify_code=verify_code,client_verify_code=client_verify_code)

    def weak_peer(self,kind):
        self.stop()
        if kind=='plaintext':
            self.call(['docker','exec','--user','0:0',self.database,'sh','-ec',
                'cp "$PGDATA/pg_hba.conf" /tmp/wal-security-hba.strict; '
                'printf "hostnossl replication ems_wal_archive 127.0.0.1/32 trust\\n" > /tmp/wal-security-hba.weak; '
                'cat /tmp/wal-security-hba.strict >> /tmp/wal-security-hba.weak; '
                'cat /tmp/wal-security-hba.weak > "$PGDATA/pg_hba.conf"'])
            self.call(['docker','exec',self.database,'psql','-U','postgres','-d','ems','-c','SELECT pg_reload_conf()'])
            self.hba_weakened=True;connection='host=127.0.0.1 user=ems_wal_archive sslmode=disable'
        else:connection=self.connection(user='postgres')
        cid=self.create('unsafe-peer-'+kind,self.image,self.network+self.client_mount()+['--user',self.uid,
            '--tmpfs','/probe:rw,size=32m,uid='+self.uid.split(':')[0]+',gid='+self.uid.split(':')[1]+',mode=0700'],
            ['pg_receivewal','-d',connection+' application_name=ems_archive','-D','/probe','--synchronous','--no-loop','-S','ems_archive_slot'])
        self.unsafe_peer=cid
        deadline=time.monotonic()+8
        while time.monotonic()<deadline:
            value=self.sql(self.database,"SELECT json_build_object('ssl',s.ssl,'client_dn',s.client_dn,'username',r.usename,'guard',edge_ingest.sync_wal_flushed('ems_archive',NULL)) FROM pg_stat_replication r JOIN pg_stat_ssl s ON s.pid=r.pid WHERE r.application_name='ems_archive' AND r.state='streaming'")
            if value:
                observed=json.loads(value)
                if observed['guard'] is not False:raise ValueError('unsafe but connected replication peer passed the ACK gate')
                if kind=='plaintext' and observed['ssl'] is not False:raise ValueError('plaintext fault did not occur')
                if kind=='wrong_role' and (observed['ssl'] is not True or observed['username']!='postgres'):
                    raise ValueError('authorized wrong-role TLS peer did not occur')
                return dict(peer_connected=True,gate_rejected=True,observed=observed)
            time.sleep(.05)
        raise TimeoutError('unsafe replication peer did not actually connect')

    def resume(self):
        if getattr(self,'unsafe_peer',None):
            self.call(['docker','stop','--time','2',self.unsafe_peer]);self.unsafe_peer=None
        if getattr(self,'hba_weakened',False):
            self.call(['docker','exec','--user','0:0',self.database,'sh','-ec','cat /tmp/wal-security-hba.strict > "$PGDATA/pg_hba.conf"; rm /tmp/wal-security-hba.strict /tmp/wal-security-hba.weak'])
            self.call(['docker','exec',self.database,'psql','-U','postgres','-d','ems','-c','SELECT pg_reload_conf()'])
            self.hba_weakened=False
        self.certificate('server');self.launch();self.wait_sync(self.database)
        return dict(synchronous=True,slot=self.status())

    def status(self):
        text=self.sql(self.database,"SELECT json_build_object('slot','ems_archive_slot','restart_lsn',restart_lsn::text,'lag_bytes',pg_wal_lsn_diff(pg_current_wal_lsn(),restart_lsn),'slot_retained_bytes',pg_wal_lsn_diff(pg_current_wal_lsn(),restart_lsn),'active',active,'peer_tls',(SELECT ssl FROM pg_stat_ssl WHERE pid=active_pid),'peer_role',(SELECT usename FROM pg_stat_replication WHERE pid=active_pid),'peer_client_dn',(SELECT client_dn FROM pg_stat_ssl WHERE pid=active_pid),'flush_lsn',(SELECT flush_lsn::text FROM pg_stat_replication WHERE pid=active_pid)) FROM pg_replication_slots WHERE slot_name='ems_archive_slot'")
        return json.loads(text)

    def full(self):
        before=self.status()
        filled=subprocess.run(['docker','exec',self.wal,'sh','-c',
            'dd if=/dev/zero of=/wal/.quota-fill bs=1048576 count=128 2>/tmp/fill.log; result=$?; sync; cat /tmp/fill.log; exit "$result"'],text=True,capture_output=True,timeout=20)
        if filled.returncode==0 or 'No space left on device' not in filled.stdout+filled.stderr:
            raise ValueError('owned WAL tmpfs did not report actual ENOSPC')
        self.sql(self.database,'SELECT pg_switch_wal()')
        # A switch alone can leave the receiver waiting at the next boundary
        # without opening another file. Emit real next-segment WAL and flush it.
        self.sql(self.database,"SELECT pg_logical_emit_message(false,'ems_qa',repeat('x',1048576))")
        self.sql(self.database,'SELECT pg_switch_wal()')
        deadline=time.monotonic()+8
        while time.monotonic()<deadline and not self.stopped():time.sleep(.03)
        if not self.stopped():raise ValueError('WAL process survived without reaching full segment allocation')
        log=self.call(['docker','exec',self.wal,'cat','/tmp/wal.log'])
        code=self.call(['docker','exec',self.wal,'cat','/tmp/wal.exit'])
        if code=='0' or 'No space left on device' not in log:raise ValueError('WAL ENOSPC failure not independently observed')
        after=self.status()
        if after['lag_bytes']<=before['lag_bytes'] or after['active']:raise ValueError('physical slot backlog not retained')
        self.publish(self.output/'wal-enospc.log',log)
        return dict(actual_enospc=True,archive_limit_bytes=128*1024*1024,child_exit=int(code),before=before,after=after,container_kept_running=True)

    def export_archive(self):
        # Stop only the child: stopping the container would discard its tmpfs.
        self.stop()
        # docker cp in this daemon did not expose the live tmpfs. Stream from
        # the process mount namespace instead; never extract tar paths on host.
        with tempfile.TemporaryFile(dir=self.private) as stream:
            done=subprocess.run(['docker','exec',self.wal,'tar','cf','-','-C','/wal','.'],stdout=stream,stderr=subprocess.PIPE,timeout=20)
            if done.returncode or stream.tell()>129*1024*1024:raise ValueError('bounded live archive export failed')
            stream.seek(0);count=0
            with tarfile.open(fileobj=stream,mode='r:') as archive:
                for member in archive:
                    if member.isdir() and member.name in ('.','./'):continue
                    name=member.name.removeprefix('./');count+=1
                    if (count>64 or not member.isfile() or not re.fullmatch(r'[0-9A-F]{24}(?:\.partial)?|[0-9A-F]{8}\.history',name)
                            or not 0<=member.size<=16*1024*1024):raise ValueError('unsafe live archive entry')
                    content=archive.extractfile(member).read(16*1024*1024+1)
                    if len(content)!=member.size:raise ValueError('truncated live WAL export')
                    self.publish(self.archive/name,content)
            if count==0:raise ValueError('live WAL export was empty')
        self.launch();self.wait_sync(self.database)

    def prepare_copy(self,name,base):
        inspect_archive(base/'base.tar');inspect_archive(base/'pg_wal.tar')
        folder=self.private/name;folder.mkdir(mode=0o700)
        cid=self.create('prepare-'+name,self.image,['--network','none','--user',self.uid,
            '-v',str(folder)+':/restore','-v',str(base)+':/backup:ro'],['sleep','1800'])
        self.call(['docker','exec',cid,'sh','-ec',
            'tar xf /backup/base.tar -C /restore; tar xf /backup/pg_wal.tar -C /restore/pg_wal; '
            'cp /backup/backup_manifest /restore/backup_manifest; chmod 700 /restore'])
        return folder,cid

    def guard(self,folder,cid,expected):
        results=[]
        def runner(args,**kwargs):
            if args[0] not in ('pg_controldata','pg_verifybackup') or args[1]!=str(folder):raise ValueError('unexpected preflight command')
            done=subprocess.run(['docker','exec','-e','LC_ALL=C',cid,args[0],'/restore'],text=True,capture_output=True,timeout=60)
            results.append(done);return done
        try:return verify_backup(folder,expected,runner=runner),results
        except ValueError as exc:return dict(verified=False,error=str(exc)),results

    def recover_variant(self,name,folder,archive,port):
        settings=("\nsynchronous_standby_names=''\nport="+str(port)+"\n"
            "restore_command='cp /archive/%f %p 2>/dev/null || cp /archive/%f.partial %p'\n"
            "recovery_target_name='ems_ack_boundary'\nrecovery_target_action='promote'\n")
        with (folder/'postgresql.auto.conf').open('a') as config:config.write(settings)
        (folder/'recovery.signal').touch()
        cid=self.create(name+'-database',self.image,self.network+['--user',self.uid,'-e','PGDATA=/restore',
            '-e','TIMESCALEDB_TELEMETRY=off','-v',str(folder)+':/restore','-v',str(archive)+':/archive:ro',
            '-v',str(self.private/'pg-server')+':/run/pg-tls:ro'],
            ['postgres','-c','shared_buffers=32MB','-c','max_connections=20','-c','unix_socket_directories=/tmp'])
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            state=json.loads(self.call(['docker','inspect',cid,'--format','{{json .State}}']))
            if not state['Running']:
                done=subprocess.run(['docker','logs',cid],text=True,capture_output=True,timeout=5)
                return dict(promoted=False,container_id=cid,log=done.stdout+done.stderr)
            ready=subprocess.run(['docker','exec',cid,'psql','-h','/tmp','-p',str(port),'-U','postgres','-d','ems',
                '-At','-c','SELECT NOT pg_is_in_recovery()'],text=True,capture_output=True,timeout=3)
            if ready.returncode==0 and ready.stdout.strip()=='t':return dict(promoted=True,container_id=cid,port=port)
            time.sleep(.06)
        raise TimeoutError('owned recovery did not reach an explicit terminal state')

    def foreign_backup(self):
        cid=self.create('foreign-primary',self.image,self.network+['-e','POSTGRES_HOST_AUTH_METHOD=trust','-e','POSTGRES_DB=ems',
            '-e','PGDATA=/var/lib/postgresql/data/pgdata','--tmpfs','/var/lib/postgresql/data:rw,size=192m'],
            ['postgres','-c','port=5435','-c','shared_buffers=16MB','-c','max_connections=12'])
        psql=['docker','exec',cid,'psql','-p','5435','-U','postgres','-d','ems','-At','-v','ON_ERROR_STOP=1','-c']
        deadline=time.monotonic()+25
        while time.monotonic()<deadline:
            result=subprocess.run(psql+['SELECT system_identifier FROM pg_control_system()'],text=True,capture_output=True,timeout=3)
            if result.returncode==0:break
            time.sleep(.1)
        else:raise TimeoutError('owned foreign primary startup')
        foreign_id=result.stdout.strip()
        for _ in range(3):self.call(psql+['SELECT pg_switch_wal()'])
        self.call(psql+["SELECT pg_logical_emit_message(false,'ems_qa','foreign'); SELECT pg_create_restore_point('ems_ack_boundary')"])
        folder=self.private/'foreign-base';folder.mkdir(mode=0o700)
        # Local socket within this owned container is a distinct fixture, not a
        # source of primary recovery data. Copy only this foreign backup/WAL.
        self.call(['docker','exec',cid,'pg_basebackup','-p','5435','-U','postgres','-D','/tmp/foreign-base','-Ft','-Xstream','--checkpoint=fast','--manifest-checksums=SHA256'])
        with tempfile.TemporaryDirectory(prefix='foreign-copy-',dir=self.private) as temp:
            self.call(['docker','cp',cid+':/tmp/foreign-base/.',temp])
            for name in ('base.tar','pg_wal.tar','backup_manifest'):self.publish(folder/name,self.read_bytes(Path(temp)/name,128*1024*1024))
        return foreign_id,folder,cid

    def recovery_matrix(self):
        external_id=self.sql(self.database,'SELECT system_identifier FROM pg_control_system()')
        super().control(dict(request_id='matrix',op='wal_basebackup'))
        # A marker row after backup is acknowledged by the worker before the
        # separate matrix call's point? Worker uses a prior receipt; a fresh
        # fixed marker table makes actual postbackup WAL replay unambiguous.
        self.sql(self.database,'CREATE TABLE public.qa_pitr_marker(value text PRIMARY KEY); INSERT INTO public.qa_pitr_marker VALUES (\'after-basebackup\')')
        target=self.sql(self.database,"SELECT pg_create_restore_point('ems_ack_boundary')::text");self.wait_sync(self.database,target=target)
        self.export_archive()
        pristine={**self.snapshot('base',publish=True),**self.snapshot('wal',publish=True)}
        folder,prep=self.prepare_copy('good-restore',self.private/'base')
        accepted,results=self.guard(folder,prep,external_id)
        if not accepted.get('verified'):raise ValueError('valid source backup rejected')
        good=self.recover_variant('good-restore',folder,self.archive,5433)
        if not good['promoted']:raise ValueError('good backup/WAL failed recovery')
        marker=self.call(['docker','exec',good['container_id'],'psql','-h','/tmp','-p','5433','-U','postgres','-d','ems','-At','-c','SELECT value FROM qa_pitr_marker'])
        if marker!='after-basebackup':raise ValueError('positive recovery did not replay postbackup WAL')
        corrupt,prep=self.prepare_copy('bad-backup',self.private/'base')
        self.call(['docker','exec',prep,'sh','-ec',"printf '99\\n' > /restore/PG_VERSION"])
        rejected,checks=self.guard(corrupt,prep,external_id)
        if rejected.get('verified') or len(checks)!=2 or 'checksum mismatch' not in checks[-1].stderr:
            raise ValueError('corrupt basebackup not rejected by checksum')
        high,low=(int(p,16) for p in target.split('/'));absolute=(high<<32)+low
        segment=f'{1:08X}{absolute//(1<<32):08X}{(absolute%(1<<32))//(16*1024*1024):08X}'
        source=self.archive/(segment if (self.archive/segment).exists() else segment+'.partial')
        corrupt_wal=self.private/'corrupt-wal';shutil.copytree(self.archive,corrupt_wal)
        data=bytearray(self.read_bytes(source,16*1024*1024));offset=absolute%(16*1024*1024)-8
        if offset<24:raise ValueError('restore point unsuitable for precise CRC corruption')
        data[offset]^=0x40;self.publish(corrupt_wal/source.name,bytes(data))
        folder,prep=self.prepare_copy('bad-wal',self.private/'base');accepted,_=self.guard(folder,prep,external_id)
        if not accepted.get('verified'):raise ValueError('basebackup was not independently valid before corrupt later WAL')
        bad=self.recover_variant('bad-wal',folder,corrupt_wal,5434)
        if bad['promoted'] or not any(s in bad.get('log','') for s in ('incorrect resource manager data checksum','invalid record','invalid resource manager')):
            raise ValueError('corrupt later WAL did not fail CRC/target recovery')
        self.publish(self.output/'corrupt-wal-recovery.log',bad['log'])
        foreign_id,foreign_base,foreign=self.foreign_backup()
        if foreign_id==external_id:raise ValueError('foreign cluster is not independent')
        folder,prep=self.prepare_copy('foreign-bundle',foreign_base)
        rejected,checks=self.guard(folder,prep,external_id)
        valid_foreign=self.call(['docker','exec',prep,'pg_verifybackup','/restore'])
        if rejected.get('verified') or len(checks)!=1:raise ValueError('valid foreign bundle passed expected-cluster gate')
        foreign_wal=self.private/'foreign-wal-archive';shutil.copytree(self.archive,foreign_wal)
        # Move foreign primary to the exact required segment number, then emit
        # a real WAL record so its system identifier is present in the header.
        psql=['docker','exec',foreign,'psql','-p','5435','-U','postgres','-d','ems','-At','-c']
        for _ in range(20):
            file=self.call(psql+['SELECT pg_walfile_name(pg_current_wal_lsn())'])
            if int(file[8:],16)>=int(segment[8:],16):break
            self.call(psql+['SELECT pg_switch_wal()'])
        self.call(psql+["SELECT pg_logical_emit_message(false,'ems_qa','foreign-segment')"])
        with tempfile.TemporaryFile(dir=self.private) as stream:
            done=subprocess.run(['docker','exec',foreign,'cat','/var/lib/postgresql/data/pgdata/pg_wal/'+segment],stdout=stream,stderr=subprocess.PIPE,timeout=10)
            if done.returncode or stream.tell()!=16*1024*1024:raise ValueError('foreign live WAL copy failed')
            stream.seek(0);self.publish(foreign_wal/source.name,stream.read(16*1024*1024+1))
        folder,prep=self.prepare_copy('foreign-wal',self.private/'base');accepted,_=self.guard(folder,prep,external_id)
        if not accepted.get('verified'):raise ValueError('good source base rejected before foreign WAL test')
        wrong=self.recover_variant('foreign-wal',folder,foreign_wal,5436)
        if wrong['promoted'] or 'different database system' not in wrong.get('log',''):
            raise ValueError('foreign WAL did not fail system identity')
        self.publish(self.output/'foreign-wal-recovery.log',wrong['log'])
        # Compare immutable exported input hashes after mutating only copies.
        after={**self.snapshot('base',publish=True),**self.snapshot('wal',publish=True)}
        if pristine!=after:raise ValueError('negative recovery probes modified pristine source inputs')
        return dict(expected_system_id=external_id,foreign_system_id=foreign_id,good_promoted=True,
            postbackup_marker_recovered=True,corrupt_backup_checksum_rejected=True,corrupt_later_wal_crc_rejected=True,
            foreign_wal_system_id_rejected=True,valid_foreign_bundle_rejected_before_start=True,
            foreign_bundle_checksum_valid=True,pristine_inputs_unchanged=True,backup_and_wal_artifacts=pristine)

    def control(self,request):
        op=request['op']
        if op.startswith('db_cert_'):
            self.certificate({'db_cert_good':'server','db_cert_wrong_host':'wrong-host','db_cert_expired':'expired'}[op]);data=dict(reloaded=True)
        elif op.startswith('wal_probe_'):data=self.probe(op.removeprefix('wal_probe_'))
        elif op=='wal_resume':data=self.resume()
        elif op.startswith('wal_gate_'):data=self.weak_peer(op.removeprefix('wal_gate_'))
        elif op=='db_client_probe_begin':
            self.client_probe_started=datetime.now(timezone.utc).isoformat();data=dict(started=True)
        elif op in ('db_client_probe_end','db_client_probe_end_expired'):
            if not getattr(self,'client_probe_started',None):raise ValueError('missing owned client probe marker')
            log=subprocess.run(['docker','logs','--since',self.client_probe_started,self.database],text=True,capture_output=True,timeout=5)
            if 'could not accept SSL connection: certificate verify failed' not in log.stdout+log.stderr:
                raise ValueError('server did not independently report client certificate rejection')
            expired=op.endswith('_expired')
            cert='expired-receiver.crt' if expired else 'rogue-receiver.crt'
            checked=subprocess.run(['openssl','verify','-CAfile',str(self.private/'ca.crt'),
                str(self.private/'pg-client'/cert)],text=True,capture_output=True,timeout=5)
            match=re.search(r'error ([0-9]+) at',checked.stdout+checked.stderr)
            expected=(10,) if expired else (19,20,21)
            if checked.returncode==0 or not match or int(match[1]) not in expected:raise ValueError('independent client certificate cause mismatch')
            data=dict(server_rejected_client_certificate=True,client_certificate_verify_code=int(match[1]))
        elif op=='wal_full':data=self.full()
        elif op=='wal_free':
            self.call(['docker','exec',self.wal,'rm','/wal/.quota-fill']);self.launch();self.wait_sync(self.database)
            data=dict(synchronous=True,same_slot=True,slot=self.status())
        elif op=='wal_status':data=self.status()
        elif op=='wal_caught_up':
            fence=self.sql(self.database,'SELECT pg_current_wal_flush_lsn()::text');self.wait_sync(self.database,target=fence)
            data=dict(fixed_lsn=fence,flush_fence_satisfied=True,slot=self.status())
        elif op=='recovery_matrix':data=self.recovery_matrix()
        else:raise ValueError('unknown owned WAL security operation')
        return dict(passed=True,**request,**data)
