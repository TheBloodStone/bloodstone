#!/usr/bin/env python3
"""SpaceXpanse ROD mainnet neoscrypt-xaya stratum (browser + CPU miners)."""

import argparse
import asyncio
import binascii
import hashlib
import json
import logging
import os
import struct
import subprocess
import sys
import time
from typing import Dict, Optional, Tuple

sys.path.insert(0, "/root")
from stratum_utils import (  # noqa: E402
    block_job_is_stale,
    extranonce_bytes,
    resolve_share_header,
    share_target_int,
    stratum_word_from_hex,
)
from stratum_worker_status import stratum_export_loop  # noqa: E402
from stratum_extensions import (  # noqa: E402
    handle_client_get_version,
    handle_configure,
    handle_mining_ping,
)
import pool_browser_miner  # noqa: E402
import pool_db  # noqa: E402
import rod_dual_submit  # noqa: E402

SPACEXPANSE_HASH = "/root/bloodstone-core/src/spacexpanse-hash"
DIFF1_TARGET = 0x00000000FFFF0000000000000000000000000000000000000000000000000000
# ccminer xaya/neoscrypt uses job.diff / 65536 for the actual target.
CCMINER_NEOSCRYPT_DIFF_SCALE = 65536.0
POOL_WALLET = os.environ.get("BLOODSTONE_ROD_POOL_WALLET", "").strip()
DEFAULT_ROD_RPC = rod_dual_submit.DEFAULT_ROD_RPC
ROD_BROWSER_DIFF = float(
    os.environ.get("BLOODSTONE_ROD_NEOSCRYPT_BROWSER_SHARE_DIFFICULTY", "1e-6")
)


def rod_address_from_worker(user: str) -> Tuple[str, bool]:
    raw = (user or "").strip()
    explicit = raw.split(".")[0].strip() if raw else ""
    if explicit and rod_dual_submit.is_plausible_rod_address(explicit):
        return explicit, False
    if POOL_WALLET and rod_dual_submit.is_plausible_rod_address(POOL_WALLET):
        return POOL_WALLET, True
    return "", True


def normalize_rod_work(work: dict) -> dict:
    out = dict(work)
    if "header" not in out or not out.get("header"):
        data = str(out.get("data") or "")
        if len(data) >= 152:
            out["header"] = data[:152]
        elif data:
            out["header"] = data
    if "target" not in out and out.get("_target"):
        out["target"] = out["_target"]
    return out


def swap_getwork(data: bytearray) -> None:
    for i in range(0, len(data), 4):
        data[i], data[i + 3] = data[i + 3], data[i]
        data[i + 1], data[i + 2] = data[i + 2], data[i + 1]


def reverse_hex_bytes(hex_str: str) -> str:
    return binascii.hexlify(binascii.unhexlify(hex_str)[::-1]).decode()


def target_hex_to_int(target_hex: str) -> int:
    raw = binascii.unhexlify(target_hex)
    return int.from_bytes(raw[::-1], "big")


def int_to_compare_hex(value: int) -> str:
    mem = value.to_bytes(32, byteorder="little", signed=False)
    return reverse_hex_bytes(binascii.hexlify(mem).decode())


def target_to_difficulty(target: int) -> float:
    if target <= 0:
        return 1.0
    return DIFF1_TARGET / target


def double_sha256(data: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()


def flip32_words(data: bytes) -> bytes:
    """Byte-swap each 4-byte word (sgminer flip32)."""
    words = struct.unpack("<8I", data[:32])
    return struct.pack("<8I", *[struct.unpack(">I", struct.pack("<I", w))[0] for w in words])


def block_hash_from_header(header_bytes: bytes) -> str:
    return double_sha256(header_bytes)[::-1].hex()


def neoscrypt_hash_compare_hex(mining_header_bytes: bytes) -> str:
    """Return neoscrypt PoW hash (uint256 display hex) for a mining work buffer."""
    # spacexpanse-hash decodes a normal serialised header and applies the
    # getwork byte-swap inside GetPowHash — do not pre-swap here.
    hex_str = binascii.hexlify(mining_header_bytes).decode()
    proc = subprocess.run(
        [SPACEXPANSE_HASH, "neoscrypt", hex_str],
        capture_output=True,
        check=True,
    )
    return proc.stdout.decode().strip()


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
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._call_sync, method, params)


