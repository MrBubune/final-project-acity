# secure_mqtt_broker/admin/web.py
import eventlet
eventlet.monkey_patch()  # patch stdlib for eventlet

from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_socketio import SocketIO
import json
from database.encrypted_db import EncryptedSQLiteDB
from database.models import init_db
import config.settings as settings


app = Flask(__name__, template_folder="templates", static_folder="../static")
app.secret_key = "password123"

# ─── Setup SocketIO ──────────────────────────────────────────
socketio = SocketIO(app, async_mode="eventlet")

# ─── Init DB ─────────────────────────────────────────────────
db = EncryptedSQLiteDB(settings.DB_PATH, settings.FERNET_KEY_PATH)
init_db(db)

# ─── Simple auth check ───────────────────────────────────────
def is_logged_in():
    return session.get("user_role") == "Admin"

@app.before_request
def require_login():
    if request.endpoint not in ("login","static"):
        if not is_logged_in():
            return redirect(url_for("login"))

@app.route("/")
def index():
    return redirect(url_for("logs") if is_logged_in() else url_for("login"))

@app.route("/login", methods=("GET", "POST"))
def login():
    """
    Render the login form and handle credential checks.
    On success: store user info in session and redirect to index.
    """
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"].encode()

        # look up the user (decrypting username if needed)
        row = db.query(
            "SELECT u.id, u.password_hash, r.name AS role "
            "FROM users u JOIN roles r ON u.role_id=r.id "
            "WHERE username = ?",
            (username,)
        )
        if not row or not bcrypt.checkpw(password, row[0]["password_hash"]):
            flash("Invalid username or password", "danger")
            return render_template("login.html")

        # login success
        session.clear()
        session["user_id"]   = row[0]["id"]
        session["username"]  = username
        session["user_role"] = row[0]["role"]
        flash(f"Welcome, {username}!", "success")
        return redirect(url_for("index"))

    return render_template("login.html")
    
# ——— Users —————————————————————————————————————————————

@app.route("/users", methods=("GET","POST"))
def users():
    if request.method == "POST":
        uname = request.form["username"]
        pwd   = request.form["password"].encode()
        role  = request.form["role"]
        phash = bcrypt.hashpw(pwd, bcrypt.gensalt())
        # insert user
        db.execute(
            "INSERT INTO users(username,password_hash,role_id) "
            "VALUES (?, ?, (SELECT id FROM roles WHERE name=?))",
            (uname, phash, role)
        )
        flash(f"User '{uname}' created", "success")
        return redirect(url_for("users"))

    rows = db.query("""
        SELECT u.id, u.username, r.name AS role
          FROM users u JOIN roles r ON u.role_id=r.id
        ORDER BY u.id
    """)
    roles = [r["name"] for r in db.query("SELECT name FROM roles")]
    return render_template("users.html", users=rows, roles=roles)

# ——— ACLs ——————————————————————————————————————————————

@app.route("/acls", methods=("GET","POST"))
def acls():
    if request.method == "POST":
        user_id      = request.form["user_id"]
        topic        = request.form["topic"]
        can_sub      = 1 if "can_subscribe" in request.form else 0
        can_pub      = 1 if "can_publish"  in request.form else 0
        db.execute(
            "INSERT INTO acls(user_id,topic,can_subscribe,can_publish) "
            "VALUES (?,?,?,?)",
            (user_id, topic, can_pub, can_sub)
        )
        flash("ACL added", "success")
        return redirect(url_for("acls"))

    users = db.query("SELECT id,username FROM users")
    acls  = db.query("""
        SELECT a.id, u.username, a.topic, a.can_subscribe, a.can_publish
          FROM acls a JOIN users u ON a.user_id=u.id
        ORDER BY a.id
    """)
    return render_template("acls.html", users=users, acls=acls)

# ——— Logs ——————————————————————————————————————————————
@app.route("/logs")
def logs():
    # Load initial page with the most recent 50 entries
    rows = db.query("""
        SELECT id, timestamp, client_id, topic, action, success, details
          FROM logs
         ORDER BY id DESC
         LIMIT 50
    """, [])
    # We’ll send them in reverse so newest is on top
    rows = list(reversed(rows))
    return render_template("logs.html", logs=rows)

# ─── WebSocket: broadcast new log entries ─────────────────────
thread = None
thread_lock = eventlet.semaphore.Semaphore()

