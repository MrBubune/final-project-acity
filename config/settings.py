# config/settings.py
HOST        = "localhost"
PORT        = 8883

SERVER_CERT = "config/certs/server.crt"
SERVER_KEY  = "config/certs/server.key"
CA_CERT     = "config/certs/ca.crt"    # ← this must exist
MUTUAL_TLS  = False

DB_PATH         = "secure_mqtt_broker.db"
FERNET_KEY_PATH = "config/certs/db_fernet.key"