class Job:
    def __init__(self, job_id: str, work: dict, extranonce1: str):
        self.job_id = job_id
        self.short_id = job_id
        self.work = work
        if "header" not in work:
            raise RuntimeError("creatework missing header/data field")
        self.header_prefix = work["header"]
        self.block_hash = work["hash"]
        self.extranonce1 = extranonce1
        self.block_target_hex = int_to_compare_hex(target_hex_to_int(work["target"]))
        self.share_target_hex = self.block_target_hex
        self.pow_bits = work["bits"]


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
        self.subscribed = False
        self.authorized = False
        self.solo_mode = False
        self.user_agent = ""
        self.is_web_miner = False
        self.share_difficulty = 0.0
        self.jobs: Dict[str, Job] = {}
        self.current_job_height = 0
        self.configured = False
        self.version_mask = "1fffe000"

    async def send(self, method: str, params, msg_id=None):
        payload = {"id": msg_id, "method": method, "params": params}
        self.writer.write((json.dumps(payload) + "\n").encode())
        await self.writer.drain()

    async def reply(self, msg_id, result=None, error=None):
        payload = {"id": msg_id, "result": result, "error": error}
        self.writer.write((json.dumps(payload) + "\n").encode())
        await self.writer.drain()

    async def handle(self):
        peer = self.writer.get_extra_info("peername")
        logging.info("connection from %s", peer)
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
            logging.info("disconnect %s worker=%s", peer, self.worker or "-")
            self.writer.close()
            await self.writer.wait_closed()

    async def dispatch(self, msg):
        msg_id = msg.get("id")
        method = msg.get("method")
        params = msg.get("params", [])

        if method == "mining.subscribe":
            self.subscribed = True
            self.user_agent = str(params[0]).strip() if params else ""
            self.is_web_miner = self.user_agent == "bloodstone-web-miner"
            if self.is_web_miner:
                self.share_difficulty = min(
                    self.server.share_difficulty,
                    ROD_BROWSER_DIFF,
                )
            else:
                self.share_difficulty = self.server.share_difficulty
            # 2 bytes in nNonce for extranonce1 per SpaceXpanse stratum spec.
            self.extranonce1 = binascii.hexlify(os.urandom(2)).decode("ascii")
            await self.reply(
                msg_id,
                [
                    [
                        ["mining.set_difficulty", "bloodstone"],
                        ["mining.notify", "bloodstone"],
                    ],
                    self.extranonce1,
                    2,
                ],
            )
            return

        if method == "mining.authorize":
            user = params[0] if params else ""
            password = params[1] if len(params) > 1 else ""
            self.solo_mode = str(password).strip().lower() == "solo"
            self.worker = user
            self.address, fallback = rod_address_from_worker(user)
            if not self.address:
                await self.reply(
                    msg_id,
                    False,
                    [24, "set a ROD core wallet address on /mining/", None],
                )
                return
            try:
                work_address = (
                    self.address
                    if self.solo_mode or not self.server.pool_wallet
                    else self.server.pool_wallet
                )
                job = await self.server.create_job(
                    work_address, self.extranonce1, solo=self.solo_mode
                )
                self.jobs[job.short_id] = job
                self.jobs[job.job_id] = job
            except Exception as exc:
                logging.warning(
                    "authorize failed for %s (payout %s): %s",
                    user,
                    self.address,
                    exc,
                )
                await self.reply(msg_id, False, [24, "cannot create work", None])
                return
            self.authorized = True
            if fallback:
                logging.info(
                    "using default payout %s for worker %r",
                    self.address,
                    user,
                )
            await self.reply(msg_id, True, None)
            await self.server.send_job(self, job)
            return

        if method == "mining.submit":
            if not self.authorized:
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
            if (
                suggested is not None
                and self.is_web_miner
                and not self.solo_mode
            ):
                self.share_difficulty = pool_browser_miner.clamp_suggested_difficulty(
                    "neoscrypt",
                    float(suggested),
                    self.server.share_difficulty,
                )
                try:
                    await self.server.push_job(self)
                except Exception as exc:
                    logging.warning(
                        "browser vardiff refresh failed for %s: %s",
                        self.worker or self.address,
                        exc,
                    )
            await self.reply(msg_id, True, None)
            return

        if msg_id is not None:
            await self.reply(msg_id, None, None)


