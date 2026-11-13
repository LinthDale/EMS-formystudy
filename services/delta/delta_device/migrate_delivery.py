"""Offline, no-clobber v1 pending -> dedicated v2 queue conversion."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from uuid import uuid4

from .config import load_config
from .delivery import encode_line
from .reliable_store import ReliableOutbox


def migrate(source, destination, limit, identity, *, source_stopped=False,
            byte_limit=4 * 1024**3, audit_limit=600000):
    source, destination = Path(source), Path(destination)
    if not source_stopped or source.is_symlink() or destination.is_symlink():
        raise ValueError('explicitly stopped source required')
    if destination.exists():
        raise FileExistsError('destination must be new')
    if not source.is_file() or source.resolve() == destination.resolve():
        raise ValueError('distinct source required')
    if destination.parent.is_symlink():
        raise ValueError('destination symlink')
    destination.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    temp = destination.parent / ('.migration-' + uuid4().hex + '.db')
    db = sqlite3.connect(source.resolve().as_uri() + '?mode=ro', uri=True, timeout=5)
    try:
        version = db.execute('PRAGMA data_version').fetchone()[0]
        db.execute('BEGIN')
        metadata = dict(db.execute('SELECT key,value FROM metadata').fetchall())
        if metadata.get('device_id') != identity['device_id'] or metadata.get('protocol', '1') != '1':
            raise ValueError('legacy queue identity mismatch')
        rows = db.execute('SELECT id,sampled_ns,payload,snapshot FROM outbox ORDER BY id').fetchall()
        if len(rows) > limit or len(rows) > audit_limit:
            raise OverflowError('destination capacity')
        box = ReliableOutbox(temp, limit, **identity, byte_limit=byte_limit, audit_limit=audit_limit)
        mapping = []
        for old_id, ns, payload, snapshot_text in rows:
            snapshot = json.loads(snapshot_text)
            if encode_line(identity['device_id'], snapshot, ns) != payload:
                raise ValueError('legacy payload differs from stored source snapshot')
            sample = box.enqueue(ns, snapshot)
            mapping.append(dict(legacy_row_id=old_id, sample_id=sample['sample_id'], payload_hash=sample['payload_hash']))
        if box.retention_status()['audit_evicted_total']:
            raise OverflowError('destination cannot retain complete migration')
        receipt = dict(rows=len(rows), source_digest=hashlib.sha256(json.dumps(rows, separators=(',', ':')).encode()).hexdigest(),
                       mapping=mapping, scope='pending only; previously v1-deleted samples are not recoverable')
        with box.connect() as target:
            high = max(box.latest_timestamp(), int(metadata.get('latest_timestamp', '0')))
            target.execute("UPDATE metadata SET value=? WHERE key='latest_timestamp'", (str(high),))
            target.execute("INSERT INTO metadata VALUES ('v1_migration',?)", (json.dumps(receipt, separators=(',', ':')),))
        db.commit()
        if db.execute('PRAGMA data_version').fetchone()[0] != version:
            raise ValueError('source changed while converting')
        # Same-filesystem hard link is atomic and refuses an existing target.
        # A crash before this point leaves only a non-runnable temporary file.
        os.link(temp, destination)
        directory_fd = os.open(destination.parent, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        return receipt
    finally:
        db.close()
        if temp.exists():
            temp.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--config', required=True, help='validated v2 config with a new destination path')
    parser.add_argument('--source-stopped', action='store_true')
    args = parser.parse_args()
    config = load_config(args.config)
    delivery = config.get('delivery', {})
    if delivery.get('protocol') != 2:
        raise ValueError('v2 config required')
    identity = {k: delivery[k] for k in ('gateway_id', 'stream_id', 'config_revision', 'profile_version')}
    identity['device_id'] = config['device_id']
    result = migrate(args.source, config['outbox_path'], config['queue_limit'], identity,
                     source_stopped=args.source_stopped, byte_limit=delivery['queue_byte_limit'],
                     audit_limit=delivery['audit_limit'])
    print(json.dumps(dict(rows=result['rows'], source_digest=result['source_digest'])))


if __name__ == '__main__':
    main()
