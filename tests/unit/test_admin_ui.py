import pytest
from admin.web import app, db, init_db
import config.settings as settings

@pytest.fixture
def client(tmp_path, monkeypatch):
    # ensure fresh DB
    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path/"ui.db"))
    monkeypatch.setattr(settings, "FERNET_KEY_PATH", str(tmp_path/"ui.key"))
    from database.encrypted_db import generate_key
    (tmp_path/"ui.key").write_bytes(generate_key())
    init_db(db)

    return app.test_client()

def login(client):
    # create an Admin user
    from admin.cli import create_user
    create_user(db, "admin", "Admin")
    client.post("/login", data={"username":"admin","password":""})
    return client

def test_user_crud_and_acl_delete(client):
    # login
    client = login(client)

    # Create user via CLI
    from admin.cli import create_user
    create_user(db, "u1", "Teacher")
    # List users page
    rv = client.get("/users")
    assert b"u1" in rv.data

    # Add ACL via web
    rv = client.post("/acls", data={
        "username":"u1", "topic":"foo/bar","can_subscribe":"y"
    }, follow_redirects=True)
    assert b"foo/bar" in rv.data

    # Delete ACL
    # find id in DB
    acl_id = db.query("SELECT id FROM acls WHERE topic=?",("foo/bar",))[0]["id"]
    rv2 = client.post(f"/acls/{acl_id}/delete", follow_redirects=True)
    assert b"deleted" in rv2.data
    assert b"foo/bar" not in rv2.data

def test_live_logs_socketio(client):
    login(client)
    socketio = app.extensions["socketio"]
    # connect socket
    client.environ_base['wsgi.url_scheme'] = 'http'
    ws = socketio.test_client(app, namespace="/logs")
    # insert a log entry directly
    db.execute(
      "INSERT INTO logs(client_id,topic,action,success,details) VALUES (?,?,?,?,?)",
      ("cid","t","PUBLISH",1,"d")
    )
    # give background poller a sec
    pytest.sleep(1.2)
    received = ws.get_received("/logs")
    assert any(msg["name"]=="new_log" for msg in received)
