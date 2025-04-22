# secure_mqtt_broker/database/models.py

from typing import Any
from .encrypted_db import EncryptedSQLiteDB

# ——— SQL DDL ——————————————————————————————————————

CREATE_ROLES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS roles (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT    UNIQUE NOT NULL
);
"""

CREATE_USERS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      BLOB    NOT NULL,
    password_hash BLOB    NOT NULL,
    role_id       INTEGER NOT NULL,
    FOREIGN KEY(role_id) REFERENCES roles(id)
);
"""

CREATE_ACLS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS acls (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL,
    topic           TEXT    NOT NULL,
    can_publish     INTEGER NOT NULL DEFAULT 0,
    can_subscribe   INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY(user_id) REFERENCES users(id)
);
"""

CREATE_RETAINED_MESSAGES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS retained_messages (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    topic     TEXT    NOT NULL,
    payload   BLOB,
    qos       INTEGER NOT NULL DEFAULT 0,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_LOGS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS logs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp  DATETIME DEFAULT CURRENT_TIMESTAMP,
    client_id  TEXT    NOT NULL,
    topic      TEXT    NOT NULL,
    action     TEXT    NOT NULL,
    success    INTEGER NOT NULL,
    details    BLOB
);
"""

# ——— Helpers ————————————————————————————————————————

def seed_roles(db: EncryptedSQLiteDB) -> None:
    """Insert default roles if they’re not already present."""
    rows = db.query("SELECT name FROM roles")
    existing = {r["name"] for r in rows}
    for role in ("Admin", "Teacher", "Student"):
        if role not in existing:
            db.execute("INSERT INTO roles(name) VALUES (?)", (role,))

def init_db(db: EncryptedSQLiteDB) -> None:
    """
    Create all tables (idempotent) and seed default data.
    """
    # 1) Schema
    db.execute(CREATE_ROLES_TABLE_SQL)
    db.execute(CREATE_USERS_TABLE_SQL)
    db.execute(CREATE_ACLS_TABLE_SQL)
    db.execute(CREATE_RETAINED_MESSAGES_TABLE_SQL)
    db.execute(CREATE_LOGS_TABLE_SQL)

    # 2) Seed defaults
    seed_roles(db)
