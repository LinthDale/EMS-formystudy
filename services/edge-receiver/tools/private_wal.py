"""Fixed owned-resource PG15 WAL/PITR operations; no worker supplied paths/SQL."""
import hashlib
import json
import re
import subprocess
import time


class PrivateWal:
    def __init__(self, private, output, owned, call, create, network, image, uid, publish, read_bytes, tls=False):
        self.private,self.output,self.owned=private,output,owned
        self.call,self.create,self.network,self.image,self.uid,self.publish=call,create,network,image,uid,publish
        self.archive=private/'wal';self.archive.mkdir(mode=0o700)
        self.database=None;self.wal=None;self.recovered=None
        self.read_bytes=read_bytes
        self.tls=tls

    def client_mount(self):
        return ['-v',str(self.private/'pg-client')+':/pg-client:ro'] if self.tls else []

    def connection(self,port=5432,user='postgres'):
        value=f'host=127.0.0.1 port={port} user={user}'
        if self.tls:
            cert='archive' if user=='ems_wal_archive' else 'postgres'
            value+=f' sslmode=verify-full sslrootcert=/pg-client/ca.crt sslcert=/pg-client/{cert}.crt sslkey=/pg-client/{cert}.key'
        return value

    def snapshot(self, folder, publish=False):
        files={}
        paths=list((self.private/folder).iterdir())
        if len(paths)>64:raise ValueError('private backup file count exceeded')
        for p in paths:
            if folder=='base':
                if p.name not in ('base.tar','pg_wal.tar','backup_manifest'):raise ValueError('unexpected basebackup file')
                limit=128*1024*1024
            else:
                if not re.fullmatch(r'(?:[0-9A-F]{24}(?:\.partial)?|[0-9A-F]{8}\.history)',p.name):
                    raise ValueError('unexpected WAL archive file')
                limit=16*1024*1024
            payload=self.read_bytes(p,limit);name=folder+'-'+p.name if publish else p.name
            if publish:self.publish(self.output/name,payload)
            files[name]=dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest())
        return files

    def sql(self, cid, sql, port=5432):
        connection=(f'host=127.0.0.1 port={port} user=postgres dbname=ems sslmode=verify-full '
                    'sslrootcert=/run/pg-tls/ca.crt') if self.tls else f'host=127.0.0.1 port={port} user=postgres dbname=ems'
        return self.call(['docker','exec',cid,'psql','-d',connection,'-At','-v','ON_ERROR_STOP=1','-c',sql])

    def wait_sync(self, cid, port=5432, target=None):
        deadline=time.monotonic()+15
        query="SELECT edge_ingest.sync_wal_flushed('ems_archive',"+('NULL' if target is None else "'"+target+"'::pg_lsn")+")"
        while time.monotonic()<deadline:
            if self.sql(cid,query,port)=='t':return
            time.sleep(.05)
        raise TimeoutError('owned synchronous WAL unavailable')

    def start_wal(self, database, port=5432, suffix=''):
        self.sql(database,"SELECT pg_create_physical_replication_slot('ems_archive_slot',true)",port)
        cid=self.create('wal-receiver'+suffix,self.image,self.network+self.client_mount()+['--user',self.uid,
            '-v',str(self.archive)+':/wal'],['pg_receivewal','-d',
            self.connection(port,'ems_wal_archive' if self.tls else 'postgres')+' application_name=ems_archive',
            '-D','/wal','--synchronous','-s','1','-S','ems_archive_slot','--no-loop','--verbose'])
        self.sql(database,"ALTER SYSTEM SET synchronous_standby_names='FIRST 1 (ems_archive)'",port)
        self.sql(database,'SELECT pg_reload_conf()',port)
        self.wait_sync(database,port)
        return cid

    def provision(self, database):
        self.database=database;self.wal=self.start_wal(database)

    def wait_exit(self, cid):
        code=self.call(['docker','wait',cid],timeout=60)
        if code!='0':raise RuntimeError('owned WAL helper failed')

    def recover(self, missing=False):
        name='missing' if missing else 'recovered';port=5434 if missing else 5433
        folder=self.private/name;folder.mkdir(mode=0o700)
        archive=self.private/'empty-wal' if missing else self.archive
        if missing:archive.mkdir(mode=0o700)
        settings=("\nsynchronous_standby_names=''\nport="+str(port)+"\n"
            "restore_command='cp /archive/%f %p 2>/dev/null || cp /archive/%f.partial %p'\n"
            "recovery_target_name='ems_ack_boundary'\nrecovery_target_action='promote'\n")
        # Inputs are host generated, from our basebackup client; never extract worker input on host.
        (self.private/(name+'.conf')).write_text(settings)
        prep=self.create('prepare-'+name,self.image,['--network','none','--user',self.uid,
            '-v',str(folder)+':/restore','-v',str(self.private/'base')+':/backup:ro',
            '-v',str(self.private/(name+'.conf'))+':/settings:ro'],['sh','-ec',
            'tar xf /backup/base.tar -C /restore; tar xf /backup/pg_wal.tar -C /restore/pg_wal; '
            'cp /backup/backup_manifest /restore/backup_manifest; pg_verifybackup /restore; '
            'cat /settings >> /restore/postgresql.auto.conf; touch /restore/recovery.signal; '
            'chmod 700 /restore'])
        self.wait_exit(prep)
        tls_mount=['-v',str(self.private/'pg-server')+':/run/pg-tls:ro'] if self.tls else []
        cid=self.create(name+'-database',self.image,self.network+tls_mount+['--user',self.uid,
            '-e','PGDATA=/restore','-e','TIMESCALEDB_TELEMETRY=off',
            '-v',str(folder)+':/restore','-v',str(archive)+':/archive:ro'],
            ['postgres','-c','shared_buffers=32MB','-c','max_connections=20','-c','unix_socket_directories=/tmp'])
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            state=json.loads(self.call(['docker','inspect',cid,'--format','{{json .State}}']))
            if not state['Running']:
                if missing:
                    result=subprocess.run(['docker','logs',cid],text=True,capture_output=True,timeout=10)
                    text=result.stdout+result.stderr
                    if 'recovery ended before configured recovery target was reached' not in text:
                        raise ValueError('missing WAL did not fail at the required recovery target')
                    return dict(container_id=cid,target_not_reached=True,promoted=False)
                raise RuntimeError('owned recovery database stopped')
            result=subprocess.run(['docker','exec',cid,'psql','-h','127.0.0.1','-p',str(port),
                '-U','postgres','-d','ems','-At','-c','SELECT NOT pg_is_in_recovery()'],text=True,capture_output=True,timeout=3)
            if result.returncode==0 and result.stdout.strip()=='t':
                if missing:raise ValueError('missing WAL silently promoted')
                self.recovered=cid
                # basebackup copied the old physical slot? Physical slots are not restored.
                self.start_wal(cid,port,'-recovered')
                return dict(container_id=cid,target_reached=True,promoted=True,port=port,backup_verified=True)
            time.sleep(.1)
        raise TimeoutError('owned PITR did not reach a terminal state')

    def control(self, request):
        op=request['op']
        if op=='wal_stop':
            self.call(['docker','stop','--time','2',self.wal]);data=dict(running=False,container_id=self.wal)
        elif op=='wal_start':
            self.call(['docker','start',self.wal]);self.wait_sync(self.database)
            data=dict(running=True,container_id=self.wal)
        elif op=='wal_basebackup':
            folder=self.private/'base';folder.mkdir(mode=0o700)
            cid=self.create('basebackup-client',self.image,self.network+self.client_mount()+['--user',self.uid,
                '-v',str(folder)+':/backup'],['pg_basebackup','-d',self.connection(),
                '-D','/backup','-Ft','-Xstream','--checkpoint=fast','--manifest-checksums=SHA256'])
            self.wait_exit(cid)
            files=self.snapshot('base')
            data=dict(files=files,format='physical-basebackup-tar')
        elif op=='wal_restorepoint':
            target=self.sql(self.database,"SELECT pg_create_restore_point('ems_ack_boundary')::text")
            self.wait_sync(self.database,target=target)
            data=dict(restore_point='ems_ack_boundary',target_lsn=target,independent_flush_verified=True)
        elif op=='wal_primary_loss':
            self.call(['docker','kill','--signal','KILL',self.database])
            state=json.loads(self.call(['docker','inspect',self.database,'--format','{{json .State}}']))
            if state['Running']:raise ValueError('original primary is still running')
            # Capture only independent archive/base; never copy primary PGDATA/pg_wal.
            self.call(['docker','stop','--time','2',self.wal])
            files={}
            for folder in ('base','wal'):
                files.update(self.snapshot(folder,publish=True))
            data=dict(original_primary_stopped=True,container_id=self.database,artifacts=files,
                      original_pgdata_used_for_recovery=False)
        elif op=='wal_recover':data=self.recover()
        elif op=='wal_missing':data=self.recover(missing=True)
        else:raise ValueError('unknown fixed WAL operation')
        return dict(passed=True,**request,**data)
