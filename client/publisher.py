# client/publisher.py

import asyncio
import ssl
import json
import argparse

from config.settings import HOST, PORT, CA_CERT, SERVER_CERT, SERVER_KEY, MUTUAL_TLS

class Publisher:
    def __init__(self,
                 client_id: str,
                 username: str,
                 password: str,
                 topic: str,
                 message: str,
                 qos: int = 0,
                 retain: bool = False,
                 lwt_topic: str = None,
                 lwt_payload: str = None):
        self.client_id = client_id
        self.username  = username
        self.password  = password
        self.topic     = topic
        self.message   = message
        self.qos       = qos
        self.retain    = retain
        self.lwt       = None
        if lwt_topic and lwt_payload is not None:
            self.lwt = {
                "topic":   lwt_topic,
                "payload": lwt_payload,
                "retain":  False
            }
        # packet id counter
        self._next_id = 1

    def _make_ssl_context(self) -> ssl.SSLContext:
        ctx = ssl.create_default_context(
            purpose=ssl.Purpose.SERVER_AUTH,
            cafile=CA_CERT
        )
        if MUTUAL_TLS:
            ctx.load_cert_chain(certfile=SERVER_CERT, keyfile=SERVER_KEY)
        return ctx

    def _get_packet_id(self) -> int:
        pid = self._next_id
        self._next_id = pid + 1 if pid < 0xFFFF else 1
        return pid

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
        if self.lwt:
            connect_pkt["last_will"] = self.lwt

        writer.write((json.dumps(connect_pkt) + "\n").encode())
        await writer.drain()

        resp = json.loads((await reader.readline()).decode())
        if not resp.get("success"):
            print("❌ Authentication failed")
            writer.close()
            try: await writer.wait_closed()
            except: pass
            return

        print("✅ Connected, publishing…")

        # PUBLISH
        pub_pkt = {
            "type":    "PUBLISH",
            "topic":   self.topic,
            "payload": self.message,
            "retain":  self.retain,
            "qos":     self.qos
        }
        if self.qos in (1, 2):
            pub_id = self._get_packet_id()
            pub_pkt["id"] = pub_id

        writer.write((json.dumps(pub_pkt) + "\n").encode())
        await writer.drain()

        # QoS handshakes
        if self.qos == 1:
            ack = json.loads((await reader.readline()).decode())
            if ack.get("type") == "PUBACK" and ack.get("id") == pub_id:
                print(f"✅ PUBACK received for {pub_id}")
            else:
                print("⚠️ Unexpected PUBACK:", ack)

        elif self.qos == 2:
            # wait for PUBREC
            rec = json.loads((await reader.readline()).decode())
            if rec.get("type") == "PUBREC" and rec.get("id") == pub_id:
                # send PUBREL
                rel = {"type":"PUBREL","id":pub_id}
                writer.write((json.dumps(rel) + "\n").encode())
                await writer.drain()
                # wait for PUBCOMP
                comp = json.loads((await reader.readline()).decode())
                if comp.get("type") == "PUBCOMP" and comp.get("id") == pub_id:
                    print(f"✅ PUBCOMP received for {pub_id}")
                else:
                    print("⚠️ Unexpected PUBCOMP:", comp)
            else:
                print("⚠️ Unexpected PUBREC:", rec)

        # small pause to allow dispatch
        await asyncio.sleep(0.1)

        # DISCONNECT
        writer.write((json.dumps({"type":"DISCONNECT"}) + "\n").encode())
        await writer.drain()
        writer.close()
        try: await writer.wait_closed()
        except: pass
        print("🔌 Disconnected")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Secure MQTT‑style Publisher with QoS")
    p.add_argument("--client-id",   required=True)
    p.add_argument("--username",    required=True)
    p.add_argument("--password",    required=True)
    p.add_argument("--topic",       required=True)
    p.add_argument("--message",     required=True)
    p.add_argument("--qos",         type=int, choices=[0,1,2], default=0,
                   help="Quality of Service level (0, 1, or 2)")
    p.add_argument("--retain",      action="store_true", help="Set retained flag")
    p.add_argument("--lwt-topic",   help="Last Will topic")
    p.add_argument("--lwt-payload", help="Last Will payload")
    args = p.parse_args()

    publisher = Publisher(
        client_id=args.client_id,
        username=args.username,
        password=args.password,
        topic=args.topic,
        message=args.message,
        qos=args.qos,
        retain=args.retain,
        lwt_topic=args.lwt_topic,
        lwt_payload=args.lwt_payload
    )
    asyncio.run(publisher.run())
