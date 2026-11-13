"""QoS1 broker ACK tracking, including the publish/reconnect/callback races."""
import os
import ssl
import threading
import paho.mqtt.client as mqtt


class Publisher:
    def __init__(self, config, device_id):
        self.config = config
        self.topic = f"ems/devices/{device_id}/measurements"
        self.ready = threading.Event()
        self.lock = threading.Lock()
        self.inflight = None
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                                  client_id=config["client_id"], clean_session=True)
        self.client.max_inflight_messages_set(1)
        self.client.max_queued_messages_set(1)
        self.client.reconnect_delay_set(min_delay=1, max_delay=30)
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_publish = self.on_publish
        if config.get("tls"):
            context = ssl.create_default_context(cafile=config.get("ca_file"))
            if config.get("cert_file"):
                context.load_cert_chain(config["cert_file"], config["key_file"])
            self.client.tls_set_context(context)
        if config.get("username_env"):
            username = os.environ.get(config["username_env"])
            password = os.environ.get(config["password_env"])
            if not username or not password:
                raise ValueError("MQTT credentials missing")
            self.client.username_pw_set(username, password)

    def on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            self.ready.set()
        else:
            self.ready.clear()

    def on_disconnect(self, client, userdata, flags, reason_code, properties):
        self.ready.clear()

    def on_publish(self, client, userdata, mid, reason_code, properties):
        # publish() and registration hold the same lock: an early callback waits.
        with self.lock:
            if self.inflight and self.inflight[1] == mid and reason_code == 0:
                self.inflight[2].set()

    def start(self):
        self.client.connect_async(self.config["host"], self.config["port"], keepalive=30)
        self.client.loop_start()

    def publish(self, payload):
        with self.lock:
            if self.inflight is None:
                if not self.ready.is_set():
                    return False
                info = self.client.publish(self.topic, payload, qos=1, retain=False)
                # Paho queues QoS1 on NO_CONN; wait for its eventual on_publish.
                if info.rc not in (mqtt.MQTT_ERR_SUCCESS, mqtt.MQTT_ERR_NO_CONN):
                    return False
                self.inflight = (payload, info.mid, threading.Event())
            old_payload, _, acknowledged = self.inflight
            if old_payload != payload:
                raise RuntimeError("outbox order changed while publish pending")
        if not acknowledged.wait(timeout=5):
            return False
        with self.lock:
            self.inflight = None
        return True

    def close(self):
        self.client.disconnect()
        self.client.loop_stop()
