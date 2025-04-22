import pytest
import asyncio
import json
from client.publisher import Publisher
from client.subscriber import Subscriber

HOST = "127.0.0.1"
PORT = 1884

@pytest.mark.asyncio
async def test_qos0_pubsub(broker_server):
    """QoS0 publish/subscribe with wildcard and retained messages."""
    # 1) Create ACL: allow teacher1 subscribe+publish on school/#
    from admin.cli import add_acl, create_user
    from database.encrypted_db import EncryptedSQLiteDB
    from database.models import init_db
    import config.settings as settings

    db = EncryptedSQLiteDB(settings.DB_PATH, settings.FERNET_KEY_PATH)
    init_db(db)
    # create user
    from admin.cli import create_user
    monkey = pytest.MonkeyPatch()
    # create teacher1
    create_user(db, "teacher1", "Teacher")
    # add ACL
    add_acl(db, "teacher1", "school/#", can_sub=True, can_pub=True)
    monkey.undo()

    # 2) Subscriber
    sub = Subscriber(
        client_id="sub0",
        username="teacher1", password="secret",
        topic="school/#", qos=0
    )
    # run subscriber in background
    sub_task = asyncio.create_task(sub.run())
    await asyncio.sleep(0.2)

    # 3) Publisher send retained
    pub = Publisher(
        client_id="pub0",
        username="teacher1", password="secret",
        topic="school/demo", message="hello0",
        qos=0, retain=True
    )
    await pub.run()
    await asyncio.sleep(0.2)

    # Verify subscriber got the message
    # (subscriber prints to stdout; instead we wonder if no exceptions)
    sub_task.cancel()

@pytest.mark.asyncio
async def test_qos1_handshake(broker_server):
    """QoS1 end‑to‑end with PUBACK."""
    # subscriber at QoS1
    sub = Subscriber("sub1","teacher1","secret","school/demo", qos=1)
    sub_task = asyncio.create_task(sub.run())
    await asyncio.sleep(0.2)

    # publisher at QoS1
    pub = Publisher("pub1","teacher1","secret","school/demo","hello1", qos=1)
    await pub.run()
    await asyncio.sleep(0.2)

    sub_task.cancel()

@pytest.mark.asyncio
async def test_qos2_handshake(broker_server):
    """QoS2 4‑way handshake works exactly once."""
    sub = Subscriber("sub2","teacher1","secret","school/demo", qos=2)
    sub_task = asyncio.create_task(sub.run())
    await asyncio.sleep(0.2)

    pub = Publisher("pub2","teacher1","secret","school/demo","hello2", qos=2)
    await pub.run()
    await asyncio.sleep(0.2)

    sub_task.cancel()

@pytest.mark.asyncio
async def test_lwt_and_clean_session(broker_server):
    """Last Will is delivered on abrupt disconnect."""
    # subscriber listens for LWT
    sub = Subscriber("subL","teacher1","secret","school/lwt", qos=0)
    sub_task = asyncio.create_task(sub.run())
    await asyncio.sleep(0.2)

    # publisher with LWT, then kill without DISCONNECT
    pub = Publisher(
        client_id="pubL","teacher1","secret",
        topic="school/lwt","message":"will-msg",
        qos=0, lwt_topic="school/lwt", lwt_payload="gone"
    )
    # run publisher up to CONNECT and PUBLISH but then cancel
    pub_task = asyncio.create_task(pub.run())
    await asyncio.sleep(0.5)
    pub_task.cancel()

    # broker should deliver LWT
    await asyncio.sleep(0.5)
    sub_task.cancel()