def background_log_poller():
    """Poll the DB every second for new logs and broadcast via WebSocket."""
    last_id = db.query("SELECT MAX(id) AS mid FROM logs", [])[0]["mid"] or 0
    while True:
        eventlet.sleep(1)
        new = db.query(
            "SELECT id, timestamp, client_id, topic, action, success, details "
            "FROM logs WHERE id > ? ORDER BY id ASC",
            [last_id]
        )
        for row in new:
            socketio.emit("new_log", row, namespace="/logs")
            last_id = row["id"]

@socketio.on("connect", namespace="/logs")
def on_connect():
    global thread
    with thread_lock:
        if thread is None:
            thread = socketio.start_background_task(background_log_poller)


# ——— Retained Messages ——————————————————————————————————

@app.route("/retained", methods=("GET","POST"))
def retained():
    if request.method == "POST":
        topic   = request.form["topic"]
        message = request.form["message"]
        db.execute(
            "REPLACE INTO retained_messages(topic,payload) VALUES (?,?)",
            (topic, message)
        )
        flash("Retained message set", "success")
        return redirect(url_for("retained"))

    rows = db.query("SELECT topic,payload FROM retained_messages")
    return render_template("retained.html", retained=rows)

@app.route("/publish", methods=("GET","POST"))
def publish():
    from broker.server import BrokerServer  # reuse your broker logic
    if request.method == "POST":
        topic   = request.form["topic"]
        payload = request.form["payload"]
        qos     = int(request.form["qos"])
        retain  = "retain" in request.form
        # naive: connect a temporary publisher
        from client.publisher import Publisher
        pub = Publisher(
            client_id="webui", username=session["username"],
            password=request.form["password"],
            topic=topic, message=payload, qos=qos, retain=retain
        )
        # fire‐and‐forget
        asyncio.run(pub.run())
        flash(f"Published to {topic!r} (qos={qos}, retain={retain})", "success")
        return redirect(url_for("publish"))

    return render_template("publish.html")

@app.route("/sessions")
def sessions():
    # SessionManager holds sessions in memory
    from broker.server import broker  # assume you exposed a global BrokerServer instance
    active = []
    for cid, sess in broker.router.session_mgr.sessions.items():
        active.append({
          "client_id": cid,
          "will": sess.will,
          "writer": sess.writer.get_extra_info("peername")
        })
    return render_template("sessions.html", sessions=active)

@app.route("/sessions/<client_id>/disconnect", methods=("POST",))
def disconnect_session(client_id):
    from broker.server import broker
    broker.router.session_mgr.terminate_session(client_id)
    flash(f"Session {client_id!r} disconnected", "success")
    return redirect(url_for("sessions"))

@app.route("/logs/stream")
def logs_stream():
    def gen():
        import time
        last_id = 0
        while True:
            rows = db.query(
                "SELECT id, timestamp, client_id, topic, action, success, details "
                "FROM logs WHERE id > ? ORDER BY id ASC", (last_id,)
            )
            for r in rows:
                last_id = r["id"]
                yield f"data: {json.dumps(r)}\n\n"
            time.sleep(1)
    return app.response_class(gen(), mimetype="text/event-stream")

@app.route("/acls/<int:acl_id>/delete", methods=("POST",))
def delete_acl(acl_id):
    """Delete a specific ACL entry by its ID."""
    db.execute("DELETE FROM acls WHERE id = ?", (acl_id,))
    flash(f"ACL {acl_id} deleted", "success")
    return redirect(url_for("acls"))


@app.route("/roles", methods=("GET","POST"))
def roles():
    if request.method == "POST":
        name = request.form["name"]
        db.execute("INSERT INTO roles(name) VALUES(?)", (name,))
        flash(f"Role '{name}' created", "success")
        return redirect(url_for("roles"))

    roles = db.query("SELECT id,name FROM roles ORDER BY id")
    return render_template("roles.html", roles=roles)

@app.route("/roles/<int:role_id>/delete", methods=("POST",))
def delete_role(role_id):
    db.execute("DELETE FROM roles WHERE id=?", (role_id,))
    flash(f"Role {role_id} deleted", "success")
    return redirect(url_for("roles"))

@app.route("/logout")
def logout():
    """Log the user out and redirect to the login page."""
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000, debug=True, use_reloader=False)