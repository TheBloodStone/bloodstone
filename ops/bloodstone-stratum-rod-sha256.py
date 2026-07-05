#!/usr/bin/env python3
"""ROD-primary SHA256D stratum: jobs from ROD node, optional STONE dual-submit."""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import logging
import os
import sys
from typing import Optional, Tuple

import bloodstone_broadcast  # noqa: E402
import pool_db  # noqa: E402
import rod_dual_submit  # noqa: E402
from stratum_utils import BECH32_ADDR, LEGACY_ADDR  # noqa: E402

POOL_WALLET = rod_dual_submit.ROD_SHA256_POOL_WALLET

_SPEC = importlib.util.spec_from_file_location(
    "bloodstone_stratum_sha256",
    "/root/bloodstone-stratum-sha256.py",
)
_base = importlib.util.module_from_spec(_SPEC)
sys.modules["bloodstone_stratum_sha256"] = _base
_SPEC.loader.exec_module(_base)


def _explicit_worker_address(user: str) -> str:
    raw = (user or "").strip()
    return raw.split(".")[0].strip() if raw else ""


def _is_stone_address(address: str) -> bool:
    addr = str(address or "").strip()
    return bool(addr and (LEGACY_ADDR.match(addr) or BECH32_ADDR.match(addr)))


def miner_payout_from_worker(user: str) -> Tuple[str, str, bool]:
    """Return (rod_job_address, stone_share_address, used_fallback)."""
    explicit = _explicit_worker_address(user)
    pool_rod = POOL_WALLET

    if explicit and rod_dual_submit.is_plausible_rod_address(explicit):
        stone = pool_db.get_stone_wallet_for_rod(explicit) or ""
        return explicit, stone, False

    if explicit and _is_stone_address(explicit):
        linked_rod = pool_db.get_miner_rod_wallet(explicit) or ""
        if linked_rod and rod_dual_submit.is_plausible_rod_address(linked_rod):
            return linked_rod, explicit, False
        if pool_rod and rod_dual_submit.is_plausible_rod_address(pool_rod):
            return pool_rod, explicit, True
        return "", explicit, True

    if pool_rod and rod_dual_submit.is_plausible_rod_address(pool_rod):
        return pool_rod, "", True
    return "", "", True


