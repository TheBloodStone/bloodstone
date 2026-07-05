#!/usr/bin/env python3
"""Bloodstone SHA256D (auxpow) stratum server for SHA256 ASICs / Bitaxe."""

import argparse
import asyncio
import binascii
import hashlib
import json
import logging
import os
import struct
import sys
import time
from typing import Dict, Optional, Tuple

sys.path.insert(0, "/root")
from stratum_utils import address_from_worker, block_job_is_stale  # noqa: E402
from stratum_worker_status import (  # noqa: E402
    stratum_export_loop,
    stratum_mobile_contrib_loop,
)
from stratum_extensions import (  # noqa: E402
    handle_client_get_version,
    handle_configure,
    handle_mining_ping,
)
import pool_db  # noqa: E402
import bloodstone_broadcast  # noqa: E402
import pool_sha256_miner as sha256_miner  # noqa: E402
import rod_dual_submit  # noqa: E402

POOL_WALLET = os.environ.get(
    "BLOODSTONE_SHA256_POOL_WALLET",
    os.environ.get(
        "BLOODSTONE_SHA256_POOL_PAYOUT",
        os.environ.get(
            "BLOODSTONE_POOL_WALLET",
            os.environ.get(
                "BLOODSTONE_DEFAULT_PAYOUT_ADDRESS",
                "SNQ2mNsQSumv1P4QdiDqYz5sjCwdDTnbWV",
            ),
        ),
    ),
)
POOL_FEE_PCT = float(os.environ.get("BLOODSTONE_POOL_FEE_PCT", "1.0"))

sys.path.insert(0, "/root/bloodstone-core/test/functional/test_framework")
import auxpow  # noqa: E402

DIFF1_TARGET = 0x00000000FFFF0000000000000000000000000000000000000000000000000000


def reverse_hex_bytes(hex_str: str) -> str:
    return binascii.hexlify(binascii.unhexlify(hex_str)[::-1]).decode()


def target_hex_to_int(target_hex: str) -> int:
    raw = binascii.unhexlify(target_hex)
    return int.from_bytes(raw[::-1], "big")


def int_to_compare_hex(value: int) -> str:
    """Convert a target integer to hex for lexicographic PoW comparison."""
    mem = value.to_bytes(32, byteorder="little", signed=False)
    return reverse_hex_bytes(binascii.hexlify(mem).decode())


def target_to_difficulty(target: int) -> float:
    if target <= 0:
        return 1.0
    return DIFF1_TARGET / target


