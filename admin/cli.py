# secure_mqtt_broker/admin/cli.py

import argparse
import getpass
import bcrypt

from database.encrypted_db import EncryptedSQLiteDB
from database.models import init_db
import config.settings as settings

def create_user(db, username, role):
    pwd = getpass.getpass(f"Password for {username}: ")
    pw_hash = bcrypt.hashpw(pwd.encode(), bcrypt.gensalt())

    rows = db.query("SELECT id FROM roles WHERE name = ?", (role,))
    if not rows:
        print(f"❌ Role {role!r} not found.")
        return
    role_id = rows[0]["id"]

    db.execute(
        "INSERT INTO users(username, password_hash, role_id) VALUES (?,?,?)",
        (username, pw_hash, role_id)
    )
    print(f"✅ User {username!r} created with role {role!r}.")

def add_acl(db, username, topic, can_sub, can_pub):
    rows = db.query("SELECT id FROM users WHERE username = ?", (username,))
    if not rows:
        print(f"❌ User {username!r} not found.")
        return
    user_id = rows[0]["id"]

    db.execute(
        "INSERT INTO acls(user_id, topic, can_subscribe, can_publish) VALUES (?,?,?,?)",
        (user_id, topic, int(can_sub), int(can_pub))
    )
    print(f"✅ ACL for {username!r} on topic {topic!r} added.")

def list_users(db):
    rows = db.query("""
        SELECT u.id, u.username, r.name AS role
          FROM users u
          JOIN roles r ON u.role_id = r.id
    """)
    for r in rows:
        print(f"• {r['id']}: {r['username']} ({r['role']})")

def view_logs(db, args):
    clauses, params = [], []
    if args.client_id:
        clauses.append("client_id = ?");    params.append(args.client_id)
    if args.topic:
        clauses.append("topic = ?");        params.append(args.topic)
    if args.action:
        clauses.append("action = ?");       params.append(args.action)
    if args.success is not None:
        clauses.append("success = ?");      params.append(int(args.success))

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f"""
       SELECT timestamp, client_id, topic, action, success, details
         FROM logs
       {where}
       ORDER BY id DESC
       LIMIT ?
    """
    params.append(args.limit)

    rows = db.query(sql, params)
    if not rows:
        print("No log entries found.")
        return

    print(f"{'Time':<20} {'Client':<10} {'Topic':<25} {'Action':<10} {'OK':<3} Details")
    print("-" * 80)
    for r in rows:
        ts, cid, topic, act, ok, det = (
            r["timestamp"][:19], r["client_id"],
            r["topic"], r["action"],
            r["success"], r["details"]
        )
        print(f"{ts:<20} {cid:<10} {topic:<25} {act:<10} {ok:<3} {det}")

def main():
    parser = argparse.ArgumentParser(prog="admin", description="Broker Admin CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # create-user
    cu = sub.add_parser("create-user", help="Add a new user")
    cu.add_argument("--username", required=True)
    cu.add_argument("--role", choices=["Admin","Teacher","Student"], required=True)

    # add-acl
    aa = sub.add_parser("add-acl", help="Grant a user subscribe/publish rights on a topic")
    aa.add_argument("--username", required=True)
    aa.add_argument("--topic", required=True)
    aa.add_argument("--can-subscribe", action="store_true")
    aa.add_argument("--can-publish",  action="store_true")

    # list-users
    sub.add_parser("list-users", help="List all users")

    # view-logs (define *before* parse_args)
    lv = sub.add_parser("view-logs", help="View broker event logs")
    lv.add_argument("--client-id", help="Filter by client_id")
    lv.add_argument("--topic",     help="Filter by topic")
    lv.add_argument(
        "--action",
        choices=["CONNECT","SUBSCRIBE","PUBLISH","DISCONNECT"],
        help="Filter by action"
    )
    lv.add_argument(
        "--success",
        choices=["0","1"],
        help="Filter by success flag (0=failure,1=success)"
    )
    lv.add_argument(
        "--limit", type=int, default=50,
        help="Max number of entries to show"
    )

    args = parser.parse_args()

    # initialize DB & tables once
    db = EncryptedSQLiteDB(settings.DB_PATH, settings.FERNET_KEY_PATH)
    init_db(db)

    # dispatch
    if args.cmd == "create-user":
        create_user(db, args.username, args.role)
    elif args.cmd == "add-acl":
        add_acl(db, args.username, args.topic, args.can_subscribe, args.can_publish)
    elif args.cmd == "list-users":
        list_users(db)
    elif args.cmd == "view-logs":
        view_logs(db, args)

if __name__ == "__main__":
    main()