class StratumServer:
    def __init__(self, rpc_url: str, host: str, port: int, share_difficulty: float):
        self.rpc_url = rpc_url
        self.host = host
        self.port = port
        self.share_difficulty = share_difficulty
        self.pool_wallet = POOL_WALLET
        self.rpc = RpcClient(rpc_url)
        self.clients = set()
        self.job_counter = 0
        self.jobs_by_id: Dict[str, Job] = {}
        self.tip_height = -1
        self.job_refresh_interval = 1.0
        self._refresh_lock: Optional[asyncio.Lock] = None

    def _refresh_lock_get(self) -> asyncio.Lock:
        if self._refresh_lock is None:
            self._refresh_lock = asyncio.Lock()
        return self._refresh_lock

    def remember_job(self, job: Job) -> None:
        self.jobs_by_id[job.job_id] = job
        self.jobs_by_id[job.short_id] = job
        if len(self.jobs_by_id) > 512:
            oldest = sorted(self.jobs_by_id)[:128]
            for job_id in oldest:
                self.jobs_by_id.pop(job_id, None)

    async def refresh_all_jobs(self, reason: str) -> None:
        clients = [c for c in list(self.clients) if c.authorized and c.address]
        if not clients:
            return
        async with self._refresh_lock_get():
            logging.info(
                "refreshing neoscrypt jobs for %d client(s): %s",
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

    async def refresh_jobs_loop(self) -> None:
        while True:
            try:
                tip = int(await self.rpc.call("getblockcount"))
                if self.tip_height < 0:
                    self.tip_height = tip
                elif tip != self.tip_height:
                    old_tip = self.tip_height
                    self.tip_height = tip
                    await self.refresh_all_jobs(f"chain tip {old_tip} -> {tip}")
                else:
                    next_h = tip + 1
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
                logging.warning("neoscrypt job refresh poll failed: %s", exc)
            await asyncio.sleep(self.job_refresh_interval)

    async def _rod_ready(self) -> Tuple[bool, str]:
        try:
            info = await self.rpc.call("getblockchaininfo")
        except Exception as exc:
            return False, f"ROD RPC unavailable: {exc}"
        return rod_dual_submit.rod_chain_ready(info)

    async def create_job(
        self, address: str, extranonce1: str, solo: bool = False
    ) -> Job:
        if not address or not rod_dual_submit.is_plausible_rod_address(address):
            raise RuntimeError("valid ROD payout address required")
        ready, reason = await self._rod_ready()
        if not ready:
            raise RuntimeError(f"ROD node not ready: {reason}")
        work = normalize_rod_work(await self.rpc.call("creatework", [address]))
        if work.get("algo") not in (None, "neoscrypt"):
            raise RuntimeError(f"expected neoscrypt work, got {work.get('algo')}")
        if "header" not in work:
            raise RuntimeError("creatework missing header/data from ROD node")
        self.job_counter += 1
        short_id = f"{work['height']:x}.{self.job_counter:x}"
        # ccminer submits job_id + 8, skipping an 8-char prefix.
        job_id = f"00000000{short_id}"
        job = Job(job_id, work, extranonce1)
        job.short_id = short_id
        block_target_int = target_hex_to_int(work["target"])
        share_target = share_target_int(
            block_target_int, self.share_difficulty, solo=solo
        )
        job.share_target_hex = int_to_compare_hex(share_target)
        self.remember_job(job)
        return job

    def client_share_difficulty(self, client: StratumClient) -> float:
        return pool_browser_miner.effective_share_difficulty(
            "neoscrypt",
            self.share_difficulty,
            is_web_miner=bool(client.is_web_miner),
            solo_mode=bool(client.solo_mode),
            client_diff=float(client.share_difficulty or 0.0),
        )

    async def send_job(self, client: StratumClient, job: Job):
        nbits = job.pow_bits
        ntime = format(int(time.time()), "08x")
        block_target_int = target_hex_to_int(job.work["target"])
        share_diff = self.client_share_difficulty(client)
        share_target_int_val = share_target_int(
            block_target_int, share_diff, solo=client.solo_mode
        )
        share_target_hex = int_to_compare_hex(share_target_int_val)
        job.share_target_hex = share_target_hex
        stratum_diff = target_to_difficulty(share_target_int_val) * CCMINER_NEOSCRYPT_DIFF_SCALE
        await client.send("mining.set_share_target", [share_target_hex])
        await client.send("mining.set_difficulty", [stratum_diff])
        difficulty = stratum_diff / CCMINER_NEOSCRYPT_DIFF_SCALE
        client.jobs[job.job_id] = job
        client.jobs[job.short_id] = job
        self.remember_job(job)
        await client.send(
            "mining.notify",
            [
                job.job_id,
                "0000000000000000000000000000000000000000000000000000000000000000",
                job.header_prefix,
                "",
                [],
                "00000000",
                nbits,
                ntime,
                True,
            ],
        )
        await client.send(
            "mining.set_block_target",
            [job.block_target_hex, str(job.work["height"])],
        )
        mode = "solo" if client.solo_mode else "pool"
        browser_note = " browser" if client.is_web_miner else ""
        logging.info(
            "ROD neoscrypt job %s height=%s address=%s mode=%s diff=%.6f%s",
            job.job_id,
            job.work["height"],
            client.address,
            mode,
            difficulty,
            browser_note,
        )

    async def push_job(self, client: StratumClient):
        work_address = (
            client.address
            if client.solo_mode or not self.pool_wallet
            else self.pool_wallet
        )
        if not work_address:
            raise RuntimeError("ROD payout address required")
        job = await self.create_job(
            work_address, client.extranonce1, solo=client.solo_mode
        )
        client.jobs[job.short_id] = job
        client.jobs[job.job_id] = job
        client.current_job_height = int(job.work["height"])
        await self.send_job(client, job)

    async def handle_stale_submit(self, client: StratumClient, worker: str, job_id: str) -> None:
        logging.warning("stale job %s from %s", job_id, worker)
        try:
            await self.push_job(client)
            logging.info(
                "pushed fresh neoscrypt job to %s after stale %s",
                worker,
                job_id,
            )
        except Exception as exc:
            logging.warning("stale job recovery failed for %s: %s", worker, exc)

    def build_fake_header(
        self,
        job: Job,
        extranonce2: str,
        ntime_hex: str,
        nonce_hex: str,
        nonce_big_endian: bool = True,
        merkle_flip32: bool = False,
    ) -> bytes:
        en1 = extranonce_bytes(job.extranonce1, 2)
        en2 = extranonce_bytes(extranonce2, 2)
        real_header = binascii.unhexlify(job.header_prefix) + en1 + en2

        fake = bytearray(80)
        struct.pack_into("<I", fake, 0, 0)
        struct.pack_into("<I", fake, 68, stratum_word_from_hex(str(ntime_hex)))
        struct.pack_into("<I", fake, 72, stratum_word_from_hex(str(job.pow_bits)))
        nonce_raw = binascii.unhexlify(str(nonce_hex).zfill(8))
        if nonce_big_endian:
            struct.pack_into("<I", fake, 76, int.from_bytes(nonce_raw, "big"))
        else:
            fake[76:80] = nonce_raw[-4:]
        merkle = double_sha256(real_header)
        if merkle_flip32:
            merkle = flip32_words(merkle)
        fake[36:68] = merkle
        return bytes(fake)

    @staticmethod
    def nonce_submit_is_big_endian(worker: str) -> bool:
        # neoscrypt-xaya / ccminer forks submit the nonce as raw LE bytes.
        # Legacy sgminer used big-endian nonce words; try both in handle_submit.
        return False

    def to_submit_data(self, fake_header: bytes) -> str:
        data = bytearray(fake_header)
        swap_getwork(data)
        return binascii.hexlify(data).decode()

    async def notify_block_result(
        self,
        client: StratumClient,
        accepted: bool,
        height: int,
        block_hash: str,
        reason: str,
    ) -> None:
        await client.send(
            "mining.block_result",
            [
                {
                    "accepted": accepted,
                    "height": height,
                    "hash": block_hash,
                    "reason": reason,
                }
            ],
        )

    async def handle_submit(self, client: StratumClient, params) -> bool:
        if len(params) < 5:
            logging.warning("submit with too few params: %s", params)
            return False
        worker = str(params[0]).strip()
        job_id = str(params[1]).strip()
        extranonce2, ntime_hex, nonce_hex = params[2:5]
        expected_hash = str(params[5]).strip() if len(params) > 5 else None
        job_key = str(job_id).strip()
        job = client.jobs.get(job_key)
        if job is None and not job_key.startswith("00000000"):
            job = client.jobs.get(f"00000000{job_key}")
        if job is None:
            job = self.jobs_by_id.get(job_key) or self.jobs_by_id.get(
                f"00000000{job_key}"
            )
        if job is None:
            await self.handle_stale_submit(client, worker, job_key)
            return False

        try:
            resolved = resolve_share_header(
                self.build_fake_header,
                neoscrypt_hash_compare_hex,
                job,
                extranonce2,
                str(ntime_hex),
                str(nonce_hex),
                job.share_target_hex,
                expected_hash=expected_hash,
                preferred_nonce_be=True,
            )
        except (ValueError, binascii.Error) as exc:
            logging.warning("invalid submit from %s: %s", worker, exc)
            return False
        except (FileNotFoundError, subprocess.CalledProcessError, OSError) as exc:
            logging.error("share validation failed for %s: %s", worker, exc)
            return False

        stone_address = ""
        rod_address = str(getattr(client, "address", "") or "").strip()
        if rod_address:
            try:
                stone_address = pool_db.get_stone_wallet_for_rod(rod_address) or ""
            except Exception:
                stone_address = ""

        if resolved is None:
            logging.info(
                "rejected share from %s job=%s en2=%s ntime=%s nonce=%s",
                worker,
                job_id,
                extranonce2,
                ntime_hex,
                nonce_hex,
            )
            pool_db.record_dual_chain_event(
                chain="rod",
                event_type="share",
                status="rejected",
                stone_address=stone_address,
                rod_address=rod_address,
                worker=worker,
                pool="rod_neoscrypt",
                job_height=int(job.work.get("height") or 0),
            )
            return False

        fake_header, hash_hex = resolved

        logging.info(
            "accepted share from %s job=%s hash=%s",
            worker,
            job_id,
            hash_hex[:16],
        )
        pool_db.record_dual_chain_event(
            chain="rod",
            event_type="share",
            status="accepted",
            stone_address=stone_address,
            rod_address=rod_address,
            worker=worker,
            pool="rod_neoscrypt",
            job_height=int(job.work.get("height") or 0),
        )

        if int(hash_hex, 16) <= int(job.block_target_hex, 16):
            height = int(job.work["height"])
            if await block_job_is_stale(self.rpc, height):
                logging.info(
                    "skip stale block submit %s height=%s",
                    job.block_hash,
                    height,
                )
                await self.notify_block_result(
                    client, False, height, job.block_hash, "stale"
                )
                return True
            rod_ready, rod_reason = await self._rod_ready()
            if not rod_ready:
                logging.warning(
                    "skip ROD block submit height=%s — %s",
                    height,
                    rod_reason,
                )
                await self.notify_block_result(
                    client, False, height, job.block_hash, "rod-not-ready"
                )
                return True
            submit_data = self.to_submit_data(fake_header)
            try:
                accepted = await self.rpc.call(
                    "submitwork",
                    [job.block_hash, submit_data],
                )
            except RuntimeError as exc:
                logging.warning(
                    "submitwork failed for %s height=%s: %s",
                    job.block_hash,
                    height,
                    exc,
                )
                accepted = False
            if accepted:
                logging.info(
                    "ROD BLOCK neoscrypt height=%s hash=%s worker=%s payout=%s",
                    height,
                    job.block_hash,
                    worker,
                    client.address,
                )
                pool_db.record_dual_chain_event(
                    chain="rod",
                    event_type="block",
                    status="accepted",
                    stone_address=stone_address,
                    rod_address=rod_address,
                    worker=worker,
                    pool="rod_neoscrypt",
                    job_height=height,
                    block_hash=job.block_hash,
                )
                await self.notify_block_result(
                    client, True, height, job.block_hash, "accepted"
                )
                await self.refresh_all_jobs(f"block found height={height}")
            else:
                logging.warning(
                    "block solution not submitted for %s (stale template or node reject)",
                    job.block_hash,
                )
                pool_db.record_dual_chain_event(
                    chain="rod",
                    event_type="block",
                    status="rejected",
                    stone_address=stone_address,
                    rod_address=rod_address,
                    worker=worker,
                    pool="rod_neoscrypt",
                    job_height=height,
                    block_hash=job.block_hash,
                )
                await self.notify_block_result(
                    client, False, height, job.block_hash, "rejected"
                )
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
        logging.info(
            "SpaceXpanse ROD neoscrypt stratum on %s:%s", self.host, self.port
        )
        async with server:
            await asyncio.gather(
                server.serve_forever(),
                self.refresh_jobs_loop(),
                stratum_export_loop(self.clients, "rod_neoscrypt"),
            )


def main():
    parser = argparse.ArgumentParser(
        description="SpaceXpanse ROD mainnet neoscrypt stratum server"
    )
    parser.add_argument("--rpc-url", default=DEFAULT_ROD_RPC)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=3440)
    parser.add_argument("--share-difficulty", type=float, default=1e-6)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    if not os.path.isfile(SPACEXPANSE_HASH) or not os.access(SPACEXPANSE_HASH, os.X_OK):
        logging.error(
            "missing spacexpanse-hash at %s — run /root/build-spacexpanse-hash.sh",
            SPACEXPANSE_HASH,
        )
        sys.exit(1)

    pool_db.init_db()
    logging.info(
        "ROD neoscrypt stratum fallback_wallet=%s share_diff=%s",
        POOL_WALLET or "(per-miner ROD address required)",
        args.share_difficulty,
    )

    server = StratumServer(args.rpc_url, args.host, args.port, args.share_difficulty)
    asyncio.run(server.run())


if __name__ == "__main__":
    main()