def double_sha256(data: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()


class RpcClient:
    def __init__(self, url: str):
        from urllib.parse import urlparse
        import base64

        parsed = urlparse(url)
        self.endpoint = f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"
        self.path = parsed.path or "/"
        creds = ""
        if parsed.username:
            creds = base64.b64encode(
                f"{parsed.username}:{parsed.password}".encode()
            ).decode()
        self.auth_header = f"Basic {creds}" if creds else ""
        self._id = 0
        self._lock: Optional[asyncio.Lock] = None

    def _lock_get(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    def _call_sync(self, method: str, params=None):
        import urllib.request

        self._id += 1
        payload = json.dumps(
            {
                "jsonrpc": "1.0",
                "id": self._id,
                "method": method,
                "params": params or [],
            }
        ).encode()
        req = urllib.request.Request(
            self.endpoint + self.path,
            data=payload,
            headers={
                "content-type": "text/plain",
                "authorization": self.auth_header,
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read().decode())
        if body.get("error"):
            raise RuntimeError(body["error"])
        return body["result"]

    async def call(self, method: str, params=None):
        async with self._lock_get():
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, self._call_sync, method, params)


class Job:
    def __init__(
        self,
        job_id: str,
        auxblock: dict,
        tx_template: str,
        extranonce1: str,
        share_target_hex: str,
        block_target_hex: str,
        rod_auxblock: Optional[dict] = None,
        *,
        rod_merge_block_diff: bool = False,
        notify_difficulty: float = 0.0,
    ):
        self.job_id = job_id
        self.auxblock = auxblock
        self.tx_template = tx_template
        self.extranonce1 = extranonce1
        self.share_target_hex = share_target_hex
        self.block_target_hex = block_target_hex
        self.rod_auxblock = rod_auxblock
        self.rod_merge_block_diff = bool(rod_merge_block_diff)
        self.notify_difficulty = float(notify_difficulty or 0.0)
        self.stone_block_target_hex = block_target_hex
        self.rod_block_target_hex = block_target_hex
        self.rod_share_target_hex = share_target_hex


class StratumClient:
    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        server: "StratumServer",
    ):
        self.reader = reader
        self.writer = writer
        self.server = server
        self.address: Optional[str] = None
        self.worker: str = ""
        self.extranonce1: str = ""
        self.solo_mode = False
        self.user_agent = ""
        self.miner_kind = "asic"
        self.share_difficulty = server.share_difficulty
        self.authorized = False
        self._auth_lock = asyncio.Lock()
        self.jobs: Dict[str, Job] = {}
        self.current_job_height = 0
        self.rod_address: Optional[str] = None
        self.configured = False
        self.version_mask = "1fffe000"

    async def ensure_authorized(self, user: str, *, issue_work: bool = True) -> bool:
        if self.authorized:
            return True
        async with self._auth_lock:
            if self.authorized:
                return True
            if not self.extranonce1:
                logging.warning(
                    "authorize skipped for %r: subscribe first (peer=%s)",
                    user,
                    self.writer.get_extra_info("peername"),
                )
                return False
            self.worker = user
            self.address, fallback = address_from_worker(user)
            self.rod_address = self.server.resolve_rod_payout(self.address)
            if not issue_work:
                self.authorized = True
                logging.info(
                    "implicit authorize %s on submit (peer=%s)",
                    user,
                    self.writer.get_extra_info("peername"),
                )
                return True
            self.authorized = True
            if fallback:
                logging.info(
                    "using default payout %s for worker %r",
                    self.address,
                    user,
                )
            else:
                rod_note = (
                    f" rod={self.rod_address[:12]}…"
                    if self.rod_address and len(self.rod_address) > 12
                    else (" rod=" + self.rod_address if self.rod_address else "")
                )
                peer = self.writer.get_extra_info("peername")
                peer_ip = peer[0] if peer else None
                try:
                    import pool_bitaxe as pbx

                    pbx.register_stratum_peer(
                        self.address, user, peer_ip, user_agent=self.user_agent
                    )
                except Exception:
                    pass
                logging.info(
                    "authorized %s kind=%s diff=%.8f%s (peer=%s)",
                    user,
                    self.miner_kind,
                    self.share_difficulty,
                    rod_note,
                    self.writer.get_extra_info("peername"),
                )
            try:
                await self.server.push_job(self)
            except RuntimeError as exc:
                if "sha256d not allowed" in str(exc):
                    logging.info("authorize deferred for %s: %s", user, exc)
                    return True
                logging.warning(
                    "authorize job failed for %s (payout %s): %s",
                    user,
                    self.address,
                    exc,
                )
                return False
            except Exception as exc:
                logging.warning(
                    "authorize job failed for %s (payout %s): %s",
                    user,
                    self.address,
                    exc,
                )
                return False
            return True

    async def send(self, method: str, params, msg_id=None):
        payload = {"id": msg_id, "method": method, "params": params}
        self.writer.write((json.dumps(payload) + "\n").encode())
        await self.writer.drain()

    async def send_mining_stop(self) -> None:
        await self.send("mining.stop", [])

    async def reply(self, msg_id, result=None, error=None):
        payload = {"id": msg_id, "result": result, "error": error}
        self.writer.write((json.dumps(payload) + "\n").encode())
        await self.writer.drain()

    async def handle(self):
        peer = self.writer.get_extra_info("peername")
        logging.info("sha256 client from %s", peer)
        try:
            while True:
                line = await self.reader.readline()
                if not line:
                    break
                try:
                    await self.dispatch(json.loads(line.decode().strip()))
                except json.JSONDecodeError as exc:
                    logging.warning("bad json from %s: %s", peer, exc)
                except Exception as exc:
                    logging.exception("request error from %s: %s", peer, exc)
        except Exception as exc:
            logging.exception("client connection error: %s", exc)
        finally:
            peer = self.writer.get_extra_info("peername")
            logging.info("sha256 disconnect %s worker=%s", peer, self.worker or "-")
            self.writer.close()
            await self.writer.wait_closed()

    async def dispatch(self, msg):
        msg_id = msg.get("id")
        method = msg.get("method")
        params = msg.get("params", [])

        if method == "mining.subscribe":
            self.user_agent = str(params[0]).strip() if params else ""
            self.miner_kind = sha256_miner.classify_miner(self.user_agent, self.worker)
            self.share_difficulty = sha256_miner.default_share_difficulty(
                self.miner_kind, self.server.share_difficulty
            )
            self.extranonce1 = binascii.hexlify(os.urandom(4)).decode("ascii")
            await self.reply(
                msg_id,
                [
                    [
                        ["mining.set_difficulty", "bloodstone-sha256"],
                        ["mining.notify", "bloodstone-sha256"],
                    ],
                    self.extranonce1,
                    4,
                ],
            )
            return

        if method == "mining.authorize":
            user = params[0] if params else ""
            password = params[1] if len(params) > 1 else ""
            self.solo_mode = str(password).strip().lower() == "solo"
            self.worker = str(user).strip()
            self.miner_kind = sha256_miner.classify_miner(
                self.user_agent, self.worker
            )
            self.share_difficulty = sha256_miner.default_share_difficulty(
                self.miner_kind, self.server.share_difficulty
            )
            ok = await self.ensure_authorized(user)
            if not ok:
                await self.reply(msg_id, False, [24, "cannot create work", None])
                return
            await self.reply(msg_id, True, None)
            return

        if method == "mining.submit":
            worker = str(params[0]).strip() if params else ""
            if not self.authorized:
                if not worker or not await self.ensure_authorized(
                    worker, issue_work=False
                ):
                    peer = self.writer.get_extra_info("peername")
                    logging.warning(
                        "submit rejected (not authorized) worker=%r peer=%s job=%s",
                        worker or self.worker,
                        peer,
                        params[1] if len(params) > 1 else "-",
                    )
                    await self.reply(msg_id, False, [21, "not authorized", None])
                    return
            ok = await self.server.handle_submit(self, params)
            await self.reply(
                msg_id,
                ok,
                None if ok else [20, "rejected", None],
            )
            return

        if method == "mining.extranonce.subscribe":
            await self.reply(msg_id, True, None)
            return

        if method == "mining.configure":
            await handle_configure(self, msg_id, params)
            return

        if method == "client.get_version":
            await handle_client_get_version(self, msg_id)
            return

        if method == "mining.ping":
            await handle_mining_ping(self, msg_id)
            return

        if method == "mining.suggest_difficulty":
            suggested = params[0] if params else None
            if suggested is not None and not self.solo_mode:
                self.share_difficulty = sha256_miner.clamp_suggested_difficulty(
                    self.miner_kind,
                    float(suggested),
                    self.server.share_difficulty,
                )
                try:
                    await self.server.push_job(self)
                except Exception as exc:
                    logging.warning(
                        "vardiff refresh failed for %s: %s",
                        self.worker or self.address,
                        exc,
                    )
            await self.reply(msg_id, True, None)
            return

        if msg_id is not None:
            await self.reply(msg_id, None, None)


class StratumServer:
    def __init__(
        self,
        rpc_url: str,
        host: str,
        port: int,
        share_difficulty: float,
        rod_rpc_url: str = "",
        rod_pool_wallet: str = "",
        rod_dual_submit: bool = True,
    ):
        self.rpc_url = rpc_url
        self.host = host
        self.port = port
        self.share_difficulty = share_difficulty
        self.pool_wallet = POOL_WALLET
        self.pool_fee_pct = POOL_FEE_PCT
        self.rpc = RpcClient(rpc_url)
        self.rod_dual_submit = bool(rod_dual_submit)
        self.rod_pool_wallet = (rod_pool_wallet or "").strip()
        self.rod_rpc = (
            RpcClient(rod_rpc_url)
            if rod_rpc_url and self.rod_dual_submit
            else None
        )
        self.clients = set()
        self.job_counter = 0
        self.jobs_by_id: Dict[str, Job] = {}
        self.tip_height = -1
        self.job_refresh_interval = 1.0
        self._refresh_lock: Optional[asyncio.Lock] = None
        self._submit_lock: Optional[asyncio.Lock] = None
        self._submitted_blocks: Dict[str, float] = {}
        self._rod_submitted_blocks: Dict[str, float] = {}
        self._last_refresh_at = 0.0
        self._sha256d_idle = False
        self._sha256d_idle_height = -1
        self._rod_block_diff_mode = sha256_miner.rod_block_diff_mode_enabled()
        self._asic_diff_min = sha256_miner.get_asic_diff_min()
        self._overrides_mtime = sha256_miner.service_overrides_mtime()
        self._pool_last_share_accept_at = 0.0

    @staticmethod
    def sha256d_allowed_for_height(height: int) -> bool:
        """Return whether sha256d can mine the block at the given height."""
        return height >= 1

    def _refresh_lock_get(self) -> asyncio.Lock:
        if self._refresh_lock is None:
            self._refresh_lock = asyncio.Lock()
        return self._refresh_lock

    def _submit_lock_get(self) -> asyncio.Lock:
        if self._submit_lock is None:
            self._submit_lock = asyncio.Lock()
        return self._submit_lock

    def _already_submitted(self, block_hash: str) -> bool:
        now = time.monotonic()
        stale = [h for h, ts in self._submitted_blocks.items() if now - ts > 3600]
        for h in stale:
            self._submitted_blocks.pop(h, None)
        return block_hash in self._submitted_blocks

    def _mark_submitted(self, block_hash: str) -> None:
        self._submitted_blocks[block_hash] = time.monotonic()

    def resolve_rod_payout(self, stone_address: Optional[str]) -> Optional[str]:
        addr = (stone_address or "").strip()
        if addr:
            try:
                registered = pool_db.get_miner_rod_wallet(addr)
            except Exception as exc:
                logging.debug("ROD wallet lookup failed for %s: %s", addr, exc)
                registered = None
            if registered:
                return registered
        return self.rod_pool_wallet or None

    async def apply_pool_vardiff_on_share(self) -> None:
        """Retarget pool SHA256 difficulty toward ~30s between accepted shares."""
        if not sha256_miner.pool_vardiff_enabled():
            return
        now = time.time()
        last = float(self._pool_last_share_accept_at or 0.0)
        self._pool_last_share_accept_at = now
        if last <= 0:
            return
        old = float(self.share_difficulty or 0.0)
        new = sha256_miner.pool_vardiff_adjust(old, now - last)
        if abs(new - old) / max(old, 1e-20) < 0.02:
            return
        self.share_difficulty = sha256_miner.save_runtime_share_difficulty(
            new, reason="pool_vardiff"
        )
        logging.info(
            "sha256d pool vardiff %.8f -> %.8f (elapsed %.1fs, target %.0fs)",
            old,
            self.share_difficulty,
            now - last,
            sha256_miner.pool_target_share_interval(),
        )
        if self._rod_block_diff_mode:
            return
        for client in list(self.clients):
            if not client.authorized or client.solo_mode:
                continue
            if str(getattr(client, "miner_kind", "") or "").lower() == "android":
                continue
            client.share_difficulty = sha256_miner.default_share_difficulty(
                client.miner_kind, self.share_difficulty
            )
            try:
                await client.send(
                    "mining.set_difficulty", [client.share_difficulty]
                )
            except Exception as exc:
                logging.warning(
                    "set_difficulty failed for %s after pool vardiff: %s",
                    client.worker or client.address,
                    exc,
                )

    async def apply_client_vardiff_on_share(self, client: "StratumClient") -> None:
        """Per-client SHA256 difficulty toward ~30s between accepted shares."""
        kind = str(getattr(client, "miner_kind", "") or "").lower()
        if kind != "android" and not client.solo_mode:
            return
        now = time.time()
        last = float(getattr(client, "_last_share_accept_at", 0.0) or 0.0)
        client._last_share_accept_at = now
        if last <= 0:
            return
        old = float(client.share_difficulty or 0.0)
        new = sha256_miner.android_vardiff_adjust(
            old, now - last, self.share_difficulty
        )
        if abs(new - old) / max(old, 1e-20) < 0.02:
            return
        client.share_difficulty = new
        try:
            await client.send("mining.set_difficulty", [client.share_difficulty])
        except Exception as exc:
            logging.warning(
                "set_difficulty failed for %s after android vardiff: %s",
                client.worker or client.address,
                exc,
            )

    async def apply_client_block_vardiff(self, client: "StratumClient") -> None:
        """Solo/pool per-client SHA256 difficulty toward ~30s between block finds."""
        now = time.time()
        last = float(getattr(client, "_last_block_find_at", 0.0) or 0.0)
        client._last_block_find_at = now
        if last <= 0:
            return
        old = float(client.share_difficulty or 0.0)
        if old <= 0:
            client.share_difficulty = sha256_miner.default_share_difficulty(
                client.miner_kind, self.share_difficulty
            )
            return
        new = sha256_miner.android_vardiff_adjust(
            old, now - last, self.share_difficulty
        )
        if abs(new - old) / max(old, 1e-20) < 0.02:
            return
        client.share_difficulty = new
        logging.info(
            "sha256d block vardiff worker=%s diff=%.8f -> %.8f (elapsed %.1fs)",
            client.worker or client.address,
            old,
            new,
            now - last,
        )
        try:
            await client.send("mining.set_difficulty", [client.share_difficulty])
        except Exception as exc:
            logging.warning(
                "set_difficulty failed for %s after block vardiff: %s",
                client.worker or client.address,
                exc,
            )

    async def apply_pool_difficulty_bump(self, block_height: int) -> None:
        """Increase pool share difficulty after each accepted block find."""
        if not sha256_miner.block_bump_on_find_enabled():
            return
        old = float(self.share_difficulty or 0.0)
        new = sha256_miner.bump_share_difficulty_on_block(
            old, block_height=int(block_height)
        )
        if new <= old:
            return
        self.share_difficulty = new
        logging.info(
            "sha256d pool share_difficulty %.8f -> %.8f after block height %s",
            old,
            new,
            block_height,
        )
        if self._rod_block_diff_mode:
            return
        for client in list(self.clients):
            if not client.authorized or client.solo_mode:
                continue
            client.share_difficulty = sha256_miner.default_share_difficulty(
                client.miner_kind, self.share_difficulty
            )
            try:
                await client.send(
                    "mining.set_difficulty", [client.share_difficulty]
                )
            except Exception as exc:
                logging.warning(
                    "set_difficulty failed for %s after block bump: %s",
                    client.worker or client.address,
                    exc,
                )

    async def refresh_all_jobs(self, reason: str) -> None:
        clients = [c for c in list(self.clients) if c.authorized and c.address]
        if not clients:
            return
        async with self._refresh_lock_get():
            self._last_refresh_at = time.monotonic()
            logging.info(
                "refreshing sha256d jobs for %d client(s): %s",
                len(clients),
                reason,
            )
            for client in clients:
                try:
                    await self.push_job(client)
                except Exception as exc:
                    logging.warning(
                        "job refresh failed for %s: %s",
                        client.worker or client.address,
                        exc,
                    )

    async def _apply_pool_difficulty_sync(self, reason: str) -> None:
        base_diff = sha256_miner.load_base_share_difficulty(self.share_difficulty)
        new_diff, changed = sha256_miner.apply_runtime_difficulty_from_settings(
            self.share_difficulty, base_diff=base_diff
        )
        if not changed:
            return
        old = float(self.share_difficulty or 0.0)
        self.share_difficulty = new_diff
        logging.info(
            "sha256d pool share_difficulty %.8f -> %.8f (%s)",
            old,
            new_diff,
            reason,
        )
        if self._rod_block_diff_mode:
            await self.refresh_all_jobs("pool share difficulty settings changed")
            return
        for client in list(self.clients):
            if not client.authorized or client.solo_mode:
                continue
            client.share_difficulty = sha256_miner.default_share_difficulty(
                client.miner_kind, self.share_difficulty
            )
            try:
                await client.send("mining.set_difficulty", [client.share_difficulty])
            except Exception as exc:
                logging.warning(
                    "set_difficulty failed for %s: %s",
                    client.worker or client.address,
                    exc,
                )

    def _sync_pool_overrides(self) -> Tuple[bool, bool]:
        mode = sha256_miner.rod_block_diff_mode_enabled()
        asic_min = sha256_miner.get_asic_diff_min()
        mtime = sha256_miner.service_overrides_mtime()
        rod_changed = mode != self._rod_block_diff_mode
        diff_changed = (
            mtime != self._overrides_mtime
            or asic_min != self._asic_diff_min
        )
        self._rod_block_diff_mode = mode
        self._asic_diff_min = asic_min
        self._overrides_mtime = mtime
        return rod_changed, diff_changed

    async def refresh_jobs_loop(self) -> None:
        while True:
            try:
                rod_changed, diff_changed = self._sync_pool_overrides()
                if diff_changed:
                    await self._apply_pool_difficulty_sync("dashboard difficulty settings")
                if rod_changed:
                    await self.refresh_all_jobs("ROD block difficulty mode changed")
                elif diff_changed:
                    await self.refresh_all_jobs("pool share difficulty settings changed")
                tip = int(await self.rpc.call("getblockcount"))
                if self.tip_height < 0:
                    self.tip_height = tip
                elif tip != self.tip_height:
                    old_tip = self.tip_height
                    self.tip_height = tip
                    await self.refresh_all_jobs(f"chain tip {old_tip} -> {tip}")
                else:
                    next_h = tip + 1
                    if not self.sha256d_allowed_for_height(next_h):
                        if not self._sha256d_idle or self._sha256d_idle_height != next_h:
                            await self._notify_sha256d_idle(tip)
                    else:
                        self._sha256d_idle = False
                        self._sha256d_idle_height = -1
                        stale = any(
                            c.authorized
                            and c.address
                            and c.current_job_height != next_h
                            for c in self.clients
                        )
                        if stale:
                            await self.refresh_all_jobs(
                                f"client job behind tip {tip}"
                            )
            except Exception as exc:
                logging.warning("sha256d job refresh poll failed: %s", exc)
            await asyncio.sleep(self.job_refresh_interval)

    def remember_job(self, job: Job) -> None:
        self.jobs_by_id[job.job_id] = job
        if len(self.jobs_by_id) > 512:
            oldest = sorted(self.jobs_by_id)[:128]
            for job_id in oldest:
                self.jobs_by_id.pop(job_id, None)

    def _extranonce_offset(self, tx_bytes: bytearray) -> int:
        script_start = tx_bytes.index(b"\xfa\xbe")
        return script_start + 40

    def build_stratum_parts(
        self, block_hash: str, extranonce1: str
    ) -> Tuple[str, str, str, str]:
        tx, header = auxpow.constructAuxpow(block_hash)
        tx_bytes = bytearray(binascii.unhexlify(tx))
        insert_at = self._extranonce_offset(tx_bytes)
        tx_bytes[insert_at : insert_at + 4] = binascii.unhexlify(extranonce1)
        tx_hex = binascii.hexlify(tx_bytes).decode("ascii")
        # Bitaxe builds coinbase as coinb1 + extranonce1 + extranonce2 + coinb2.
        # Do not embed extranonce1 in coinb1; subscribe supplies it separately.
        coinb1 = tx_hex[: insert_at * 2]
        coinb2 = tx_hex[(insert_at + 8) * 2 :]
        prevhash = header[8:72]
        return tx_hex, coinb1, coinb2, prevhash

    async def _notify_sha256d_idle(self, tip_height: int) -> None:
        next_h = tip_height + 1
        if self._sha256d_idle and self._sha256d_idle_height == next_h:
            return
        self._sha256d_idle = True
        self._sha256d_idle_height = next_h
        logging.info(
            "sha256d mining paused: block %d requires another algo; "
            "waiting for neoscrypt/yespower miners",
            next_h,
        )
        for client in list(self.clients):
            if client.authorized:
                try:
                    await client.send_mining_stop()
                except Exception as exc:
                    logging.warning(
                        "mining.stop failed for %s: %s",
                        client.worker or client.address,
                        exc,
                    )

    async def create_job(
        self,
        address: str,
        extranonce1: str,
        solo: bool = False,
        share_difficulty: Optional[float] = None,
        rod_payout_address: Optional[str] = None,
    ) -> Job:
        tip = int(await self.rpc.call("getblockcount"))
        next_h = tip + 1
        if not self.sha256d_allowed_for_height(next_h):
            await self._notify_sha256d_idle(tip)
            raise RuntimeError(
                f"sha256d not allowed for block height {next_h}"
            )
        self._sha256d_idle = False
        self._sha256d_idle_height = -1
        try:
            auxblock = await self.rpc.call("createauxblock", [address])
        except RuntimeError as exc:
            err = exc.args[0] if exc.args else {}
            if isinstance(err, dict) and "bad-block-algo" in str(
                err.get("message", "")
            ):
                await self._notify_sha256d_idle(tip)
            raise
        pool_diff = (
            float(share_difficulty)
            if share_difficulty and share_difficulty > 0
            else self.share_difficulty
        )
        tx_hex, _, _, _ = self.build_stratum_parts(auxblock["hash"], extranonce1)
        rod_auxblock = None
        rod_wallet = (rod_payout_address or "").strip() or self.rod_pool_wallet
        if (
            not rod_wallet
            and sha256_miner.rod_block_diff_mode_enabled()
            and self.pool_wallet
        ):
            try:
                rod_wallet = pool_db.get_miner_rod_wallet(self.pool_wallet) or ""
            except Exception as exc:
                logging.debug(
                    "pool ROD wallet fallback lookup failed: %s", exc
                )
                rod_wallet = ""
        if self.rod_rpc and rod_wallet:
            rod_auxblock = await rod_dual_submit.fetch_rod_auxblock(
                self.rod_rpc,
                rod_wallet,
            )
            if rod_auxblock:
                pool_db.record_dual_chain_event(
                    chain="rod",
                    event_type="job",
                    status="accepted",
                    rod_address=rod_wallet,
                    pool="sha256d",
                    job_height=int(rod_auxblock.get("height") or 0),
                    block_hash=str(rod_auxblock.get("hash") or ""),
                    detail="rod auxblock ready",
                )
        # ROD payout on a worker must not force block-level pool difficulty.
        # Merge-mining aux work still attaches when rod_auxblock is present;
        # rod_block_diff_mode_enabled() alone opts into ROD block target for shares.
        rod_merge_for_job = bool(
            rod_auxblock and sha256_miner.rod_block_diff_mode_enabled()
        )
        targets = sha256_miner.compute_job_targets(
            stone_auxblock=auxblock,
            rod_auxblock=rod_auxblock,
            pool_diff=pool_diff,
            solo=solo,
            rod_block_diff_mode=rod_merge_for_job,
        )
        share_target_hex = int_to_compare_hex(targets["share_target_int"])
        block_target_hex = int_to_compare_hex(targets["block_target_int"])
        stone_block_target_hex = int_to_compare_hex(
            targets["stone_block_target_int"]
        )
        rod_block_target_hex = (
            int_to_compare_hex(targets["rod_block_target_int"])
            if targets.get("rod_block_target_int") is not None
            else stone_block_target_hex
        )
        rod_share_target_hex = int_to_compare_hex(targets["rod_share_target_int"])
        self.job_counter += 1
        job_id = f"{auxblock['height']:x}.{self.job_counter:x}"
        job = Job(
            job_id=job_id,
            auxblock=auxblock,
            tx_template=tx_hex,
            extranonce1=extranonce1,
            share_target_hex=share_target_hex,
            block_target_hex=block_target_hex,
            rod_auxblock=rod_auxblock,
            rod_merge_block_diff=targets["rod_merge_block_diff"],
            notify_difficulty=targets["notify_difficulty"],
        )
        job.stone_block_target_hex = stone_block_target_hex
        job.rod_block_target_hex = rod_block_target_hex
        job.rod_share_target_hex = rod_share_target_hex
        self.remember_job(job)
        return job

    async def send_job(self, client: StratumClient, job: Job):
        _, coinb1, coinb2, prevhash = self.build_stratum_parts(
            job.auxblock["hash"], client.extranonce1
        )
        nbits = format(int(job.auxblock["bits"], 16), "08x")
        ntime = format(int(time.time()), "08x")
        if job.rod_merge_block_diff and job.notify_difficulty > 0:
            notify_diff = job.notify_difficulty
        else:
            notify_diff = client.share_difficulty
            if client.solo_mode:
                block_target_int = target_hex_to_int(job.auxblock["_target"])
                notify_diff = min(
                    float(notify_diff or 0.0),
                    target_to_difficulty(block_target_int),
                )
                if notify_diff <= 0:
                    notify_diff = target_to_difficulty(block_target_int)
        await client.send("mining.set_difficulty", [notify_diff])
        await client.send(
            "mining.notify",
            [
                job.job_id,
                prevhash,
                coinb1,
                coinb2,
                [],
                "01000000",
                nbits,
                ntime,
                True,
            ],
        )
        mode = "solo" if client.solo_mode else "pool"
        diff_note = (
            f" rod_merge_diff={job.notify_difficulty:.8f}"
            if job.rod_merge_block_diff
            else (" rod_aux=1" if job.rod_auxblock else "")
        )
        logging.info(
            "sha256d job %s height=%s address=%s mode=%s kind=%s diff=%.8f%s",
            job.job_id,
            job.auxblock["height"],
            client.address,
            mode,
            client.miner_kind,
            notify_diff,
            diff_note,
        )

    async def push_job(self, client: StratumClient):
        work_address = (
            client.address if client.solo_mode else self.pool_wallet
        )
        rod_payout = client.rod_address or self.resolve_rod_payout(client.address)
        job = await self.create_job(
            work_address,
            client.extranonce1,
            solo=client.solo_mode,
            share_difficulty=client.share_difficulty,
            rod_payout_address=rod_payout,
        )
        client.jobs[job.job_id] = job
        client.current_job_height = int(job.auxblock["height"])
        await self.send_job(client, job)

    async def handle_stale_submit(self, client: StratumClient, worker: str, job_id: str) -> None:
        logging.warning("stale job %s from %s", job_id, worker)
        if not client.address and worker:
            client.worker = worker
            client.address, _ = address_from_worker(worker)
        try:
            await self.push_job(client)
            logging.info("pushed fresh sha256d job to %s after stale %s", worker, job_id)
        except Exception as exc:
            logging.warning("stale job recovery failed for %s: %s", worker, exc)

    @staticmethod
    def _hex_str(value) -> str:
        if isinstance(value, bytes):
            return value.decode("ascii")
        return str(value)

    @staticmethod
    def _record_rod_share_event(
        client: StratumClient,
        worker: str,
        job: Job,
        *,
        accepted: bool,
        detail: str = "",
    ) -> None:
        if not job.rod_auxblock:
            return
        pool_db.record_dual_chain_event(
            chain="rod",
            event_type="share",
            status="accepted" if accepted else "rejected",
            stone_address=client.address or "",
            rod_address=client.rod_address or "",
            worker=worker,
            pool="sha256d",
            job_height=int(job.rod_auxblock.get("height") or job.auxblock.get("height") or 0),
            detail=detail,
        )

    async def handle_submit(self, client: StratumClient, params) -> bool:
        if len(params) < 5:
            logging.warning("submit with too few params: %s", params)
            return False
        worker = str(params[0]).strip()
        job_id, extranonce2, ntime_hex, nonce_hex = params[1:5]
        version_hex = params[5] if len(params) > 5 else "01000000"
        job_key = str(job_id).strip()
        job = client.jobs.get(job_key) or self.jobs_by_id.get(job_key)
        if job is None:
            await self.handle_stale_submit(client, worker, str(job_id))
            return False
        tx_bytes = bytearray(binascii.unhexlify(job.tx_template))
        insert_at = self._extranonce_offset(tx_bytes)
        en2 = binascii.unhexlify(str(extranonce2).zfill(8))
        if len(en2) != 4:
            logging.warning("bad extranonce2 from %s: %s", worker, extranonce2)
            return False
        tx_bytes[insert_at + 4 : insert_at + 8] = en2
        tx_hex = binascii.hexlify(tx_bytes).decode("ascii")

        # Standard stratum/Bitcoin header layout (matches Bitaxe ESP-Miner).
        version = 0x01000000 | int(str(version_hex), 16)
        header = bytearray(80)
        header[0:4] = struct.pack("<I", version)
        header[4:36] = b"\x00" * 32
        header[36:68] = double_sha256(binascii.unhexlify(tx_hex))
        header[68:72] = struct.pack("<I", int(str(ntime_hex), 16))
        header[72:76] = struct.pack("<I", int(job.auxblock["bits"], 16))
        header[76:80] = struct.pack("<I", int(str(nonce_hex), 16))
        header_hex = binascii.hexlify(header).decode()

        block_hash_hex = self._hex_str(auxpow.doubleHashHex(header_hex))
        if block_hash_hex > job.share_target_hex:
            logging.info(
                "rejected share from %s job=%s hash=%s target=%s ver=%08x",
                worker,
                job_id,
                block_hash_hex[:16],
                job.share_target_hex[:16],
                version,
            )
            pool_db.record_dual_chain_event(
                chain="stone",
                event_type="share",
                status="rejected",
                stone_address=client.address or "",
                rod_address=client.rod_address or "",
                worker=worker,
                pool="sha256d",
                job_height=int(job.auxblock.get("height") or 0),
            )
            self._record_rod_share_event(
                client,
                worker,
                job,
                accepted=False,
                detail="below pool share target",
            )
            return False

        logging.info(
            "accepted share from %s job=%s hash=%s diff_ok ver=%08x",
            worker,
            job_id,
            block_hash_hex[:16],
            version,
        )
        pool_db.record_dual_chain_event(
            chain="stone",
            event_type="share",
            status="accepted",
            stone_address=client.address or "",
            rod_address=client.rod_address or "",
            worker=worker,
            pool="sha256d",
            job_height=int(job.auxblock.get("height") or 0),
        )
        rod_share_ok = block_hash_hex <= getattr(
            job, "rod_share_target_hex", job.share_target_hex
        )
        self._record_rod_share_event(
            client,
            worker,
            job,
            accepted=rod_share_ok,
            detail="" if rod_share_ok else "below ROD share target",
        )

        if not client.solo_mode:
            peer = client.writer.get_extra_info("peername")
            peer_ip = peer[0] if peer else None
            share_weight = sha256_miner.share_work_weight(
                float(client.share_difficulty or 0.0)
            )
            try:
                pool_db.record_share(
                    "sha256d",
                    client.address,
                    worker,
                    int(job.auxblock["height"]),
                    weight=share_weight,
                    is_browser=False,
                    peer_ip=peer_ip,
                    miner_kind=client.miner_kind,
                )
            except Exception as exc:
                logging.warning("pool share record failed: %s", exc)
            try:
                await self.apply_pool_vardiff_on_share()
                await self.apply_client_vardiff_on_share(client)
            except Exception as exc:
                logging.warning("pool vardiff adjust failed: %s", exc)

        stone_block_ok = block_hash_hex <= getattr(
            job, "stone_block_target_hex", job.block_target_hex
        )
        rod_block_ok = bool(
            job.rod_auxblock
            and block_hash_hex
            <= getattr(job, "rod_block_target_hex", job.block_target_hex)
        )
        auxpow_hex = auxpow.finishAuxpow(tx_hex, header_hex.encode("ascii"))
        pool_block_found = False
        pool_block_bump_height = 0

        if stone_block_ok:
            block_hash = job.auxblock["hash"]
            if self._already_submitted(block_hash):
                logging.info(
                    "block %s already submitted, accepting share from %s",
                    block_hash,
                    worker,
                )
            else:
                async with self._submit_lock_get():
                    if not self._already_submitted(block_hash):
                        if await block_job_is_stale(
                            self.rpc, job.auxblock["height"]
                        ):
                            self._mark_submitted(block_hash)
                            logging.info(
                                "skip stale auxblock submit %s height=%s",
                                block_hash,
                                job.auxblock["height"],
                            )
                        else:
                            ready, net_reason = (
                                bloodstone_broadcast.ensure_network_ready()
                            )
                            if not ready:
                                logging.warning(
                                    "skip auxblock submit height=%s — network not ready: %s",
                                    job.auxblock["height"],
                                    net_reason,
                                )
                            else:
                                try:
                                    accepted = await self.rpc.call(
                                        "submitauxblock",
                                        [block_hash, auxpow_hex],
                                    )
                                except RuntimeError as exc:
                                    err = exc.args[0] if exc.args else {}
                                    if isinstance(err, dict):
                                        msg = err.get("message", "")
                                        if msg == "block hash unknown":
                                            self._mark_submitted(block_hash)
                                            logging.info(
                                                "block already accepted or stale %s from %s",
                                                block_hash,
                                                worker,
                                            )
                                            await self.refresh_all_jobs(
                                                f"stale block submit height={job.auxblock['height']}"
                                            )
                                            accepted = True
                                        elif err.get("code") == -28:
                                            logging.warning(
                                                "node busy during submitauxblock %s from %s: %s",
                                                block_hash,
                                                worker,
                                                msg,
                                            )
                                            accepted = False
                                        else:
                                            logging.error(
                                                "submitauxblock failed for %s from %s: %s",
                                                block_hash,
                                                worker,
                                                exc,
                                            )
                                            accepted = False
                                    else:
                                        logging.error(
                                            "submitauxblock failed for %s from %s: %s",
                                            block_hash,
                                            worker,
                                            exc,
                                        )
                                        accepted = False
                                except Exception as exc:
                                    logging.warning(
                                        "submitauxblock RPC error for %s from %s: %s",
                                        block_hash,
                                        worker,
                                        exc,
                                    )
                                    accepted = False
                                else:
                                    if accepted:
                                        self._mark_submitted(block_hash)
                                        height = int(job.auxblock["height"])
                                        logging.info(
                                            "BLOCK sha256d height=%s hash=%s worker=%s",
                                            height,
                                            block_hash,
                                            worker,
                                        )
                                        pool_db.record_dual_chain_event(
                                            chain="stone",
                                            event_type="block",
                                            status="accepted",
                                            stone_address=client.address or "",
                                            rod_address=client.rod_address or "",
                                            worker=worker,
                                            pool="sha256d",
                                            job_height=height,
                                            block_hash=block_hash,
                                        )
                                        try:
                                            finder_addr = client.address
                                            if not finder_addr and worker:
                                                finder_addr, _ = address_from_worker(
                                                    worker
                                                )
                                            dist = pool_db.distribute_block(
                                                "sha256d",
                                                height,
                                                block_hash,
                                                pool_fee_pct=self.pool_fee_pct,
                                                finder_address=finder_addr,
                                                finder_worker=worker,
                                            )
                                            logging.info(
                                                "pool payout round=%s miners=%s reward=%.4f STONE",
                                                dist.get("round_id"),
                                                dist.get("miners"),
                                                dist.get("reward_stone", 0),
                                            )
                                        except Exception as exc:
                                            logging.warning(
                                                "pool distribution failed: %s", exc
                                            )
                                        pool_block_found = True
                                        pool_block_bump_height = height
                                        await self.refresh_all_jobs(
                                            f"block found height={height}"
                                        )
                                    else:
                                        logging.warning(
                                            "submitauxblock rejected for %s from %s",
                                            block_hash,
                                            worker,
                                        )
                                        pool_db.record_dual_chain_event(
                                            chain="stone",
                                            event_type="block",
                                            status="rejected",
                                            stone_address=client.address or "",
                                            rod_address=client.rod_address or "",
                                            worker=worker,
                                            pool="sha256d",
                                            job_height=int(
                                                job.auxblock.get("height") or 0
                                            ),
                                            block_hash=block_hash,
                                        )

        if rod_block_ok and self.rod_rpc and job.rod_auxblock:
            rod_hash = str(job.rod_auxblock.get("hash") or "")
            rod_ok = False
            try:
                rod_ok = await rod_dual_submit.submit_rod_auxblock(
                    self.rod_rpc,
                    job.rod_auxblock,
                    header_hex,
                    job.extranonce1,
                    extranonce2,
                    submitted_cache=self._rod_submitted_blocks,
                )
            except Exception as exc:
                logging.warning("ROD dual-submit error: %s", exc)
            pool_db.record_dual_chain_event(
                chain="rod",
                event_type="block",
                status="accepted" if rod_ok else "rejected",
                stone_address=client.address or "",
                rod_address=client.rod_address or "",
                worker=worker,
                pool="sha256d",
                job_height=int(job.rod_auxblock.get("height") or 0),
                block_hash=rod_hash,
            )
            if rod_ok:
                if not pool_block_found:
                    pool_block_found = True
                    pool_block_bump_height = int(
                        job.rod_auxblock.get("height") or 0
                    )
                await self.refresh_all_jobs(
                    f"ROD block found height={job.rod_auxblock.get('height')}"
                )
        elif stone_block_ok and self.rod_rpc and not job.rod_auxblock:
            pool_db.record_dual_chain_event(
                chain="rod",
                event_type="block",
                status="skipped",
                stone_address=client.address or "",
                rod_address=client.rod_address or "",
                worker=worker,
                pool="sha256d",
                job_height=int(job.auxblock.get("height") or 0),
                detail="no ROD wallet linked",
            )
        if pool_block_found:
            try:
                await self.apply_client_block_vardiff(client)
                if not client.solo_mode:
                    await self.apply_pool_difficulty_bump(pool_block_bump_height)
            except Exception as exc:
                logging.warning("share difficulty bump failed: %s", exc)
        return True

    async def client_handler(self, reader, writer):
        client = StratumClient(reader, writer, self)
        self.clients.add(client)
        try:
            await client.handle()
        finally:
            self.clients.discard(client)

    async def run(self):
        server = await asyncio.start_server(self.client_handler, self.host, self.port)
        logging.info("Bloodstone SHA256D stratum on %s:%s", self.host, self.port)
        async with server:
            await asyncio.gather(
                server.serve_forever(),
                self.refresh_jobs_loop(),
                stratum_export_loop(self.clients, "sha256d"),
                stratum_mobile_contrib_loop(
                    self.clients, "sha256d", subsidy_algo="yespower"
                ),
            )


def main():
    parser = argparse.ArgumentParser(description="Bloodstone SHA256D stratum server")
    parser.add_argument(
        "--rpc-url",
        default="http://bloodstone:a250b99cd8798d396087d0cbd87ab1721cb6f9ba53f6ba06adf77074e6886aff@127.0.0.1:18332/",
    )
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=3429)
    parser.add_argument("--share-difficulty", type=float, default=0.01)
    parser.add_argument(
        "--rod-rpc-url",
        default=rod_dual_submit.DEFAULT_ROD_RPC,
        help="ROD mainnet RPC for dual AuxPoW submission (empty disables)",
    )
    parser.add_argument(
        "--rod-pool-wallet",
        default=rod_dual_submit.ROD_POOL_WALLET,
        help="ROD payout address for dual-submitted merge-mined blocks",
    )
    parser.add_argument(
        "--no-rod-dual-submit",
        action="store_true",
        help="Disable submitting found blocks to ROD mainnet",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    pool_db.init_db()
    try:
        import pool_bitaxe as pbx

        pbx.start_poller()
    except Exception as exc:
        logging.warning("bitaxe poller unavailable: %s", exc)
    rod_dual = (
        rod_dual_submit.ROD_DUAL_ENABLED
        and not args.no_rod_dual_submit
        and bool((args.rod_rpc_url or "").strip())
    )
    logging.info(
        "sha256d proportional pool wallet=%s fee=%.2f%% share_diff=%s rod_dual=%s",
        POOL_WALLET,
        POOL_FEE_PCT,
        args.share_difficulty,
        rod_dual,
    )
    if rod_dual:
        if (args.rod_pool_wallet or "").strip():
            logging.info("ROD dual-submit pool fallback wallet=%s", args.rod_pool_wallet)
        else:
            logging.info(
                "ROD dual-submit uses per-miner ROD wallets from /mining/ registration"
            )

    runtime_share_diff = sha256_miner.load_runtime_share_difficulty(args.share_difficulty)
    if abs(runtime_share_diff - float(args.share_difficulty)) > 1e-12:
        logging.info(
            "sha256d runtime share_difficulty=%.8f (configured base=%.8f)",
            runtime_share_diff,
            args.share_difficulty,
        )

    server = StratumServer(
        args.rpc_url,
        args.host,
        args.port,
        runtime_share_diff,
        rod_rpc_url=args.rod_rpc_url if rod_dual else "",
        rod_pool_wallet=(args.rod_pool_wallet or "").strip() if rod_dual else "",
        rod_dual_submit=rod_dual,
    )
    asyncio.run(server.run())


if __name__ == "__main__":
    main()