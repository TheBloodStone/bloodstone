"""Probe stratum process and connection status."""

import os
import re
import socket
import subprocess
import sys
from typing import Dict, List

sys.path.insert(0, "/root")
from stratum_worker_status import (  # noqa: E402
    is_fresh,
    read_json,
    stratum_status_path,
    ws_status_path,
)

import mining_config
import pool_db

_SUBPROCESS_TIMEOUT = int(os.environ.get("MINER_STATUS_SUBPROCESS_TIMEOUT", "8"))


def _check_output(cmd, **kwargs):
    kwargs.setdefault("timeout", _SUBPROCESS_TIMEOUT)
    return subprocess.check_output(cmd, **kwargs)


def port_listening(port: int) -> bool:
    try:
        out = _check_output(
            ["ss", "-H", "-tln", f"sport = :{port}"],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return bool(out.strip())
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False


def process_running(script_name: str) -> Dict:
    needle = f"/root/{script_name}"
    try:
        out = _check_output(
            ["pgrep", "-af", needle],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        lines = [
            ln.strip()
            for ln in out.splitlines()
            if ln.strip() and "python" in ln and script_name in ln
        ]
        return {"running": bool(lines), "processes": lines, "count": len(lines)}
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return {"running": False, "processes": [], "count": 0}


def connections_on_port(port: int) -> List[Dict]:
    peers = []
    try:
        out = _check_output(
            ["ss", "-H", "-tn", f"sport = :{port}"],
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return peers
    for line in out.splitlines():
        m = re.search(r"([\d.]+):(\d+)\s+([\d.]+):(\d+)", line)
        if not m:
            continue
        local_ip, local_port, peer_ip, peer_port = m.groups()
        peers.append(
            {
                "peer_ip": peer_ip,
                "peer_port": int(peer_port),
                "local": peer_ip in ("127.0.0.1", "::1"),
                "state": "ESTAB" if "ESTAB" in line else "UNKNOWN",
            }
        )
    return peers


_STRATUM_STATUS_ALIASES = {
    "neoscrypt": ("neoscrypt", "neoscrypt-xaya"),
}


def _read_stratum_worker_export(pool_key: str):
    keys = _STRATUM_STATUS_ALIASES.get(pool_key, (pool_key,))
    candidates = []
    for key in keys:
        data = read_json(stratum_status_path(key))
        if data:
            candidates.append(data)
    if not candidates:
        return None
    with_workers = [
        row for row in candidates if int(row.get("authorized") or 0) > 0
    ]
    pool = with_workers or candidates
    return max(pool, key=lambda row: float(row.get("updated_at") or 0))


def _worker_counts(pool_key: str, tcp_peers: List[Dict]) -> Dict:
    stratum_data = _read_stratum_worker_export(pool_key)
    ws_data = read_json(ws_status_path())

    authorized = 0
    worker_details: List[Dict] = []
    if is_fresh(stratum_data):
        authorized = int(stratum_data.get("authorized") or 0)
        worker_details = list(stratum_data.get("workers") or [])
    elif stratum_data:
        # Keep last known workers briefly if the export loop hiccups.
        authorized = int(stratum_data.get("authorized") or 0)
        worker_details = list(stratum_data.get("workers") or [])

    browser_workers = 0
    browser_details: List[Dict] = []
    if is_fresh(ws_data):
        browser_details = list((ws_data.get("pools") or {}).get(pool_key) or [])
        browser_workers = len(browser_details)

    tcp_count = len(tcp_peers)
    workers = max(authorized, browser_workers, tcp_count)
    native_workers = max(0, workers - browser_workers)

    return {
        "workers": workers,
        "authorized_workers": authorized,
        "browser_workers": browser_workers,
        "native_workers": native_workers,
        "worker_details": worker_details,
        "browser_details": browser_details,
    }


def pool_connection_info(pool_key: str) -> Dict:
    """Static stratum URLs and examples — always safe to show (no subprocess probes)."""
    cfg = mining_config.POOLS[pool_key]
    port = cfg["port"]
    tls_port = cfg.get("tls_port")
    sv2_port = cfg.get("sv2_port")
    ip = mining_config.stratum_client_host_for_pool(pool_key)
    fmt = {"ip": ip, "port": port, "tls_port": tls_port or port}
    url = f"stratum+tcp://{ip}:{port}"
    url_tls = f"stratum+tcp://{ip}:{tls_port}" if tls_port else None
    try:
        from stratum_extensions import SV2_AUTHORITY_PUBKEY, SV2_ENABLED
    except ImportError:
        SV2_ENABLED = False
        SV2_AUTHORITY_PUBKEY = ""
    sv2_pubkey = SV2_AUTHORITY_PUBKEY
    keys_path = "/opt/bloodstone-sv2/pool/authority-pubkey.txt"
    if not sv2_pubkey and os.path.isfile(keys_path):
        with open(keys_path, encoding="utf-8") as fh:
            sv2_pubkey = fh.read().strip()
    info = {
        "key": pool_key,
        "name": cfg["name"],
        "algo": cfg["algo"],
        "port": port,
        "tls_port": tls_port,
        "stratum_host": ip,
        "url": url,
        "url_tls": url_tls,
        "share_difficulty": cfg["share_difficulty"],
        "miner_hint": cfg["miner_hint"],
        "example_cmd": cfg["example_cmd"].format(**fmt),
        "example_user": cfg.get("stratum_user", "YOUR_STONE_ADDRESS"),
        "sv2_enabled": bool(pool_key == "sha256d" and SV2_ENABLED and sv2_port),
        "sv2_port": int(sv2_port) if sv2_port else None,
        "sv2_authority_pubkey": sv2_pubkey if pool_key == "sha256d" else "",
        "sv2_extensions": True,
        "connection_note": (
            f"Port {port} = plain TCP Stratum V1 (TLS OFF) — use this for Bitaxe SV1. "
            "Port 3430 = TLS via stunnel (TLS ON; self-signed cert — disable certificate "
            f"verification on Bitaxe). Port {sv2_port} = Stratum V2 only (Bitaxe SV2 mode); "
            "do not point SV1 miners at the SV2 port."
            if pool_key == "sha256d"
            else None
        ),
    }
    if pool_key == "sha256d":
        try:
            import pool_sha256_miner as sm

            info["rod_block_diff"] = sm.sha256_rod_block_diff_status(
                pool_share_difficulty=float(cfg["share_difficulty"])
            )
        except Exception as exc:
            info["rod_block_diff"] = {"error": str(exc)}
    return info


def _systemd_active(unit: str) -> bool:
    try:
        out = _check_output(
            ["systemctl", "is-active", unit],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        return out == "active"
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def sv2_tp_status() -> Dict:
    """Bloodstone auxpow template provider (pool_sv2 upstream on 127.0.0.1:8442)."""
    proc = {"running": False, "processes": [], "count": 0}
    try:
        out = _check_output(
            ["pgrep", "-af", "/opt/bloodstone-sv2/bloodstone-sv2-tp"],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
        proc = {"running": bool(lines), "processes": lines, "count": len(lines)}
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        pass
    listening = port_listening(8442)
    service_active = _systemd_active("bloodstone-sv2-tp.service")
    return {
        "enabled": True,
        "listen": "127.0.0.1:8442",
        "listening": listening,
        "process": proc,
        "service_active": service_active,
        "healthy": proc["running"] and listening,
        "service": "bloodstone-sv2-tp.service",
    }


def sv2_pool_status() -> Dict:
    """SRI pool_sv2 listener on the SHA256d SV2 port."""
    sv2_port = mining_config.POOLS.get("sha256d", {}).get("sv2_port")
    if not sv2_port:
        return {"enabled": False}
    proc = process_running("pool_sv2")
    if not proc["running"]:
        try:
            out = _check_output(
                ["pgrep", "-af", "/opt/bloodstone-sv2/pool/pool_sv2"],
                stderr=subprocess.DEVNULL,
                text=True,
            )
            lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
            proc = {"running": bool(lines), "processes": lines, "count": len(lines)}
        except subprocess.CalledProcessError:
            pass
    listening = port_listening(int(sv2_port))
    service_active = _systemd_active("bloodstone-stratum-sv2.service")
    return {
        "enabled": True,
        "port": int(sv2_port),
        "listening": listening,
        "process": proc,
        "service_active": service_active,
        "waiting_for_template_provider": service_active and not listening,
        "healthy": proc["running"] and listening,
        "service": "bloodstone-stratum-sv2.service",
    }


def pool_status(pool_key: str) -> Dict:
    cfg = mining_config.POOLS[pool_key]
    port = cfg["port"]
    proc = process_running(cfg["script"])
    peers = connections_on_port(port)
    listening = port_listening(port)
    counts = _worker_counts(pool_key, peers)
    status = {
        **pool_connection_info(pool_key),
        "listening": listening,
        "process": proc,
        "workers": counts["workers"],
        "authorized_workers": counts["authorized_workers"],
        "browser_workers": counts["browser_workers"],
        "native_workers": counts["native_workers"],
        "worker_details": counts["worker_details"],
        "browser_details": counts["browser_details"],
        "peers": peers,
        "healthy": proc["running"] and listening,
    }
    if pool_key == "sha256d":
        status["sv2_tp"] = sv2_tp_status()
        status["sv2_pool"] = sv2_pool_status()
    return status


def _pool_accounting(algo: str) -> Dict:
    try:
        stats = pool_db.get_pool_stats(algo)
        stats["round_miners"] = pool_db.get_round_miners(algo)
        import pool_algo_balance as pab

        stats["balance_multiplier"] = pab.get_share_multiplier(algo)
        stats["fee_pct"] = float(
            __import__("os").environ.get("BLOODSTONE_POOL_FEE_PCT", "1.0")
        )
        try:
            import pool_block_subsidy as pbs

            tip = pbs.current_tip_reward()
            stats["block_reward_stone"] = float(
                tip.get("reward_stone")
                or __import__("os").environ.get("BLOODSTONE_BLOCK_REWARD_STONE", "100")
            )
            stats["subsidy_schedule"] = {
                "era": tip.get("era"),
                "phase": tip.get("phase"),
                "next_halving_height": tip.get("next_halving_height"),
                "source": tip.get("source"),
            }
        except Exception:
            stats["block_reward_stone"] = float(
                __import__("os").environ.get("BLOODSTONE_BLOCK_REWARD_STONE", "100")
            )
        return pool_db.sanitize_public_pool_view(stats)
    except Exception as exc:
        return {"error": str(exc)}


def yespower_pool_accounting() -> Dict:
    return _pool_accounting("yespower")


def neoscrypt_pool_accounting() -> Dict:
    return _pool_accounting("neoscrypt")


def sha256_pool_accounting() -> Dict:
    return _pool_accounting("sha256d")


def _cpuminer_pool_miner_status(
    service: str, algo_needle: str, port: int
) -> Dict:
    active = False
    try:
        out = _check_output(
            ["systemctl", "is-active", service],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        active = out == "active"
    except (subprocess.CalledProcessError, FileNotFoundError):
        active = False

    processes = []
    try:
        out = _check_output(
            ["pgrep", "-af", "/root/cpuminer-opt"],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        processes = [
            ln.strip()
            for ln in out.splitlines()
            if algo_needle in ln and f":{port}" in ln
        ]
    except subprocess.CalledProcessError:
        processes = []

    return {
        "service": service,
        "active": active or bool(processes),
        "processes": processes,
        "binary": "/root/cpuminer-opt",
        "mode": "pool",
        "port": port,
    }


def yespower_block_finder_status() -> Dict:
    """Server-side cpuminer-opt pool miner (shares count toward proportional rewards)."""
    return _cpuminer_pool_miner_status(
        "bloodstone-yespower-miner.service",
        "yespowerr16",
        mining_config.POOLS["yespower"]["port"],
    )


def neoscrypt_pool_miner_status() -> Dict:
    return _cpuminer_pool_miner_status(
        "bloodstone-neoscrypt-pool-miner.service",
        "neoscrypt",
        mining_config.POOLS["neoscrypt"]["port"],
    )


def _port_open(port: int, host: str = "127.0.0.1") -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=0.4):
            return True
    except OSError:
        return False


def pools_status_light_fast() -> Dict:
    """Instant pool cards: worker counts from stratum JSON exports (no subprocess)."""
    pools: Dict[str, Dict] = {}
    for pool_key in mining_config.POOLS:
        cfg = mining_config.POOLS[pool_key]
        port = int(cfg["port"])
        counts = _worker_counts(pool_key, [])
        listening = _port_open(port)
        workers = int(counts["workers"] or 0)
        pools[pool_key] = {
            **pool_connection_info(pool_key),
            "listening": listening or workers > 0,
            "healthy": listening or workers > 0,
            "process": {"running": listening, "processes": [], "count": 1 if listening else 0},
            "workers": workers,
            "authorized_workers": counts["authorized_workers"],
            "browser_workers": counts["browser_workers"],
            "native_workers": counts["native_workers"],
            "worker_details": counts["worker_details"],
            "browser_details": counts["browser_details"],
            "peers": [],
        }
        if pool_key == "sha256d":
            pools[pool_key]["sv2_tp"] = {"enabled": False}
            pools[pool_key]["sv2_pool"] = {"listening": False}
    return pools


def pools_status_light():
    """Worker/listener status only — safe for frequent /api/status polling."""
    return {key: pool_status(key) for key in mining_config.POOLS}


def all_pools_status():
    pools = pools_status_light()
    pools["yespower"]["block_finder"] = yespower_block_finder_status()
    pools["yespower"]["pool_accounting"] = yespower_pool_accounting()
    pools["neoscrypt"]["pool_miner"] = neoscrypt_pool_miner_status()
    pools["neoscrypt"]["pool_accounting"] = neoscrypt_pool_accounting()
    pools["sha256d"]["pool_accounting"] = sha256_pool_accounting()
    return pools