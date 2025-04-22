# client/subscriber.py

import asyncio
import ssl
import json
import argparse

from config.settings import HOST, PORT, CA_CERT, SERVER_CERT, SERVER_KEY, MUTUAL_TLS

class Subscriber:
    def __init__(self,
                 client_id: str,
                 username: str,
                 password: str,
                 topic: str,
                 qos: int = 0):
        self.client_id = client_id
        self.username  = username
        self.password  = password
        self.topic     = topic
        self.qos       = qos

    def _make_ssl_context(self) -> ssl.SSLContext:
        ctx = ssl.create_default_context(
            purpose=ssl.Purpose.SERVER_AUTH,
            cafile=CA_CERT
        )
        if MUTUAL_TLS:
            ctx.load_cert_chain(certfile=SERVER_CERT, keyfile=SERVER_KEY)
        return ctx

    async def run(self):
        ssl_ctx = self._make_ssl_context()
        reader, writer = await asyncio.open_connection(HOST, PORT, ssl=ssl_ctx)

        # CONNECT
        connect_pkt = {
            "type":      "CONNECT",
            "client_id": self.client_id,
            "username":  self.username,
            "password":  self.password
        }
        writer.write((json.dumps(connect_pkt) + "\n").encode())
        await writer.drain()

        resp = json.loads((await reader.readline()).decode())
        if not resp.get("success"):
            print("❌ Authentication failed")
            writer.close()
            try: await writer.wait_closed()
            except: pass
            return

        print("✅ Connected, subscribing…")

        # SUBSCRIBE
        sub_pkt = {
            "type":  "SUBSCRIBE",
            "topic": self.topic,
            "qos":   self.qos
        }
        writer.write((json.dumps(sub_pkt) + "\n").encode())
        await writer.drain()

        suback = json.loads((await reader.readline()).decode())
        if not suback.get("success"):
            print("❌ SUBSCRIBE failed")
            writer.close()
            try: await writer.wait_closed()
            except: pass
            return

        print(f"👂 Listening on '{self.topic}' (QoS {self.qos})…")

        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                pkt = json.loads(line.decode().strip())

                if pkt.get("type") == "PUBLISH":
                    topic   = pkt["topic"]
                    payload = pkt.get("payload")
                    retain  = pkt.get("retain", False)
                    qos     = pkt.get("qos", 0)
                    pid     = pkt.get("id")

                    flag = " (retained)" if retain else ""
                    print(f"🔔 {topic} → {payload!r}{flag} [qos={qos}, id={pid}]")

                    if qos == 1 and pid is not None:
                        # QoS1 ack
                        ack = {"type":"PUBACK","id":pid}
                        writer.write((json.dumps(ack) + "\n").encode())
                        await writer.drain()
                        print(f"   ↳ Sent PUBACK for {pid}")

                    elif qos == 2 and pid is not None:
                        # QoS2 handshake
                        # 1) send PUBREC
                        writer.write((json.dumps({"type":"PUBREC","id":pid}) + "\n").encode())
                        await writer.drain()
                        print(f"   ↳ Sent PUBREC for {pid}")
                        # 2) wait for PUBREL
                        rel = json.loads((await reader.readline()).decode())
                        if rel.get("type") == "PUBREL" and rel.get("id") == pid:
                            # 3) send PUBCOMP
                            writer.write((json.dumps({"type":"PUBCOMP","id":pid}) + "\n").encode())
                            await writer.drain()
                            print(f"   ↳ Completed QoS2 handshake for {pid}")
                        else:
                            print("⚠️ Unexpected PUBREL:", rel)

        except asyncio.CancelledError:
            pass
        finally:
            writer.close()
            try: await writer.wait_closed()
            except: pass

if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Secure MQTT‑style Subscriber with QoS")
    p.add_argument("--client-id", required=True)
    p.add_argument("--username",  required=True)
    p.add_argument("--password",  required=True)
    p.add_argument("--topic",     required=True)
    p.add_argument("--qos",       type=int, choices=[0,1,2], default=0,
                   help="Requested QoS level (0, 1, or 2)")
    args = p.parse_args()

    sub = Subscriber(
        client_id=args.client_id,
        username=args.username,
        password=args.password,
        topic=args.topic,
        qos=args.qos
    )
    asyncio.run(sub.run())
