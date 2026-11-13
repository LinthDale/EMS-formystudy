"""Owned PG15 TLS fixture; server private key stays outside PGDATA/basebackup."""
import shutil


def prepare(private,call):
    server=private/'pg-server';client=private/'pg-client'
    server.mkdir(mode=0o700);client.mkdir(mode=0o700)
    for name in ('server.crt','server.key','ca.crt','wrong-host.crt','wrong-host.key','expired.crt','expired.key'):
        shutil.copy2(private/name,server/name)
    shutil.copy2(private/'ca.crt',client/'ca.crt')
    shutil.copy2(private/'rogue-ca.crt',client/'rogue-ca.crt')
    for name,principal in (('postgres','postgres'),('receiver','qa_tls_receiver'),('archive','ems_wal_archive')):
        call(['openssl','req','-new','-newkey','rsa:2048','-nodes','-subj','/CN='+principal,
            '-keyout',str(client/(name+'.key')),'-out',str(client/(name+'.csr'))])
        call(['openssl','x509','-req','-in',str(client/(name+'.csr')),'-CA',str(private/'ca.crt'),
            '-CAkey',str(private/'ca.key'),'-CAcreateserial','-days','2','-sha256',
            '-extfile',str(private/'client.ext'),'-out',str(client/(name+'.crt'))])
        (client/(name+'.key')).chmod(0o600)
    # Wrong CA with the same expected CN distinguishes trust failure from names.
    call(['openssl','x509','-req','-in',str(client/'receiver.csr'),'-CA',str(private/'rogue-ca.crt'),
        '-CAkey',str(private/'rogue-ca.key'),'-CAcreateserial','-days','2','-sha256',
        '-extfile',str(private/'client.ext'),'-out',str(client/'rogue-receiver.crt')])
    (server/'server.key').chmod(0o600)
    ca_config=(private/'ca.conf').read_text()
    for key,name in (('database','index.txt'),('serial','serial'),('new_certs_dir','newcerts'),
                     ('certificate','ca.crt'),('private_key','ca.key')):
        ca_config=ca_config.replace(key+'='+name,key+'='+str(private/name))
    (private/'pg-expired-ca.conf').write_text(ca_config)
    for name in ('receiver','archive'):
        call(['openssl','ca','-batch','-notext','-config',str(private/'pg-expired-ca.conf'),
            '-in',str(client/(name+'.csr')),'-out',str(client/('expired-'+name+'.crt')),
            '-extfile',str(private/'client.ext'),'-startdate','20200101000000Z','-enddate','20200102000000Z'])


def provision(database,call):
    call(['docker','exec','--user','0:0',database,'sh','-ec',
        'cp /qa-pg/server.crt /qa-pg/server.key /qa-pg/ca.crt /run/pg-tls/; '
        'chown postgres:postgres /run/pg-tls/*; chmod 600 /run/pg-tls/server.key'])
    psql=['docker','exec','-i',database,'psql','-U','postgres','-d','ems','-v','ON_ERROR_STOP=1']
    for statement in ("ALTER SYSTEM SET shared_buffers='32MB'","ALTER SYSTEM SET max_connections='20'",
        "ALTER SYSTEM SET ssl_cert_file='/run/pg-tls/server.crt'",
        "ALTER SYSTEM SET ssl_key_file='/run/pg-tls/server.key'",
        "ALTER SYSTEM SET ssl_ca_file='/run/pg-tls/ca.crt'","ALTER SYSTEM SET ssl='on'"):
        call(psql,input_text=statement+';')
    call(psql,input_text='ALTER ROLE ems_wal_archive LOGIN; CREATE ROLE qa_tls_receiver LOGIN IN ROLE ems_edge_receiver; CREATE ROLE qa_tls_other LOGIN IN ROLE ems_edge_receiver;')
    # Only fixed private fixture roles/endpoints. Existing local QA admin stays
    # trusted; replication never falls back to the later initdb trust rule.
    rules=('hostnossl replication all 127.0.0.1/32 reject\n'
           'hostssl replication all 127.0.0.1/32 cert\n'
           'hostnossl all qa_tls_receiver,qa_tls_other 127.0.0.1/32 reject\n'
           'hostssl all qa_tls_receiver,qa_tls_other 127.0.0.1/32 cert\n')
    call(['docker','exec','-i','--user','0:0',database,'sh','-ec',
        'cat > /tmp/tls-hba; cat "$PGDATA/pg_hba.conf" >> /tmp/tls-hba; '
        'cat /tmp/tls-hba > "$PGDATA/pg_hba.conf"; rm /tmp/tls-hba'],input_text=rules)
    call(psql,input_text='SELECT pg_reload_conf();')
