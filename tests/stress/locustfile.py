# tests/stress/locustfile.py

import time
import paho.mqtt.client as mqtt
from locust import User, task, constant
import config.settings as settings

HOST        = settings.HOST
PORT        = settings.PORT
CA_CERT     = settings.CA_CERT
CLIENT_CERT = settings.SERVER_CERT
CLIENT_KEY  = settings.SERVER_KEY
TEST_USER   = "teacher1"
TEST_PASS   = "teacherpass"
TOPIC       = "school/locust/demo"


class MQTTPublishUser(User):
    """
    A Locust user that:
      - Connects via mutual‐TLS + user/pass
      - Publishes to a test topic in a tight loop
    Measures the round‐trip of the publish() call.
    """
    wait_time = constant(1)  # 1s between tasks

    def on_start(self):
        # 1) Create & configure client
        self.client = mqtt.Client(client_id=f"locust-{id(self)}", clean_session=True)
        self.client.tls_set(
            ca_certs=CA_CERT,
            certfile=CLIENT_CERT,
            keyfile=CLIENT_KEY,
        )
        self.client.username_pw_set(TEST_USER, TEST_PASS)

        # 2) Connect & start network loop
        self.client.connect(HOST, PORT)
        self.client.loop_start()

    @task
    def publish(self):
        # Build payload
        payload = f"locust load @ {time.time():.3f}"

        # Record start, perform publish(), record end
        start = time.time()
        res = self.client.publish(TOPIC, payload, qos=0)
        # block until sent out
        res.wait_for_publish()
        latency_ms = (time.time() - start) * 1000

        # Fire a custom “request” to Locust so it surfaces in the UI
        if res.rc == mqtt.MQTT_ERR_SUCCESS:
            self.environment.events.request.fire(
                request_type="MQTT",
                name="publish",
                response_time=latency_ms,
                response_length=len(payload),
                exception=None,
            )
        else:
            self.environment.events.request.fire(
                request_type="MQTT",
                name="publish",
                response_time=latency_ms,
                response_length=0,
                exception=Exception(f"Publish failed rc={res.rc}"),
            )

    def on_stop(self):
        # Gracefully disconnect
        self.client.loop_stop()
        self.client.disconnect()
