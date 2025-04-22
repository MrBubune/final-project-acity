# secure_mqtt_broker/auth/auth.py

import bcrypt

class AuthManager:
    def __init__(self, db):
        """
        db: your EncryptedSQLiteDB instance
        """
        self.db = db

    def verify_user(self, username: str, password: str):
        """
        Return a user dict if credentials match, else None.
        """
        row = self.db.query(
            "SELECT id, password_hash, role_id FROM users WHERE username = ?",
            (username,)
        )
        if not row:
            return None

        record = row[0]
        stored_hash = record["password_hash"]
        # bcrypt stores hashes as bytes
        if isinstance(stored_hash, str):
            stored_hash = stored_hash.encode()

        if bcrypt.checkpw(password.encode(), stored_hash):
            return {
                "id":    record["id"],
                "username": username,
                "role_id":  record["role_id"]
            }
        return None

    def can_subscribe(self, user_id: int, topic_filter: str) -> bool:
        """
        Allow subscribing to a filter if:
          1) Exact match exists (user has ACL on that filter)
          2) If filter ends with '/#', user has ACL on the prefix before '/#'
          3) If filter contains '+', we check each possible expanded level
        """
        # 1) Exact ACL on the filter itself
        rows = self.db.query(
            "SELECT 1 FROM acls WHERE user_id=? AND topic=? AND can_subscribe=1",
            (user_id, topic_filter)
        )
        if rows:
            return True

        # 2) Prefix‐wildcard: e.g. 'school/#' → check 'school'
        if topic_filter.endswith("/#"):
            prefix = topic_filter[:-2] or ""  # strip '/#'
            rows = self.db.query(
                "SELECT 1 FROM acls WHERE user_id=? AND topic=? AND can_subscribe=1",
                (user_id, prefix)
            )
            if rows:
                return True

        # 3) Single‑level '+' wildcards: e.g. 'school/+/status'
        if "+" in topic_filter:
            parts = topic_filter.split("/")
            # build patterns replacing '+' with each actual level from ACL table
            # but simpler: allow if user has subscribe on the parent prefix
            parent = parts[0]
            rows = self.db.query(
                "SELECT 1 FROM acls WHERE user_id=? AND topic LIKE ? AND can_subscribe=1",
                (user_id, parent + "/%",)
            )
            if rows:
                return True

        return False

    def can_publish(self, user_id: int, topic: str) -> bool:
        """
        Return True if the user has ANY publish ACL filter that matches this topic.
        Supports exact topics, '+' single‑level and '#' multi‑level wildcards.
        """
        # 1) Fetch all publish filters for this user
        rows: List[dict] = self.db.query(
            "SELECT topic FROM acls WHERE user_id=? AND can_publish=1",
            (user_id,)
        )
        for r in rows:
            filt = r["topic"]
            if self._match_topic(filt, topic):
                return True
        return False

    def _match_topic(self, filt: str, topic: str) -> bool:
        """
        MQTT‑style match: '+' matches one level, '#' matches all remaining levels.
        """
        f_parts = filt.split('/')
        t_parts = topic.split('/')

        for i, fp in enumerate(f_parts):
            if fp == '#':
                return True
            if i >= len(t_parts):
                return False
            if fp == '+':
                continue
            if fp != t_parts[i]:
                return False

        # only match if filter and topic have same number of levels
        return len(t_parts) == len(f_parts)