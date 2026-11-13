"""Three bounded owned-only failure drills; no operator-selected control input."""
import json
import re
import shutil
import subprocess
import time

from private_wal import PrivateWal
from private_wal_security import PrivateWalSecurity
from edge_receiver.backup_preflight import recovery_settings

OPERATIONS=frozenset(('db_data_full','db_data_free','db_data_clean','slot_lose','slot_reseed','timeline_matrix'))


class PrivateCritical(PrivateWalSecurity):
    slot_name='ems_archive_slot'

    def launch(self):
        self.call(['docker','exec',self.wal,'rm','-f','/tmp/wal.exit'])
        self.call(['docker','exec','-d',self.wal,'sh','-c',
            'pg_receivewal -d "$1" -D /wal --synchronous -s 1 -S "$2" --no-loop --verbose >>/tmp/wal.log 2>&1; '
            'code=$?; printf "%s" "$code" >/tmp/wal.exit','wal-job',
            self.connection(user='ems_wal_archive')+' application_name=ems_archive',self.slot_name])

    def status(self):
        if self.slot_name not in ('ems_archive_slot','ems_archive_reseed'):raise ValueError('unknown owned slot')
        query=("SELECT json_build_object('slot',slot_name,'active',active,'restart_lsn',restart_lsn::text,"
            "'wal_status',wal_status,'peer_tls',(SELECT ssl FROM pg_stat_ssl WHERE pid=active_pid),"
            "'flush_lsn',(SELECT flush_lsn::text FROM pg_stat_replication WHERE pid=active_pid)) "
            "FROM pg_replication_slots WHERE slot_name='"+self.slot_name+"'")
        return json.loads(self.sql(self.database,query))

    def data_full(self):
        self.call(['docker','exec','--user','0:0',self.database,'chown','postgres:postgres','/qa-db-quota'])
        self.sql(self.database,"CREATE TABLESPACE qa_full LOCATION '/qa-db-quota'")
        self.sql(self.database,'ALTER TABLE edge_ingest.receipts SET TABLESPACE qa_full')
        relation=self.sql(self.database,"SELECT pg_relation_filepath('edge_ingest.receipts')")
        if not relation.startswith('pg_tblspc/'):raise ValueError('receipt relation is not on bounded quota')
        fill=subprocess.run(['docker','exec','--user','postgres',self.database,'sh','-c',
            'dd if=/dev/zero of=/qa-db-quota/.qa-fill bs=1048576 count=16 2>&1'],text=True,capture_output=True,timeout=15)
        if fill.returncode==0 or 'No space left on device' not in fill.stdout+fill.stderr:
            raise ValueError('owned receipt tablespace did not actually fill')
        self.publish(self.output/'db-data-fill.log',fill.stdout+fill.stderr)
        return dict(actual_enospc=True,limit_bytes=16*1024*1024,receipt_relation=relation)

    def data_free(self):
        captured=subprocess.run(['docker','logs',self.database],text=True,capture_output=True,timeout=10)
        if captured.returncode:raise ValueError('owned PostgreSQL logs unavailable')
        log=captured.stdout+captured.stderr
        if 'could not extend file' not in log or 'No space left on device' not in log:
            raise ValueError('real PostgreSQL relation extension failure was not observed')
        self.call(['docker','exec','--user','postgres',self.database,'rm','/qa-db-quota/.qa-fill'])
        self.publish(self.output/'db-data-enospc.log',log)
        return dict(actual_relation_enospc=True,space_freed=True)

    def lose_slot(self):
        self.sql(self.database,'CREATE TABLE public.qa_branch_marker(value text PRIMARY KEY)')
        before=self.status();self.stop()
        for sql in ("ALTER SYSTEM SET max_slot_wal_keep_size='1MB'","ALTER SYSTEM SET min_wal_size='32MB'",
                    "ALTER SYSTEM SET max_wal_size='64MB'",'SELECT pg_reload_conf()'):
            self.sql(self.database,sql)
        lost=None
        for _ in range(10):
            self.sql(self.database,"SELECT pg_logical_emit_message(false,'ems_qa',repeat('s',32768)); SELECT pg_switch_wal()")
            self.sql(self.database,'CHECKPOINT')
            lost=self.status()
            if lost['wal_status']=='lost':break
        if lost['wal_status']!='lost' or lost['restart_lsn'] is not None:
            raise ValueError('slot did not really lose required WAL')
        self.launch()
        deadline=time.monotonic()+6
        while not self.stopped() and time.monotonic()<deadline:time.sleep(.05)
        if not self.stopped():raise ValueError('invalid slot unexpectedly streamed')
        log=self.call(['docker','exec',self.wal,'cat','/tmp/wal.log'])
        code=self.call(['docker','exec',self.wal,'cat','/tmp/wal.exit'])
        if code=='0' or not any(s in log for s in ('invalidated','can no longer get changes','already been removed')):
            raise ValueError('slot failure was not caused by missing WAL')
        if self.sql(self.database,"SELECT edge_ingest.sync_tls_wal_flushed('ems_archive',NULL)")!='f':
            raise ValueError('lost slot still authorized ACK')
        self.publish(self.output/'lost-slot.log',log)
        return dict(before=before,lost=lost,child_exit=int(code),gate_rejected=True)

    def reseed(self):
        old_slot=self.status()
        if old_slot['wal_status']!='lost':raise ValueError('no lost slot to reseed')
        # Reserve the replacement slot BEFORE backup. ACK fencing alone does
        # not prevent other sessions generating/recycling WAL during backup.
        self.sql(self.database,"ALTER SYSTEM SET max_slot_wal_keep_size='-1'")
        self.sql(self.database,'SELECT pg_reload_conf()')
        self.sql(self.database,"SELECT pg_create_physical_replication_slot('ems_archive_reseed',true)")
        reserved=self.sql(self.database,"SELECT restart_lsn::text FROM pg_replication_slots WHERE slot_name='ems_archive_reseed'")
        if not reserved:raise ValueError('new slot did not reserve WAL before backup')
        PrivateWal.control(self,dict(request_id='reseed',op='wal_basebackup'))
        # A real committed gap marker and three checkpointed segment changes
        # exercise the interval BEFORE archive pickup; PG15 receivewal queries
        # the reserved slot restart_lsn when its destination is empty.
        self.sql(self.database,"SET synchronous_commit=local; INSERT INTO qa_branch_marker VALUES ('reseed-gap')")
        for _ in range(3):
            self.sql(self.database,"SELECT pg_logical_emit_message(false,'ems_qa','reseed-gap'); SELECT pg_switch_wal()")
            self.sql(self.database,'CHECKPOINT')
        expected=self.sql(self.database,'SELECT system_identifier FROM pg_control_system()')
        folder,prep=self.prepare_copy('reseed-verify',self.private/'base')
        verified,_=self.guard(folder,prep,expected)
        if not verified.get('verified'):raise ValueError('replacement basebackup did not verify')
        self.slot_name='ems_archive_reseed'
        self.wal=self.create('wal-receiver-reseed',self.image,self.network+self.client_mount()+['--user',self.uid,
            '--tmpfs','/wal:rw,size=128m,uid='+self.uid.split(':')[0]+',gid='+self.uid.split(':')[1]+',mode=0700'],['sleep','1800'])
        self.launch();self.wait_sync(self.database)
        fence=self.sql(self.database,'SELECT pg_current_wal_flush_lsn()::text');self.wait_sync(self.database,target=fence)
        point=self.sql(self.database,"SELECT pg_create_restore_point('ems_reseed_boundary')::text");self.wait_sync(self.database,target=point)
        self.export_archive()
        recovered,_=self.recover_pinned('reseed-chain-pitr',self.archive,5437,1,'ems_reseed_boundary')
        marker=self.sql(recovered,"SELECT value FROM qa_branch_marker WHERE value='reseed-gap'",5437)
        if marker!='reseed-gap':raise ValueError('new base/archive chain lost the backup-to-pickup marker')
        return dict(base_verified=True,expected_system_id=expected,old_slot_preserved=old_slot['slot'],
            replacement_slot=self.status(),fixed_lsn=fence,flush_fence_satisfied=True,
            reserved_before_backup=reserved,forced_gap_segments=3,reseed_chain_pitr_verified=True,recovered_gap_marker=marker,
            base_artifacts=self.snapshot('base',publish=True))

    def recover_pinned(self,name,archive,port,timeline,target,unsafe=False):
        folder,prep=self.prepare_copy(name,self.private/'base')
        expected=self.sql(self.database,'SELECT system_identifier FROM pg_control_system()')
        accepted,_=self.guard(folder,prep,expected)
        if not accepted.get('verified'):raise ValueError('basebackup identity/checksum verification failed')
        settings=(dict(recovery_target_timeline='latest',recovery_target_name=target,recovery_target_action='promote')
                  if unsafe else recovery_settings(str(timeline),target))
        # These strings are host-selected constants or validated production
        # settings, never data from worker/control or an untrusted archive.
        text="\nsynchronous_standby_names=''\nport="+str(port)+"\nrestore_command='cp /archive/%f %p 2>/dev/null || cp /archive/%f.partial %p'\n"
        text+=''.join(k+"='"+v+"'\n" for k,v in settings.items())
        with (folder/'postgresql.auto.conf').open('a') as stream:stream.write(text)
        (folder/'recovery.signal').touch()
        cid=self.create(name+'-database',self.image,self.network+['--user',self.uid,'-e','PGDATA=/restore',
            '-e','TIMESCALEDB_TELEMETRY=off','-v',str(folder)+':/restore','-v',str(archive)+':/archive:ro',
            '-v',str(self.private/'pg-server')+':/run/pg-tls:ro'],
            ['postgres','-c','shared_buffers=16MB','-c','max_connections=20','-c','unix_socket_directories=/tmp'])
        deadline=time.monotonic()+18
        while time.monotonic()<deadline:
            state=json.loads(self.call(['docker','inspect',cid,'--format','{{json .State}}']))
            if not state['Running']:raise ValueError('pinned recovery failed; see owned database log')
            result=subprocess.run(['docker','exec',cid,'psql','-h','/tmp','-p',str(port),'-U','postgres','-d','ems','-At',
                '-c','SELECT NOT pg_is_in_recovery()'],text=True,capture_output=True,timeout=3)
            if result.returncode==0 and result.stdout.strip()=='t':
                info=json.loads(self.sql(cid,"SELECT json_build_object('system_id',system_identifier::text,'timeline',timeline_id) FROM pg_control_system(),pg_control_checkpoint()",port))
                return cid,info
            time.sleep(.1)
        raise TimeoutError('pinned recovery did not promote')

    def archive_branch(self,cid,port,label):
        timeline=int(self.sql(cid,'SELECT timeline_id FROM pg_control_checkpoint()',port))
        if timeline not in (2,3):raise ValueError('unexpected owned branch timeline')
        folder=self.private/(label+'-archive');folder.mkdir(mode=0o700)
        self.sql(cid,"SELECT pg_create_physical_replication_slot('qa_branch',true)",port)
        job=self.create(label+'-wal',self.image,self.network+self.client_mount()+['--user',self.uid,'-v',str(folder)+':/wal'],
            ['pg_receivewal','-d',self.connection(port,'ems_wal_archive')+' application_name=ems_archive',
             '-D','/wal','--synchronous','-s','1','-S','qa_branch','--no-loop'])
        self.sql(cid,"ALTER SYSTEM SET synchronous_standby_names='FIRST 1 (ems_archive)'",port)
        self.sql(cid,'SELECT pg_reload_conf()',port);self.wait_sync(cid,port)
        self.sql(cid,"INSERT INTO qa_branch_marker VALUES ('"+label+"')",port)
        fence=self.sql(cid,"SELECT pg_create_restore_point('ems_branch_target')::text",port);self.wait_sync(cid,port,target=fence)
        self.call(['docker','stop','--time','2',job])
        history=self.call(['docker','exec',cid,'cat',f'/restore/pg_wal/{timeline:08X}.history'])+'\n'
        self.publish(folder/f'{timeline:08X}.history',history)
        self.call(['docker','stop','--time','2',cid])
        return folder,timeline

    def timeline_matrix(self):
        origin=self.sql(self.database,"SELECT pg_create_restore_point('ems_branch_origin')::text");self.wait_sync(self.database,target=origin)
        self.export_archive()
        inputs={**self.snapshot('base',publish=True),**self.snapshot('wal',publish=True)}
        mixed=self.private/'mixed-branches';shutil.copytree(self.archive,mixed)
        first,first_info=self.recover_pinned('branch-two',mixed,5433,1,'ems_branch_origin')
        branch2,two=self.archive_branch(first,5433,'branch-two')
        for path in branch2.iterdir():self.publish(mixed/path.name,self.read_bytes(path,16*1024*1024))
        second,second_info=self.recover_pinned('branch-three',mixed,5434,1,'ems_branch_origin')
        branch3,three=self.archive_branch(second,5434,'branch-three')
        for path in branch3.iterdir():self.publish(mixed/path.name,self.read_bytes(path,16*1024*1024))
        if (two,three)!=(2,3) or first_info['system_id']!=second_info['system_id']:
            raise ValueError('same-cluster distinct branch scenario was not established')
        pinned,pinned_info=self.recover_pinned('pinned-second-pitr',mixed,5435,2,'ems_branch_target')
        rows=self.sql(pinned,"SELECT value FROM qa_branch_marker WHERE value LIKE 'branch-%' ORDER BY value",5435)
        if rows!='branch-two':raise ValueError('pinned second PITR selected the wrong branch')
        # Explicitly unsafe diagnostic counterexample, never the production
        # path: same target name/system ID plus latest selects branch three.
        unsafe,unsafe_info=self.recover_pinned('unsafe-latest-counterexample',mixed,5436,1,'ems_branch_target',unsafe=True)
        wrong=self.sql(unsafe,"SELECT value FROM qa_branch_marker WHERE value LIKE 'branch-%' ORDER BY value",5436)
        if wrong!='branch-three':raise ValueError('latest counterexample did not select the other branch')
        try:recovery_settings('latest','ems_branch_target')
        except ValueError:latest_rejected=True
        else:latest_rejected=False
        if inputs!={**self.snapshot('base',publish=True),**self.snapshot('wal',publish=True)}:
            raise ValueError('branch probes altered pristine inputs')
        # Preserve WAL/history as immutable evidence; never include PG TLS keys.
        for path in mixed.iterdir():self.publish(self.output/('mixed-'+path.name),self.read_bytes(path,16*1024*1024))
        return dict(system_id=first_info['system_id'],branch_timelines=[two,three],target='ems_branch_target',
            approved_timeline=2,pinned_rows=rows,unsafe_latest_rows=wrong,latest_rejected=latest_rejected,
            second_pitr_promoted=True,backup_verified=True,pristine_inputs_unchanged=True,
            pinned_recovery=pinned_info,unsafe_recovery=unsafe_info)

    def control(self,request):
        op=request['op']
        if op=='db_data_full':data=self.data_full()
        elif op=='db_data_free':data=self.data_free()
        elif op=='db_data_clean':
            self.sql(self.database,'ALTER TABLE edge_ingest.receipts SET TABLESPACE pg_default')
            self.sql(self.database,'DROP TABLESPACE qa_full');data=dict(tablespace_removed=True)
        elif op=='slot_lose':data=self.lose_slot()
        elif op=='slot_reseed':data=self.reseed()
        elif op=='timeline_matrix':data=self.timeline_matrix()
        else:raise ValueError('unknown fixed critical operation')
        return dict(passed=True,**request,**data)
