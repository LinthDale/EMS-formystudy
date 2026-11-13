"""Dedicated v2 queue: immutable sample identity survives crash and resend."""
from contextlib import closing, contextmanager
import json
import logging
import os
from pathlib import Path
import sqlite3
import time
from uuid import uuid4

from .reliable_wire import FIELDS, canonical, decode, identifier, sample_hash, uuid_text, validate_sample

LOG = logging.getLogger(__name__)


def empty_retention():
    """A fixed-size summary, never an unbounded replacement audit ledger."""
    return dict(policy='drop_oldest', audit_evicted_total=0, unconfirmed_evicted_total=0,
                committed_audit_evicted_total=0, quarantine_evicted_total=0, last=None)


def read_retention(text):
    if len(text) > 4096:
        raise ValueError('invalid retention metadata')
    value = json.loads(text)
    expected = empty_retention()
    if not isinstance(value, dict) or value.keys() != expected.keys() or value['policy'] != 'drop_oldest':
        raise ValueError('invalid retention policy')
    for key in expected.keys() - {'policy', 'last'}:
        if type(value[key]) is not int or not 0 <= value[key] <= 2**63-1:
            raise ValueError('invalid retention counter')
    if (value['audit_evicted_total'] != value['unconfirmed_evicted_total'] + value['committed_audit_evicted_total']
            or value['quarantine_evicted_total'] > value['unconfirmed_evicted_total']
            or (value['last'] is not None and not isinstance(value['last'], dict))):
        raise ValueError('inconsistent retention summary')
    return value


