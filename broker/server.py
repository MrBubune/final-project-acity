import asyncio
import logging

from .router import Router
from .session import SessionManager
from .tls import create_tls_context      # or create_ssl_context, whichever you named it
from database.encrypted_db import EncryptedSQLiteDB
import config.settings as settings
from database.models import init_db


class BrokerServer:
    """An asyncio-based MQTT-like broker with TLS."""
    def __init__(self,
                 host: str = settings.HOST,
                 port: int = settings.PORT):
        self.host = host
        self.port = port

        # 1) Initialize encrypted SQLite + Fernet wrapper
        self.db = EncryptedSQLiteDB(
            db_path=settings.DB_PATH,
            key_path=settings.FERNET_KEY_PATH
        )
        init_db(self.db)

        # 2) Session manager (auth + ACL)
        self.sessions = SessionManager(self.db)

        # 3) Router (pub/sub, retained messages, LWT)
        self.router = Router(session_mgr=self.sessions, db=self.db)

        # 4) SSL/TLS context
        self.ssl_context = create_tls_context(
            certfile=settings.SERVER_CERT,
            keyfile=settings.SERVER_KEY,
            cafile=settings.CA_CERT,
            require_client_cert=settings.MUTUAL_TLS
        )

    async def handle_client(self,
                            reader: asyncio.StreamReader,
                            writer: asyncio.StreamWriter):
        peer = writer.get_extra_info('peername')
        logging.info(f"🔌 New connection from {peer}")
        # hand off to our router’s full MQTT‐style CONNECT→...→DISCONNECT loop
        await self.router.handle_client(reader, writer)

    async def start(self):
        server = await asyncio.start_server(
            self.handle_client,
            self.host,
            self.port,
            ssl=self.ssl_context
        )
        addr = server.sockets[0].getsockname()
        logging.info(f"🚀 Broker listening on {addr}")
        async with server:
            await server.serve_forever()

def main():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    broker = BrokerServer()
    try:
        asyncio.run(broker.start())
    except KeyboardInterrupt:
        logging.info("🛑 Broker shutting down")

if __name__ == '__main__':
    main()