class RodPrimaryStratumClient(_base.StratumClient):
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
            rod_job, stone_share, fallback = miner_payout_from_worker(user)
            if not rod_job:
                logging.warning(
                    "authorize rejected for %r: use ROD wallet (X…/R…), linked STONE "
                    "wallet, or configure BLOODSTONE_ROD_SHA256_POOL_WALLET",
                    user,
                )
                return False
            self.rod_address = rod_job
            self.stone_address = stone_share
            self.address = stone_share or rod_job
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
                    "authorized %s rod_job=%s stone_share=%s (pool fallback)",
                    user,
                    rod_job,
                    stone_share or "-",
                )
            else:
                logging.info(
                    "authorized %s rod_job=%s stone_share=%s kind=%s diff=%.8f (peer=%s)",
                    user,
                    rod_job,
                    stone_share or "-",
                    self.miner_kind,
                    self.share_difficulty,
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

    async def dispatch(self, msg):
        msg_id = msg.get("id")
        method = msg.get("method")
        params = msg.get("params", [])
        if method == "mining.subscribe":
            self.user_agent = str(params[0]).strip() if params else ""
            self.miner_kind = _base.sha256_miner.classify_miner(
                self.user_agent, self.worker
            )
            self.share_difficulty = _base.sha256_miner.default_share_difficulty(
                self.miner_kind, self.server.share_difficulty
            )
            import binascii

            self.extranonce1 = binascii.hexlify(os.urandom(4)).decode("ascii")
            await self.reply(
                msg_id,
                [
                    [
                        ["mining.set_difficulty", "bloodstone-rod-sha256"],
                        ["mining.notify", "bloodstone-rod-sha256"],
                    ],
                    self.extranonce1,
                    4,
                ],
            )
            return
        await super().dispatch(msg)


class RodPrimaryStratumServer(_base.StratumServer):
    def __init__(
        self,
        rod_rpc_url: str,
        stone_rpc_url: str,
        host: str,
        port: int,
        share_difficulty: float,
        stone_pool_wallet: str = "",
        stone_dual_submit: bool = True,
    ):
        super().__init__(
            rod_rpc_url,
            host,
            port,
            share_difficulty,
            rod_rpc_url="",
            rod_pool_wallet="",
            rod_dual_submit=False,
        )
        self.pool_wallet = POOL_WALLET
        self.stone_dual_submit = bool(stone_dual_submit)
        self.stone_pool_wallet = (stone_pool_wallet or "").strip()
        self.stone_rpc = (
            _base.RpcClient(stone_rpc_url)
            if stone_rpc_url and self.stone_dual_submit
            else None
        )
        self._stone_submitted_blocks: dict = {}

    def resolve_stone_share_address(self, client) -> str:
        stone = str(getattr(client, "stone_address", "") or "").strip()
        if _is_stone_address(stone):
            return stone
        rod = str(getattr(client, "rod_address", "") or client.address or "").strip()
        if rod == self.pool_wallet and self.stone_pool_wallet:
            return self.stone_pool_wallet
        linked = pool_db.get_stone_wallet_for_rod(rod)
        return linked or ""

    def resolve_stone_finder_address(self, client, worker: str) -> str:
        stone = self.resolve_stone_share_address(client)
        if stone:
            return stone
        rod, stone_share, _ = miner_payout_from_worker(worker)
        return stone_share if _is_stone_address(stone_share) else ""

    async def create_job(
        self,
        address: str,
        extranonce1: str,
        solo: bool = False,
        share_difficulty: Optional[float] = None,
        rod_payout_address: Optional[str] = None,
        stone_payout_address: Optional[str] = None,
    ) -> _base.Job:
        del rod_payout_address
        job = await super().create_job(
            address,
            extranonce1,
            solo=solo,
            share_difficulty=share_difficulty,
            rod_payout_address=None,
        )
        stone_wallet = (stone_payout_address or "").strip() or self.stone_pool_wallet
        stone_auxblock = None
        if self.stone_rpc and stone_wallet:
            stone_auxblock = await rod_dual_submit.fetch_stone_auxblock(
                self.stone_rpc,
                stone_wallet,
            )
            if stone_auxblock:
                pool_db.record_dual_chain_event(
                    chain="stone",
                    event_type="job",
                    status="accepted",
                    stone_address=stone_wallet,
                    rod_address=address,
                    pool="rod_sha256d",
                    job_height=int(stone_auxblock.get("height") or 0),
                    block_hash=str(stone_auxblock.get("hash") or ""),
                    detail="stone auxblock ready",
                )
        job.rod_auxblock = stone_auxblock
        return job

    async def push_job(self, client: RodPrimaryStratumClient):
        work_address = (
            (client.rod_address or client.address) if client.solo_mode else self.pool_wallet
        )
        if not work_address:
            raise RuntimeError("ROD payout address required")
        stone_payout = self.resolve_stone_share_address(client) or self.stone_pool_wallet
        job = await self.create_job(
            work_address,
            client.extranonce1,
            solo=client.solo_mode,
            share_difficulty=client.share_difficulty,
            stone_payout_address=stone_payout,
        )
        client.jobs[job.job_id] = job
        client.current_job_height = int(job.auxblock["height"])
        await self.send_job(client, job)

    async def handle_submit(self, client, params) -> bool:
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

        import binascii
        import struct

        tx_bytes = bytearray(binascii.unhexlify(job.tx_template))
        insert_at = self._extranonce_offset(tx_bytes)
        en2 = binascii.unhexlify(str(extranonce2).zfill(8))
        if len(en2) != 4:
            logging.warning("bad extranonce2 from %s: %s", worker, extranonce2)
            return False
        tx_bytes[insert_at + 4 : insert_at + 8] = en2
        tx_hex = binascii.hexlify(tx_bytes).decode("ascii")

        version = 0x01000000 | int(str(version_hex), 16)
        header = bytearray(80)
        header[0:4] = struct.pack("<I", version)
        header[4:36] = b"\x00" * 32
        header[36:68] = _base.double_sha256(binascii.unhexlify(tx_hex))
        header[68:72] = struct.pack("<I", int(str(ntime_hex), 16))
        header[72:76] = struct.pack("<I", int(job.auxblock["bits"], 16))
        header[76:80] = struct.pack("<I", int(str(nonce_hex), 16))
        header_hex = binascii.hexlify(header).decode()

        block_hash_hex = self._hex_str(_base.auxpow.doubleHashHex(header_hex))
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
                chain="rod",
                event_type="share",
                status="rejected",
                stone_address=self.resolve_stone_share_address(client) or "",
                rod_address=getattr(client, "rod_address", None) or client.address or "",
                worker=worker,
                pool="rod_sha256d",
                job_height=int(job.auxblock.get("height") or 0),
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
            chain="rod",
            event_type="share",
            status="accepted",
            stone_address=self.resolve_stone_share_address(client) or "",
            rod_address=getattr(client, "rod_address", None) or client.address or "",
            worker=worker,
            pool="rod_sha256d",
            job_height=int(job.auxblock.get("height") or 0),
        )

        if not client.solo_mode:
            share_address = self.resolve_stone_share_address(client)
            if share_address:
                peer = client.writer.get_extra_info("peername")
                peer_ip = peer[0] if peer else None
                share_weight = _base.sha256_miner.share_work_weight(
                    client.share_difficulty
                )
                try:
                    pool_db.record_share(
                        "sha256d",
                        share_address,
                        worker,
                        int(job.auxblock["height"]),
                        weight=share_weight,
                        is_browser=False,
                        peer_ip=peer_ip,
                        miner_kind=client.miner_kind,
                    )
                    pool_db.record_dual_chain_event(
                        chain="stone",
                        event_type="share",
                        status="accepted",
                        stone_address=share_address,
                        rod_address=getattr(client, "rod_address", None) or client.address or "",
                        worker=worker,
                        pool="rod_sha256d",
                        job_height=int(job.auxblock.get("height") or 0),
                    )
                except Exception as exc:
                    logging.warning("pool share record failed: %s", exc)

        if block_hash_hex <= job.block_target_hex:
            block_hash = job.auxblock["hash"]
            if self._already_submitted(block_hash):
                return True
            auxpow_hex = _base.auxpow.finishAuxpow(tx_hex, header_hex.encode("ascii"))
            async with self._submit_lock_get():
                if self._already_submitted(block_hash):
                    return True
                if await _base.block_job_is_stale(self.rpc, job.auxblock["height"]):
                    self._mark_submitted(block_hash)
                    logging.info(
                        "skip stale ROD auxblock submit %s height=%s",
                        block_hash,
                        job.auxblock["height"],
                    )
                    return True
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
                            await self.refresh_all_jobs(
                                f"stale ROD block submit height={job.auxblock['height']}"
                            )
                            return True
                        if err.get("code") == -28:
                            logging.warning(
                                "ROD node busy during submitauxblock %s: %s",
                                block_hash,
                                msg,
                            )
                            return True
                    logging.error(
                        "ROD submitauxblock failed for %s from %s: %s",
                        block_hash,
                        worker,
                        exc,
                    )
                    return True
                except Exception as exc:
                    logging.warning(
                        "ROD submitauxblock RPC error for %s from %s: %s",
                        block_hash,
                        worker,
                        exc,
                    )
                    return True
                if accepted:
                    self._mark_submitted(block_hash)
                    height = int(job.auxblock["height"])
                    logging.info(
                        "BLOCK rod-sha256d height=%s hash=%s worker=%s",
                        height,
                        block_hash,
                        worker,
                    )
                    pool_db.record_dual_chain_event(
                        chain="rod",
                        event_type="block",
                        status="accepted",
                        stone_address=self.resolve_stone_share_address(client) or "",
                        rod_address=getattr(client, "rod_address", None) or client.address or "",
                        worker=worker,
                        pool="rod_sha256d",
                        job_height=height,
                        block_hash=block_hash,
                    )
                    if self.stone_rpc and job.rod_auxblock:
                        ready, net_reason = bloodstone_broadcast.ensure_network_ready()
                        stone_accepted = False
                        if ready:
                            try:
                                stone_accepted = await rod_dual_submit.submit_stone_auxblock(
                                    self.stone_rpc,
                                    job.rod_auxblock,
                                    header_hex,
                                    job.extranonce1,
                                    extranonce2,
                                    submitted_cache=self._stone_submitted_blocks,
                                )
                            except Exception as exc:
                                logging.warning("STONE dual-submit error: %s", exc)
                        else:
                            logging.warning(
                                "skip STONE dual-submit height=%s — %s",
                                job.auxblock["height"],
                                net_reason,
                            )
                        if stone_accepted:
                            stone_height = int(job.rod_auxblock["height"])
                            stone_hash = str(job.rod_auxblock["hash"])
                            finder_addr = self.resolve_stone_finder_address(client, worker)
                            try:
                                dist = pool_db.distribute_block(
                                    "sha256d",
                                    stone_height,
                                    stone_hash,
                                    pool_fee_pct=self.pool_fee_pct,
                                    finder_address=finder_addr or None,
                                    finder_worker=worker,
                                )
                                logging.info(
                                    "STONE cross-subsidy payout round=%s miners=%s "
                                    "reward=%.4f mode=%s",
                                    dist.get("round_id"),
                                    dist.get("miners"),
                                    dist.get("reward_stone", 0),
                                    (dist.get("distribution_plan") or {}).get("mode"),
                                )
                            except Exception as exc:
                                logging.warning("STONE pool distribution failed: %s", exc)
                    await self.refresh_all_jobs(f"ROD block found height={height}")
                else:
                    logging.warning(
                        "ROD submitauxblock rejected for %s from %s",
                        block_hash,
                        worker,
                    )
        return True

    async def client_handler(self, reader, writer):
        client = RodPrimaryStratumClient(reader, writer, self)
        self.clients.add(client)
        try:
            await client.handle()
        finally:
            self.clients.discard(client)

    async def run(self):
        server = await asyncio.start_server(self.client_handler, self.host, self.port)
        logging.info("ROD-primary SHA256D stratum on %s:%s", self.host, self.port)
        async with server:
            await asyncio.gather(
                server.serve_forever(),
                self.refresh_jobs_loop(),
                _base.stratum_export_loop(self.clients, "rod-sha256d"),
            )


