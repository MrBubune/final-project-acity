import os
import time
import threading
import asyncio
import tempfile
import shutil
import pytest

from broker.server import BrokerServer
import config.settings as settings

# Use a temporary data directory & port for tests
TEST_PORT = 1884

@pytest.fixture(scope="session", autouse=True)
def test_env(tmp_path_factory, monkeypatch):
    # 1) Temporary DB & key
    tmp = tmp_path_factory.mktemp("data")
    db_path = tmp / "test.db"
    key_path = tmp / "test.key"
    # ensure key file exists
    from database.encrypted_db import generate_key
    k = generate_key()
    key_path.write_bytes(k)

    monkeypatch.setattr(settings, "DB_PATH", str(db_path))
    monkeypatch.setattr(settings, "FERNET_KEY_PATH", str(key_path))
    # override port
    monkeypatch.setattr(settings, "PORT", TEST_PORT)

    yield

@pytest.fixture(scope="session", autouse=True)
def broker_server():
    """Start the MQTT broker in a background thread."""
    server = BrokerServer(host="127.0.0.1", port=TEST_PORT)
    thr = threading.Thread(
        target=lambda: asyncio.run(server.start()),
        daemon=True
    )
    thr.start()
    # wait for server to bind
    time.sleep(1)
    yield
    # no explicit teardown; daemon thread will exit

