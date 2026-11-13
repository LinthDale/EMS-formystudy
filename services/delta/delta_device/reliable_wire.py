"""PRD-0021 v2 canonical samples and fail-closed application ACK state."""
import hashlib
import json
import math
import re
from uuid import UUID, uuid4

from .config import ID

FIELDS = ('voltage', 'current', 'power_kw', 'energy_kwh')
MAX_SAMPLE = 1024
MAX_WIRE = 65536
SAMPLE_KEYS = {'sample_id', 'gateway_id', 'device_id', 'stream_id', 'capture_seq',
               'window_id', 'config_revision', 'sampled_at_us', 'profile_version',
               'time_quality', 'measurements', 'payload_hash'}
SESSION_KEYS = {'schema_version', 'gateway_id', 'session_challenge', 'recovery_generation'}
ENVELOPE_KEYS = SESSION_KEYS | {'batch_id', 'samples'}
ACK_KEYS = SESSION_KEYS | {'batch_id', 'results'}


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False,
                      separators=(',', ':')).encode('utf-8')


def uuid_text(value):
    if not isinstance(value, str) or str(UUID(value)) != value:
        raise ValueError('invalid UUID')
    return value


def identifier(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise ValueError('invalid identity')
    return value


def decode(raw, limit=MAX_WIRE):
    if not isinstance(raw, (bytes, str)) or len(raw.encode() if isinstance(raw, str) else raw) > limit:
        raise ValueError('wire size')

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate key')
            result[key] = value
        return result

    def invalid(_):
        raise ValueError('nonfinite JSON')

    try:
        value = json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)
    except (UnicodeError, RecursionError, TypeError) as exc:
        raise ValueError('invalid JSON') from exc

    def check(item, depth=0):
        if depth > 8:
            raise ValueError('JSON depth')
        if isinstance(item, dict):
            for child in item.values():
                check(child, depth + 1)
        elif isinstance(item, list):
            for child in item:
                check(child, depth + 1)
    check(value)
    return value


def sample_hash(sample):
    return hashlib.sha256(canonical({k: v for k, v in sample.items() if k != 'payload_hash'})).hexdigest()


def validate_sample(sample, gateway_id):
    if not isinstance(sample, dict) or set(sample) != SAMPLE_KEYS:
        raise ValueError('sample schema')
    if sample['gateway_id'] != identifier(gateway_id):
        raise ValueError('gateway mismatch')
    for key in ('device_id', 'config_revision', 'profile_version'):
        identifier(sample[key])
    for key in ('sample_id', 'stream_id', 'window_id'):
        uuid_text(sample[key])
    for key in ('capture_seq', 'sampled_at_us'):
        if type(sample[key]) is not int or not 1 <= sample[key] <= 2**63 - 1:
            raise ValueError('sample integer')
    if sample['time_quality'] != 'trusted':
        raise ValueError('time quality')
    measurements = sample['measurements']
    if not isinstance(measurements, dict) or set(measurements) != set(FIELDS):
        raise ValueError('measurement schema')
    normalized = dict(sample, measurements={})
    for key, value in measurements.items():
        if type(value) not in (int, float) or not 0 <= value <= 1e15 or not math.isfinite(value):
            raise ValueError('measurement value')
        normalized['measurements'][key] = float(value) if value else 0.0
    if not isinstance(sample['payload_hash'], str) or not re.fullmatch('[0-9a-f]{64}', sample['payload_hash']):
        raise ValueError('sample hash shape')
    if sample_hash(normalized) != sample['payload_hash'] or len(canonical(normalized)) > MAX_SAMPLE:
        raise ValueError('sample hash or size')
    return normalized


class AckState:
    """Caller serializes this object and SQLite deletion using the same lock."""
    def __init__(self, gateway_id):
        self.gateway_id = identifier(gateway_id)
        self.challenge = self.generation = self.batch_id = self.sample = None

    def disconnect(self):
        self.challenge = self.generation = self.batch_id = self.sample = None

    def connect(self):
        self.disconnect()
        self.challenge = str(uuid4())

    def establish(self, reply, retained=False):
        if (retained or not self.challenge or not isinstance(reply, dict)
                or set(reply) != SESSION_KEYS or type(reply.get('schema_version')) is not int
                or reply['schema_version'] != 2 or reply['gateway_id'] != self.gateway_id
                or reply['session_challenge'] != self.challenge):
            return False
        try:
            uuid_text(reply['recovery_generation'])
        except ValueError:
            return False
        # A late session response must not replace a generation with an active batch.
        if self.generation and self.generation != reply['recovery_generation']:
            return False
        self.generation = reply['recovery_generation']
        return True

    def prepare(self, sample):
        if not self.generation:
            raise ValueError('session not established')
        self.sample = validate_sample(sample, self.gateway_id)
        self.batch_id = str(uuid4())
        return dict(schema_version=2, gateway_id=self.gateway_id,
                    session_challenge=self.challenge, recovery_generation=self.generation,
                    batch_id=self.batch_id, samples=[self.sample])

    def accept(self, ack, retained=False):
        if retained or not self.sample or not isinstance(ack, dict) or set(ack) != ACK_KEYS:
            return None
        wanted = dict(schema_version=2, gateway_id=self.gateway_id, session_challenge=self.challenge,
                      recovery_generation=self.generation, batch_id=self.batch_id)
        if type(ack.get('schema_version')) is not int or any(ack.get(k) != v for k, v in wanted.items()):
            return None
        results = ack['results']
        if not isinstance(results, list) or len(results) != 1 or not isinstance(results[0], dict):
            return None
        result = results[0]
        status = result.get('status')
        if status not in ('committed', 'retryable', 'rejected'):
            return None
        expected = {'sample_id', 'payload_hash', 'status',
                    'committed_at' if status == 'committed' else 'error_code'}
        if (set(result) != expected or result.get('sample_id') != self.sample['sample_id']
                or result.get('payload_hash') != self.sample['payload_hash']):
            return None
        if status == 'committed':
            from datetime import datetime
            try:
                if not isinstance(result['committed_at'], str) or datetime.fromisoformat(result['committed_at']).tzinfo is None:
                    return None
            except ValueError:
                return None
        elif result['error_code'] not in ('conflict', 'invalid', 'unauthorized', 'outside_window', 'database', 'rate'):
            return None
        return status