class ReliableOutbox:
    def __init__(self, path, limit, gateway_id, device_id, stream_id, config_revision,
                 profile_version, byte_limit=4 * 1024**3, audit_limit=600000):
        self.path = Path(path)
        self.limit, self.byte_limit, self.audit_limit = limit, byte_limit, audit_limit
        if (type(limit) is not int or not 1 <= limit <= 1000000
                or type(byte_limit) is not int or not 65536 <= byte_limit <= 64 * 1024**3
                or type(audit_limit) is not int or not 1 <= audit_limit <= 6000000):
            raise ValueError('queue capacity')
        self.identity = dict(gateway_id=identifier(gateway_id), device_id=identifier(device_id),
                             stream_id=uuid_text(stream_id), config_revision=identifier(config_revision),
                             profile_version=identifier(profile_version))
        if self.path.is_symlink() or self.path.parent.is_symlink():
            raise ValueError('queue symlink')
        self.path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        self.path.parent.chmod(0o700)
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, 'O_NOFOLLOW', 0), 0o600)
            created = True
        except FileExistsError:
            fd = os.open(self.path, os.O_WRONLY | getattr(os, 'O_NOFOLLOW', 0))
            created = False
        os.close(fd)
        if not created:
            # Existing empty/truncated storage is evidence, not a fresh stream.
            # Inspect read-only before any mutating PRAGMA or schema creation.
            def inspect_existing(mode):
                with closing(sqlite3.connect(self.path.resolve().as_uri()+'?mode='+mode,uri=True)) as existing:
                    version = existing.execute('PRAGMA user_version').fetchone()[0]
                    tables = {row[0] for row in existing.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                    if version not in (2, 3) or not tables:
                        raise ValueError('existing queue is uninitialized or damaged')
            try:
                inspect_existing('ro')
            except sqlite3.OperationalError as exc:
                if getattr(exc,'sqlite_errorcode',None)!=sqlite3.SQLITE_READONLY_ROLLBACK:
                    raise
                # A genuine hot rollback journal needs SQLite's own RW recovery.
                # mode=rw cannot create a missing DB; never synthesize a schema.
                inspect_existing('rw')
        self.path.chmod(0o600)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            version_number = db.execute('PRAGMA user_version').fetchone()[0]
            if version_number not in (0, 2, 3):
                raise ValueError('queue schema version')
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if 'outbox' in tables:
                raise ValueError('legacy outbox requires offline migration')
            required_tables = {'metadata', 'windows', 'queue', 'audit'}
            if tables and tables != required_tables:
                raise ValueError('dedicated reliable queue required')
            if tables:
                columns = {
                    'metadata': {'key', 'value'},
                    'windows': {'bucket', 'window_id'},
                    'queue': {'sample_id', 'capture_seq', 'payload_hash', 'payload', 'state', 'snapshot'},
                    'audit': {'sample_id', 'payload_hash', 'capture_seq', 'window_id', 'sampled_at_us', 'state', 'acknowledged_us'},
                }
                for table, names in columns.items():
                    if {row[1] for row in db.execute('PRAGMA table_info(' + table + ')')} != names:
                        raise ValueError('incompatible reliable schema')
                metadata = dict(db.execute('SELECT key,value FROM metadata'))
                if not {'protocol', 'identity', 'sequence', 'latest_timestamp'} <= metadata.keys() or metadata['protocol'] != '2':
                    raise ValueError('incomplete reliable metadata')
                for name in ('sequence', 'latest_timestamp'):
                    if not metadata[name].isdigit() or not 0 <= int(metadata[name]) <= 2**63 - 1:
                        raise ValueError('invalid reliable metadata')
                if version_number not in (2, 3) or db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                    raise ValueError('reliable database integrity')
                if version_number == 3:
                    if 'retention' not in metadata:
                        raise ValueError('missing retention metadata')
                    read_retention(metadata['retention'])
                self._check_relations(db, metadata)
            db.execute('CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY,value TEXT NOT NULL)')
            version = db.execute("SELECT value FROM metadata WHERE key='protocol'").fetchone()
            if version and version[0] != '2':
                raise ValueError('queue schema mismatch')
            identity = canonical(self.identity).decode()
            old = db.execute("SELECT value FROM metadata WHERE key='identity'").fetchone()
            if old and old[0] != identity:
                raise ValueError('queue identity mismatch')
            db.executemany('INSERT OR IGNORE INTO metadata VALUES (?,?)',
                           [('protocol', '2'), ('identity', identity), ('sequence', '0'), ('latest_timestamp', '0')])
            db.execute('CREATE TABLE IF NOT EXISTS windows (bucket INTEGER PRIMARY KEY,window_id TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS queue (sample_id TEXT PRIMARY KEY, capture_seq INTEGER UNIQUE NOT NULL, '
                       'payload_hash TEXT NOT NULL, payload TEXT NOT NULL, state TEXT NOT NULL, snapshot TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS audit (sample_id TEXT PRIMARY KEY, payload_hash TEXT NOT NULL, '
                       'capture_seq INTEGER NOT NULL, window_id TEXT NOT NULL, sampled_at_us INTEGER NOT NULL, '
                       'state TEXT NOT NULL, acknowledged_us INTEGER)')
            db.execute('INSERT OR IGNORE INTO metadata VALUES (?,?)',
                       ('retention', json.dumps(empty_retention(), separators=(',', ':'))))
            db.execute('PRAGMA user_version=3')
        # These indexes accelerate retention but are not identity constraints.
        # A full legacy DB must remain usable without allocating index pages.
        try:
            with self.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                db.execute('CREATE INDEX IF NOT EXISTS audit_sequence ON audit(capture_seq)')
                db.execute('CREATE INDEX IF NOT EXISTS audit_window ON audit(window_id)')
                db.execute('CREATE INDEX IF NOT EXISTS audit_time ON audit(sampled_at_us)')
        except sqlite3.DatabaseError as exc:
            if getattr(exc, 'sqlite_errorcode', None) != sqlite3.SQLITE_FULL:
                raise
            LOG.warning('retention_indexes_deferred reason=sqlite_full')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        try:
            db.execute('PRAGMA journal_mode=DELETE')
            db.execute('PRAGMA synchronous=EXTRA')
            page_size = db.execute('PRAGMA page_size').fetchone()[0]
            max_pages = max(16, self.byte_limit // page_size)
            actual = db.execute('PRAGMA max_page_count=' + str(max_pages)).fetchone()[0]
            if (db.execute('PRAGMA journal_mode').fetchone()[0] != 'delete'
                    or db.execute('PRAGMA synchronous').fetchone()[0] != 3 or actual > max_pages):
                raise ValueError('unsafe queue persistence')
            with db:
                yield db
        finally:
            db.close()

    def enqueue(self, sampled_ns, snapshot):
        if type(sampled_ns) is not int or not 0 <= sampled_ns <= 2**63-1 or sampled_ns % 1000:
            raise ValueError('bounded microsecond aligned source time required')
        rich_snapshot = json.dumps(snapshot, allow_nan=False, separators=(',', ':'))
        if len(rich_snapshot.encode()) > 16384:
            raise ValueError('snapshot size')
        measurements = {key: snapshot[key] for key in FIELDS}
        for key, value in measurements.items():
            if type(value) not in (int, float) or not 0 <= value <= 1e15:
                raise ValueError('measurement type')
            measurements[key] = float(value) if value else 0.0
        # FULL may roll back the entire SQLite transaction. Retry a new complete
        # transaction, never commit the deletions separately from the new sample.
        retire_count = 0
        while True:
            available = None
            try:
                with self.connect() as db:
                    db.execute('BEGIN IMMEDIATE')
                    available = db.execute('SELECT COUNT(*) FROM audit').fetchone()[0]
                    metadata = dict(db.execute("SELECT key,value FROM metadata WHERE key IN ('sequence','latest_timestamp')"))
                    seq, high = self._check_high_water(db,metadata)
                    seq += 1
                    bucket = sampled_ns // 300000000000
                    window = db.execute('SELECT window_id FROM windows WHERE bucket=?', (bucket,)).fetchone()
                    window = window[0] if window else str(uuid4())
                    sample = dict(self.identity, sample_id=str(uuid4()), capture_seq=seq, window_id=window,
                                  sampled_at_us=sampled_ns // 1000, time_quality='trusted', measurements=measurements)
                    sample['payload_hash'] = sample_hash(sample)
                    sample = validate_sample(sample, self.identity['gateway_id'])
                    event = self._retire(db, available, retire_count)
                    db.execute('DELETE FROM windows WHERE NOT EXISTS (SELECT 1 FROM audit WHERE audit.window_id=windows.window_id)')
                    db.execute('INSERT OR IGNORE INTO windows VALUES (?,?)', (bucket, window))
                    db.execute('INSERT INTO queue VALUES (?,?,?,?,?,?)',
                               (sample['sample_id'], seq, sample['payload_hash'], canonical(sample).decode(), 'pending', rich_snapshot))
                    db.execute('INSERT INTO audit VALUES (?,?,?,?,?,?,NULL)',
                               (sample['sample_id'], sample['payload_hash'], seq, window, sampled_ns // 1000, 'pending'))
                    high = max(sampled_ns, high)
                    db.executemany('UPDATE metadata SET value=? WHERE key=?',
                                   [(str(seq), 'sequence'), (str(high), 'latest_timestamp')])
                break
            except sqlite3.DatabaseError as exc:
                if (getattr(exc, 'sqlite_errorcode', None) != sqlite3.SQLITE_FULL
                        or available is None or retire_count >= available):
                    raise
                retire_count = min(available, max(1, retire_count * 2))
        if event:
            LOG.warning('capacity_eviction audit_rows=%d unconfirmed_rows=%d first_seq=%d last_seq=%d',
                        event['count'], event['unconfirmed_count'], event['first_seq'], event['last_seq'])
        return sample

    def _retire(self, db, audit_count, byte_count):
        """Retire only an oldest prefix, atomically with its replacement."""
        cutoffs = []
        queue_count = db.execute('SELECT COUNT(*) FROM queue').fetchone()[0]
        for table, count, limit in (('queue', queue_count, self.limit), ('audit', audit_count, self.audit_limit)):
            if count >= limit:
                # table is a fixed local allowlist, never supplied by a caller.
                cutoffs.append(db.execute('SELECT capture_seq FROM '+table+' ORDER BY capture_seq LIMIT 1 OFFSET ?',
                                          (count-limit,)).fetchone()[0])
        if byte_count and audit_count:
            cutoffs.append(db.execute('SELECT capture_seq FROM audit ORDER BY capture_seq LIMIT 1 OFFSET ?',
                                      (min(byte_count,audit_count)-1,)).fetchone()[0])
        if not cutoffs:
            return None
        cutoff = max(cutoffs)
        count, unconfirmed, quarantine, first, last = db.execute(
            "SELECT COUNT(*),SUM(state!='committed'),SUM(state='quarantine'),MIN(capture_seq),MAX(capture_seq) FROM audit WHERE capture_seq<=?",
            (cutoff,)).fetchone()
        if not count:
            raise ValueError('queue missing audit identity')
        sample_id, payload_hash, state, sampled_us = db.execute(
            'SELECT sample_id,payload_hash,state,sampled_at_us FROM audit WHERE capture_seq<=? ORDER BY capture_seq DESC LIMIT 1',
            (cutoff,)).fetchone()
        event = dict(count=count,unconfirmed_count=unconfirmed,first_seq=first,last_seq=last,
                     sample_id=sample_id,payload_hash=payload_hash,state=state,sampled_at_us=sampled_us)
        status = read_retention(db.execute("SELECT value FROM metadata WHERE key='retention'").fetchone()[0])
        status['audit_evicted_total'] += count
        status['unconfirmed_evicted_total'] += unconfirmed
        status['committed_audit_evicted_total'] += count-unconfirmed
        status['quarantine_evicted_total'] += quarantine
        status['last'] = event
        serialized = json.dumps(status,separators=(',',':'))
        read_retention(serialized)  # Overflow must fail before retiring any source.
        db.execute('DELETE FROM queue WHERE capture_seq<=?',(cutoff,))
        db.execute('DELETE FROM audit WHERE capture_seq<=?',(cutoff,))
        db.execute("UPDATE metadata SET value=? WHERE key='retention'",(serialized,))
        return event

    def retention_status(self):
        """Local retirement counters; these never represent central delivery."""
        with self.connect() as db:
            return read_retention(db.execute("SELECT value FROM metadata WHERE key='retention'").fetchone()[0])

    @staticmethod
    def _check_high_water(db, metadata):
        values=[]
        for key in ('sequence','latest_timestamp'):
            value=metadata.get(key)
            if not isinstance(value,str) or not value.isdigit() or not 0<=int(value)<=2**63-1:
                raise ValueError('invalid reliable high-water metadata')
            values.append(int(value))
        # Separate MAX subqueries allow each optional index to be used. If a
        # full DB deferred indexes, the scan is slower but never skips safety.
        seq, sampled_us = db.execute('''SELECT (SELECT MAX(capture_seq) FROM audit),
            (SELECT MAX(sampled_at_us) FROM audit)''').fetchone()
        if ((seq is not None and (type(seq) is not int or seq>values[0]))
                or (sampled_us is not None and (type(sampled_us) is not int or sampled_us*1000>values[1]))):
            raise ValueError('reliable high-water rollback')
        return values

    @staticmethod
    def _check_relations(db, metadata):
        """One startup scan; quick_check alone cannot validate application state."""
        broken = db.execute('''SELECT 1 FROM queue q LEFT JOIN audit a ON a.sample_id=q.sample_id
            WHERE a.sample_id IS NULL OR q.capture_seq!=a.capture_seq OR q.payload_hash!=a.payload_hash
            OR q.state!=a.state OR q.state NOT IN ('pending','quarantine') LIMIT 1''').fetchone()
        orphan = db.execute('''SELECT 1 FROM audit a LEFT JOIN queue q ON q.sample_id=a.sample_id
            WHERE a.state NOT IN ('pending','quarantine','committed')
            OR (a.state='committed' AND (q.sample_id IS NOT NULL OR a.acknowledged_us IS NULL))
            OR (a.state!='committed' AND (q.sample_id IS NULL OR a.acknowledged_us IS NOT NULL))
            OR typeof(a.capture_seq)!='integer' OR a.capture_seq<=0
            OR typeof(a.sampled_at_us)!='integer' OR a.sampled_at_us<=0 LIMIT 1''').fetchone()
        duplicate = db.execute('SELECT 1 FROM audit GROUP BY capture_seq HAVING COUNT(*)>1 LIMIT 1').fetchone()
        if broken or orphan or duplicate:
            raise ValueError('reliable queue/audit mismatch')
        ReliableOutbox._check_high_water(db,metadata)

    def _validated_pending(self, db, row):
        """Check the selected immutable sample against its SQL identity and audit."""
        sample_id, seq, payload_hash, payload, state = row
        sample = validate_sample(decode(payload,1024),self.identity['gateway_id'])
        if (any(sample[k]!=v for k,v in self.identity.items())
                or (sample_id,seq,payload_hash)!=(sample['sample_id'],sample['capture_seq'],sample['payload_hash'])
                or state not in ('pending','quarantine')):
            raise ValueError('pending payload identity mismatch')
        audit = db.execute('''SELECT capture_seq,payload_hash,window_id,sampled_at_us,state,acknowledged_us
            FROM audit WHERE sample_id=?''',(sample_id,)).fetchone()
        expected = (seq,payload_hash,sample['window_id'],sample['sampled_at_us'],state,None)
        window = db.execute('SELECT window_id FROM windows WHERE bucket=?',
                            (sample['sampled_at_us']//300000000,)).fetchone()
        if audit!=expected or window!=(sample['window_id'],):
            raise ValueError('pending audit/window mismatch')
        return sample

    def pending(self, *, newest=False):
        with self.connect() as db:
            db.execute('BEGIN')  # queue/audit/window must share one read snapshot.
            # Direction is a local boolean choice, never caller-provided SQL.
            order='DESC' if newest else 'ASC'
            row = db.execute("SELECT sample_id,capture_seq,payload_hash,payload,state FROM queue WHERE state='pending' ORDER BY capture_seq "+order+" LIMIT 1").fetchone()
            return [self._validated_pending(db,row)] if row else []

    def pending_count(self):
        with self.connect() as db:
            return db.execute('SELECT COUNT(*) FROM queue').fetchone()[0]

    def audit_count(self):
        with self.connect() as db:
            return db.execute('SELECT COUNT(*) FROM audit').fetchone()[0]

    def latest_timestamp(self):
        with self.connect() as db:
            return int(db.execute("SELECT value FROM metadata WHERE key='latest_timestamp'").fetchone()[0])

    def _resolve(self, sample_id, payload_hash, committed):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT sample_id,capture_seq,payload_hash,payload,state FROM queue WHERE sample_id=?', (sample_id,)).fetchone()
            if not row:
                return False  # Capacity retirement may race an already sent ACK.
            if row[2] != payload_hash or row[4] != 'pending':
                raise ValueError('pending identity mismatch')
            self._validated_pending(db,row)
            state = 'committed' if committed else 'quarantine'
            db.execute('UPDATE audit SET state=?,acknowledged_us=? WHERE sample_id=?',
                       (state, time.time_ns() // 1000 if committed else None, sample_id))
            if committed:
                db.execute('DELETE FROM queue WHERE sample_id=? AND payload_hash=?', (sample_id, payload_hash))
            else:
                db.execute("UPDATE queue SET state='quarantine' WHERE sample_id=?", (sample_id,))
        return True

    def committed(self, sample_id, payload_hash):
        return self._resolve(sample_id, payload_hash, True)

    def quarantine(self, sample_id, payload_hash, error_code):
        return self._resolve(sample_id, payload_hash, False)