def main():
    parser = argparse.ArgumentParser(description="ROD-primary SHA256D stratum server")
    parser.add_argument(
        "--rpc-url",
        default=rod_dual_submit.DEFAULT_ROD_RPC,
        help="ROD mainnet RPC (primary work source)",
    )
    parser.add_argument(
        "--stone-rpc-url",
        default=rod_dual_submit.DEFAULT_STONE_RPC,
        help="Bloodstone RPC for STONE dual-submit (empty disables)",
    )
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=3441)
    parser.add_argument("--share-difficulty", type=float, default=0.01)
    parser.add_argument(
        "--stone-pool-wallet",
        default=rod_dual_submit.STONE_POOL_WALLET,
        help="STONE payout for dual-submitted merge-mined blocks",
    )
    parser.add_argument(
        "--no-stone-dual-submit",
        action="store_true",
        help="Disable submitting found blocks to Bloodstone/STONE",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    pool_db.init_db()

    stone_dual = (
        rod_dual_submit.stone_dual_submit_configured()
        and not args.no_stone_dual_submit
        and bool((args.stone_rpc_url or "").strip())
    )
    logging.info(
        "rod-primary sha256d pool_wallet=%s share_diff=%s stone_dual=%s",
        POOL_WALLET or "(per-miner ROD wallets)",
        args.share_difficulty,
        stone_dual,
    )
    if stone_dual:
        logging.info("STONE dual-submit wallet=%s", args.stone_pool_wallet)

    server = RodPrimaryStratumServer(
        args.rpc_url,
        args.stone_rpc_url if stone_dual else "",
        args.host,
        args.port,
        args.share_difficulty,
        stone_pool_wallet=(args.stone_pool_wallet or "").strip() if stone_dual else "",
        stone_dual_submit=stone_dual,
    )
    asyncio.run(server.run())


if __name__ == "__main__":
    main()