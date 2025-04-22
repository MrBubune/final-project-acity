# secure_mqtt_broker/broker/session.py

from typing import Dict, Optional
from asyncio import StreamWriter

from auth.auth import AuthManager

class Session:
    def __init__(self,
                 client_id: str,
                 writer: StreamWriter,
                 will: Optional[dict] = None):
        self.client_id = client_id
        self.writer = writer
        # will format: {"topic": str, "payload": str, "retain": bool}
        self.will = will
        self.next_msg_id = 1    # for outbound QoS1 to subscribers
        self.pending_pubrec = {}  
        # maps packet_id -> (topic, payload, retain)

class SessionManager:
    def __init__(self, db):
        """
        db: instance of EncryptedSQLiteDB
        """
        # delegate auth & ACL checks to AuthManager
        self.auth = AuthManager(db)
        # map client_id -> Session
        self.sessions: Dict[str, Session] = {}

    async def authenticate(self,
                           username: str,
                           password: str) -> Optional[dict]:
        """
        Verify credentials; returns user record dict if OK, else None.
        """
        return self.auth.verify_user(username, password)

    def create_session(self,
                       client_id: str,
                       writer: StreamWriter,
                       will: Optional[dict] = None):
        """
        Register a new client session, storing its StreamWriter and LWT.
        """
        sess = Session(client_id, writer, will)
        self.sessions[client_id] = sess
        return sess

    def next_id(self, client_id):
        sess = self.sessions[client_id]
        pid = sess.next_msg_id
        sess.next_msg_id = pid+1 if pid<0xFFFF else 1
        return pid

    def can_subscribe(self,
                      user: dict,
                      topic: str) -> bool:
        """
        ACL check before allowing a SUBSCRIBE.
        """
        return self.auth.can_subscribe(user["id"], topic)

    def can_publish(self,
                    user: dict,
                    topic: str) -> bool:
        """
        ACL check before allowing a PUBLISH.
        """
        return self.auth.can_publish(user["id"], topic)

    async def terminate_session(self,
                                client_id: str) -> Optional[dict]:
        """
        Called on DISCONNECT. Removes session and returns the Last Will
        (if any) so the router can publish it.
        """
        session = self.sessions.pop(client_id, None)
        if session and session.will:
            return session.will
        return None
