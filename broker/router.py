# secure_mqtt_broker/broker/router.py

import asyncio, json
from typing import Dict, List, Tuple, Optional

from broker.session import SessionManager
from database.encrypted_db import EncryptedSQLiteDB

class Router:
    def __init__(self,
                 session_mgr: SessionManager,
                 db: EncryptedSQLiteDB):
        self.session_mgr = session_mgr
        self.db          = db

        # list of (client_id, StreamWriter, topic_filter)
        self.subscriptions: List[Tuple[str, asyncio.StreamWriter, str]] = []
        self.retained = self._load_retained_messages()

    def _log(self,
             client_id: Optional[str],
             topic: Optional[str],
             action: str,
             success: bool,
             details: str = "") -> None:
        """
        Write an entry into the logs table.
        """
        self.db.execute(
            "INSERT INTO logs(client_id, topic, action, success, details) VALUES (?,?,?,?,?)",
            (
                client_id or "",
                topic    or "",
                action,
                int(success),
                details
            )
        )

    def _load_retained_messages(self) -> Dict[str, str]:
        rows = self.db.query("SELECT topic, payload FROM retained_messages")
        return {r["topic"]: r["payload"] for r in rows}

    async def handle_client(self,
                            reader: asyncio.StreamReader,
                            writer: asyncio.StreamWriter):
        peer = writer.get_extra_info("peername")
        client_id = None
        user = None
        try:
            # ─── 1) CONNECT ────────────────────────────────────────────────
            pkt = await self._recv_packet(reader)
            if pkt.get("type") != "CONNECT":
                return await self._close(writer)

            # authenticate
            user = await self.session_mgr.authenticate(
                pkt["username"], pkt["password"]
            )
            if not user:
                # log failed CONNECT
                self._log(None, None, "CONNECT", False, "auth failed")
                await self._send_packet(writer, {"type":"CONNACK","success":False})
                return await self._close(writer)

            client_id = pkt["client_id"]
            self._log(client_id, None, "CONNECT", True)

            # create session (w/ optional LWT)
            will = pkt.get("last_will")
            self.session_mgr.create_session(client_id, writer, will)
            await self._send_packet(writer, {"type":"CONNACK","success":True})

            # ─── 2) Deliver retained messages ───────────────────────────────
            for topic, msg in self.retained.items():
                if self.session_mgr.can_subscribe(user, topic):
                    await self._send_packet(writer, {
                        "type":"PUBLISH","topic":topic,
                        "payload":msg,"retain":True
                    })

            # ─── 3) Main loop (SUBSCRIBE / PUBLISH) ─────────────────────────
            while True:
                pkt = await self._recv_packet(reader)
                if not pkt or pkt.get("type") == "DISCONNECT":
                    break
                print(f"[router] received packet: {pkt!r}")
                
                # ─── SUBSCRIBE ──────────────────────────────────────────────────
                if pkt["type"] == "SUBSCRIBE":
                    success = self.session_mgr.can_subscribe(user, pkt["topic"])
                    await self._handle_subscribe(client_id, user, pkt["topic"], writer)
                    # log SUBSCRIBE attempt
                    self._log(client_id, pkt["topic"], "SUBSCRIBE", success,
                              "" if success else "ACL denied")

                # ─── PUBLISH (QoS0/1/2 step 1) ──────────────────────────────────
                elif pkt["type"] == "PUBLISH":
                    qos = pkt.get("qos", 0)
                    pid = pkt.get("id")
                    # ACL, logging, retain…
                    if not self.session_mgr.can_publish(user, pkt["topic"]):
                        # log + continue
                        continue
                    # log success, handle retained…
                    # QoS2 first handshake
                    if qos == 2 and pid is not None:
                        sess = self.session_mgr.sessions[client_id]
                        sess.pending_pubrec[pid] = (
                            pkt["topic"], pkt["payload"], pkt.get("retain", False)
                        )
                        await self._send_packet(writer, {"type":"PUBREC","id":pid})
                        continue
                    # QoS1 handshake
                    if qos == 1 and pid is not None:
                        await self._send_packet(writer, {"type":"PUBACK","id":pid})
                    # Finally dispatch to subscribers (at qos 0/1)
                    await self._dispatch_publish(
                        pkt["topic"], pkt["payload"], qos=qos
                    )
                # ─── PUBREL (QoS2 step 2) ───────────────────────────────────────
                elif pkt["type"] == "PUBREL":
                    pid = pkt.get("id")
                    sess = self.session_mgr.sessions[client_id]
                    entry = sess.pending_pubrec.pop(pid, None)
                    if entry:
                        topic, payload, retain = entry
                        # dispatch at QoS2
                        await self._dispatch_publish(topic, payload, qos=2)
                    # complete handshake
                    await self._send_packet(writer, {"type":"PUBCOMP","id":pid})


            # ─── 4) DISCONNECT / LWT ────────────────────────────────────────
        finally:
            if client_id:
                will = await self.session_mgr.terminate_session(client_id)
                # log the DISCONNECT
                self._log(client_id, None, "DISCONNECT", True)

                # ───── Remove this client's subscriptions ──────────
                before = len(self.subscriptions)
                self.subscriptions = [
                    (cid, w, filt)
                    for (cid, w, filt) in self.subscriptions
                    if cid != client_id
                ]
                after = len(self.subscriptions)
                print(f"[router] cleaned up subscriptions for {client_id!r}: "
                      f"{before}→{after}")   
                               
                if will:
                    # publish LWT on behalf of client
                    await self._handle_publish(
                        client_id="__system__",
                        user={"id":"__system__"},
                        topic=will["topic"],
                        payload=will["payload"],
                        retain=will.get("retain", False)
                    )

            await self._close(writer)


    async def _handle_subscribe(self,
                                client_id: str,
                                user: dict,
                                topic: str,
                                writer: asyncio.StreamWriter):
        print(f"[router] handling SUBSCRIBE from {client_id!r} for filter={topic!r}")
        if not self.session_mgr.can_subscribe(user, topic):
            print(f"[router]  → ACL denied, sending NACK")
            await self._send_packet(writer, {
                "type":"SUBACK", "success":False, "topic":topic
            })
            return

        # record the wildcard filter
        self.subscriptions.append((client_id, writer, topic))
        print(f"[router]  → subscription list now has {len(self.subscriptions)} entries: {self.subscriptions!r}")

        await self._send_packet(writer, {
            "type":"SUBACK", "success":True, "topic":topic
        })
        print(f"[router]  → sent SUBACK(success=True) for {topic!r}")
    
    async def _dispatch_publish(self, topic, payload, qos=0):
        for cid, w, filt in self.subscriptions:
            if self._match_topic(filt, topic):
                pid = None
                if qos in (1,2):
                    pid = self.session_mgr.next_id(cid)
                pkt = {
                    "type":   "PUBLISH",
                    "topic":  topic,
                    "payload":payload,
                    "retain": False,
                    "qos":    qos
                }
                if pid is not None:
                    pkt["id"] = pid
                await self._send_packet(w, pkt)


    def _match_topic(self, filter: str, topic: str) -> bool:
        print(f"[router] matching topic={topic!r} against filter={filter!r}")
        f_parts = filter.split('/')
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
        return len(t_parts) == len(f_parts)


    async def _recv_packet(self,
                           reader: asyncio.StreamReader) -> Optional[dict]:
        # newline‐delimited JSON framing
        line = await reader.readline()
        if not line:
            return None
        return json.loads(line.decode().strip())

    async def _send_packet(self,
                           writer: asyncio.StreamWriter,
                           packet: dict):
        data = (json.dumps(packet) + "\n").encode()
        writer.write(data)
        await writer.drain()

    async def _close(self,
                     writer: asyncio.StreamWriter):
        writer.close()
        try:
            await writer.wait_closed()
        except:
            pass
