#!/usr/bin/env python3
"""WebSocket ↔ TCP stratum bridge for browser miners."""

import argparse
import asyncio
import json
import logging
import os
import sys
import uuid
from typing import Dict, List, Optional

import websockets

sys.path.insert(0, "/root")
from stratum_worker_status import export_ws_workers  # noqa: E402

import mining_config

# CPU pool stratum on the secondary worker (browser WS + native miners use this upstream).
STRATUM_UPSTREAM_HOST = os.environ.get("STRATUM_UPSTREAM_HOST", "").strip()
CPU_FORWARD_POOLS = frozenset(
    p.strip()
    for p in os.environ.get(
        "STRATUM_FORWARD_POOLS", "neoscrypt,yespower"
    ).split(",")
    if p.strip()
)


def stratum_upstream_host(pool_key: str) -> str:
    if STRATUM_UPSTREAM_HOST and pool_key in CPU_FORWARD_POOLS:
        return STRATUM_UPSTREAM_HOST
    return "127.0.0.1"

logger = logging.getLogger("stratum-ws")

WS_EXPORT_INTERVAL = 2.0
WS_PING_INTERVAL = 20
WS_PING_TIMEOUT = 60


class WsClientRegistry:
    def __init__(self):
        self._clients: Dict[str, Dict] = {}
        self._lock = asyncio.Lock()

    async def add(
        self,
        conn_id: str,
        pool_key: str,
        client_ip: str,
        worker: str = "",
    ) -> None:
        async with self._lock:
            self._clients[conn_id] = {
                "pool": pool_key,
                "client_ip": client_ip,
                "worker": worker,
            }

    async def set_worker(self, conn_id: str, worker: str) -> None:
        async with self._lock:
            if conn_id in self._clients:
                self._clients[conn_id]["worker"] = worker

    async def remove(self, conn_id: str) -> None:
        async with self._lock:
            self._clients.pop(conn_id, None)

    async def snapshot(self) -> Dict[str, List[Dict]]:
        async with self._lock:
            pools: Dict[str, List[Dict]] = {
                key: [] for key in mining_config.POOLS
            }
            for info in self._clients.values():
                pool_key = info.get("pool")
                if pool_key not in pools:
                    continue
                pools[pool_key].append(
                    {
                        "client_ip": info.get("client_ip"),
                        "worker": info.get("worker") or "",
                    }
                )
            return pools


registry = WsClientRegistry()


class StratumTcpClient:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self._tcp_to_ws_task: Optional[asyncio.Task] = None

    async def connect(self):
        self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
        logger.info("connected to stratum %s:%s", self.host, self.port)

    async def close(self):
        if self._tcp_to_ws_task:
            self._tcp_to_ws_task.cancel()
            try:
                await self._tcp_to_ws_task
            except asyncio.CancelledError:
                pass
            self._tcp_to_ws_task = None
        if self.writer:
            self.writer.close()
            try:
                await self.writer.wait_closed()
            except Exception:
                pass
        self.reader = None
        self.writer = None

    async def send_line(self, line: str):
        if not self.writer or self.writer.is_closing():
            raise RuntimeError("stratum not connected")
        self.writer.write((line.rstrip("\n") + "\n").encode())
        await self.writer.drain()

    async def relay_to_ws(self, ws, on_disconnect):
        assert self.reader is not None
        try:
            while True:
                data = await self.reader.readline()
                if not data:
                    logger.info(
                        "stratum %s:%s closed — browser must re-handshake",
                        self.host,
                        self.port,
                    )
                    await on_disconnect("stratum disconnected")
                    return
                await ws.send(data.decode().rstrip("\n"))
        except asyncio.CancelledError:
            raise
        except websockets.exceptions.ConnectionClosed:
            return
        except Exception as exc:
            logger.warning("tcp relay ended: %s", exc)
            await on_disconnect("stratum relay error")


def client_ip_from_ws(ws) -> str:
    request = getattr(ws, "request", None)
    headers = getattr(request, "headers", None)
    if headers is not None:
        real_ip = headers.get("X-Real-IP")
        if real_ip:
            return str(real_ip).strip()
        forwarded = headers.get("X-Forwarded-For")
        if forwarded:
            return str(forwarded).split(",")[0].strip()
    peer = ws.remote_address
    if peer:
        return str(peer[0])
    return "unknown"


async def handle_client(ws, pool_key: str):
    cfg = mining_config.POOLS.get(pool_key)
    if not cfg:
        await ws.send(json.dumps({"error": f"unknown pool: {pool_key}"}))
        await ws.close()
        return

    conn_id = uuid.uuid4().hex
    client_ip = client_ip_from_ws(ws)
    await registry.add(conn_id, pool_key, client_ip)

    upstream = stratum_upstream_host(pool_key)
    tcp = StratumTcpClient(upstream, cfg["port"])
    try:
        await tcp.connect()
    except OSError as exc:
        await registry.remove(conn_id)
        await ws.send(json.dumps({"error": f"stratum unavailable: {exc}"}))
        await ws.close()
        return

    closed = asyncio.Event()

    async def close_ws(reason: str):
        if closed.is_set():
            return
        closed.set()
        try:
            await ws.close(1012, reason[:120])
        except Exception:
            pass

    tcp._tcp_to_ws_task = asyncio.create_task(tcp.relay_to_ws(ws, close_ws))
    logger.info("ws client %s (%s) joined pool %s", client_ip, conn_id[:8], pool_key)

    try:
        async for message in ws:
            if closed.is_set():
                break
            if not isinstance(message, str):
                continue
            message = message.strip()
            if not message:
                continue
            try:
                payload = json.loads(message)
            except json.JSONDecodeError:
                await ws.send(json.dumps({"error": "invalid json"}))
                continue
            if payload.get("method") == "mining.authorize":
                user = (payload.get("params") or [""])[0]
                await registry.set_worker(conn_id, str(user))
            try:
                await tcp.send_line(message)
            except Exception as exc:
                logger.warning("stratum send failed: %s", exc)
                await close_ws("stratum send failed")
                break
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        closed.set()
        await tcp.close()
        await registry.remove(conn_id)
        logger.info("ws client %s (%s) left pool %s", client_ip, conn_id[:8], pool_key)


async def export_workers_loop():
    while True:
        try:
            pools = await registry.snapshot()
            export_ws_workers(pools)
        except Exception as exc:
            logger.debug("ws worker export failed: %s", exc)
        await asyncio.sleep(WS_EXPORT_INTERVAL)


async def main(host: str, port: int):
    async def handler(ws):
        path = getattr(getattr(ws, "request", None), "path", None) or getattr(ws, "path", "/")
        pool_key = "neoscrypt"
        parts = path.strip("/").split("/")
        if len(parts) >= 3 and parts[0] == "ws" and parts[1] == "stratum":
            pool_key = parts[2]
        await handle_client(ws, pool_key)

    async with websockets.serve(
        handler,
        host,
        port,
        max_size=2**20,
        ping_interval=WS_PING_INTERVAL,
        ping_timeout=WS_PING_TIMEOUT,
    ):
        logger.info("stratum websocket bridge on %s:%s", host, port)
        export_task = asyncio.create_task(export_workers_loop())
        try:
            await asyncio.Future()
        finally:
            export_task.cancel()
            try:
                await export_task
            except asyncio.CancelledError:
                pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8894)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    asyncio.run(main(args.host, args.port))