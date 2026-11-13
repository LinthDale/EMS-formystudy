"""Independent acquisition and MQTT sending; modem networking belongs to OS."""
import logging
import signal
import threading
import time
from .delivery import ClockGuard, Outbox, drain, encode_line
from .poller import Poller
from .publisher import Publisher

LOG = logging.getLogger(__name__)


def next_sample_deadline(previous, now, interval):
    """Keep acquisition on a fixed clock; skip missed slots without catch-up bursts."""
    deadline = previous + interval
    if deadline < now:
        deadline += (int((now - deadline) / interval) + 1) * interval
    return deadline


def run(config):
    reliable = config.get('delivery', {}).get('protocol') == 2
    if reliable:
        from .reliable_store import ReliableOutbox
        from .reliable_sender import ReliableSender
        delivery = config['delivery']
        box = ReliableOutbox(config['outbox_path'], config['queue_limit'], delivery['gateway_id'],
                             config['device_id'], delivery['stream_id'], delivery['config_revision'],
                             delivery['profile_version'], delivery['queue_byte_limit'], delivery['audit_limit'])
        publisher = ReliableSender(box, config['mqtt'], config['mode'], delivery['ack_timeout_seconds'])
    else:
        box = Outbox(config["outbox_path"], config["queue_limit"], config["device_id"])
        publisher = Publisher(config["mqtt"], config["device_id"])
    clock = ClockGuard(config["mode"], config.get("clock_sync_file"), box.latest_timestamp())
    poller = Poller(config["modbus"], mode=config['mode'])
    stop = threading.Event()

    def shutdown(signum, frame):
        stop.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, shutdown)

    def send():
        while not stop.is_set():
            try:
                sent = publisher.step(stop) if reliable else drain(box, publisher.publish, config["batch_size"], stop)
                if sent and not reliable:
                    LOG.info("broker_ack samples=%d", sent)
            except Exception as exc:
                # Do not log exception strings, connection URLs, or secrets.
                LOG.error("delivery_failed kind=%s", type(exc).__name__)
            stop.wait(1)

    publisher.start()
    sender = threading.Thread(target=send, name="delta-sender", daemon=True)
    sender.start()
    deadline = time.monotonic()
    try:
        while not stop.is_set():
            try:
                # Timestamp near acquisition; failed/incomplete polls are discarded.
                sampled_ns = clock.timestamp()
                snapshot = poller.sample()
                if reliable:
                    box.enqueue(sampled_ns, snapshot)
                else:
                    payload = encode_line(config["device_id"], snapshot, sampled_ns)
                    box.enqueue(sampled_ns, payload, snapshot)
                LOG.info("sample_queued device_id=%s time_ns=%d pending_rows=%d",
                         config["device_id"], sampled_ns, box.pending_count())
            except OverflowError:
                LOG.error("queue_full limit=%d sample_rejected", config["queue_limit"])
            except Exception as exc:
                LOG.error("sample_rejected kind=%s", type(exc).__name__)
            now = time.monotonic()
            deadline = next_sample_deadline(deadline, now, config["poll_interval"])
            stop.wait(max(0.0, deadline - now))
    finally:
        stop.set()
        sender.join(timeout=10)
        publisher.close()
