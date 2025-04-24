# Secure MQTT Broker with Embedded Database

A lightweight, secure MQTT broker implemented in Python, featuring:

- **Full MQTT v3.1–style** publish/subscribe with `+` and `#` wildcards  
- **QoS 0, 1, 2** message delivery  
- **Retained messages**, **Last Will & Testament**  
- **Embedded SQLite** with end-to-end encryption (Fernet)  
- **User authentication** (username/password + mutual TLS)  
- **Role-based ACLs** (Admin, Teacher, Student)  
- **CLI tools** for user, ACL and log management  
- **Flask web UI** with real-time WebSocket log viewer  
- **Pytest** suite for unit/integration tests  
- **Locust** stress test script  

---

## 📦 Repository Layout

```
.
├── broker/                # Core broker server & router logic  
├── client/                # Publisher & subscriber example clients  
├── admin/                 # CLI & Flask web UI  
│   ├── web.py             # Flask app entrypoint  
│   ├── templates/  
│   └── static/  
├── database/              # EncryptedSQLiteDB & schema definitions  
├── config/                # settings.py (paths, ports, cert locations)  
├── tests/  
│   ├── unit/              # Pytest unit/integration tests  
│   └── stress/            # locustfile.py  
├── requirements.txt       # Python dependencies  
├── .gitignore  
└── README.md
```

---

## 🏁 Quickstart

### 1. Clone & install

```bash
git clone https://github.com/MrBubune/final-project-acity/final-project-acity.git
cd secure-mqtt-broker
python -m venv .venv
source .venv/bin/activate    # Windows: .\.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure

Edit `config/settings.py` (or override via environment variables) to set:

- `DB_PATH` / `FERNET_KEY_PATH`  
- Broker `HOST` / `PORT`  
- Paths to CA, server & client certs/keys  

Generate a Fernet key and certificates if you haven’t already:

```bash
# generate Fernet key
python - <<EOF
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
EOF > fern_key.txt

# use your preferred OpenSSL commands for CA/server/client certs…
```

### 3. Initialize & seed DB

```bash
# The first time you run any CLI/web command, tables & roles are auto-created.
python -m admin.cli create-user --username admin --role Admin
```

### 4. Run the broker

```bash
python -m broker.server
# Broker listens on TLS port (default 8883)
```

### 5. Use the CLI

```bash
# create users
python -m admin.cli create-user --username teacher1 --role Teacher

# grant ACLs
python -m admin.cli add-acl --username teacher1 --topic school/# --can-publish --can-subscribe

# list users
python -m admin.cli list-users

# view logs
python -m admin.cli view-logs --limit 20 --action PUBLISH
```

### 6. Launch the Web UI

```bash
python -m admin.web
# Visit http://localhost:5000 in your browser
```

---

## 💻 Usage Examples

### Publisher

```bash
python -m client.publisher --client-id <clientid> --username <username> --password <password --topic ",topic>" --message "<message>" --retain --qos <0/1/2>
```

### Subscriber

```bash
python -m client.subscriber --client-id <clientid> --username <username> --password <password> --topic "<topic>" qos <0/1/2>
```

---

## 🔧 Development & Testing

### Unit & Integration Tests (Pytest)

```bash
pytest tests/unit
```

Covers:

- Topic wildcard matching  
- QoS handshake flows  
- Retained message persistence  
- ACL enforcement  
- CLI and web-UI view functions  

### Stress Testing (Locust)

```bash
locust -f tests/stress/locustfile.py --host broker-hostname
# Open http://localhost:8089 to configure and run load scenarios
```

---

## 🧱 Architecture Overview

1. **BrokerServer** (`broker/server.py`)  
   - Accepts TCP+TLS connections, spawns per-client tasks  
2. **Router** (`broker/router.py`)  
   - Handles CONNECT/SUBSCRIBE/PUBLISH/DISCONNECT  
   - Maintains in-memory subscription filters & retained messages  
   - Wildcard-aware dispatch  
3. **SessionManager**  
   - Tracks active sessions, pending QoS 2 states, LWT  
4. **EncryptedSQLiteDB** (`database/encrypted_db.py`)  
   - Wraps SQLite: encrypts/decrypts BLOB fields with Fernet  
   - Tables: `roles`, `users`, `acls`, `logs`, `retained_messages`  
5. **CLI** (`admin/cli.py`) & **Web UI** (`admin/web.py`)  
   - User/ACL/log management via terminal and browser  
   - WebSocket pushes for live log updates  

---

## 🚀 Roadmap / Future Enhancements

- Distributed broker clustering & high availability  
- Bridge support for cross-broker federation  
- Fine-grained ACL wildcards (e.g. topic-level permissions)  
- Web UI themes & role-based dashboards  

---

## 🤝 Contributing

1. Fork & clone  
2. Create a feature branch  
3. Run tests: `pytest && locust --help`  
4. Submit a PR with clear description & test coverage  

---

## 📄 License

This project is licensed under the MIT License. See [`LICENSE`](LICENSE) for details.
