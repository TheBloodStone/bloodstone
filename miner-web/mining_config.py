"""Bloodstone mining / stratum configuration."""

import copy
import os

from settings_store import read_kv

VPS_IP = os.environ.get("MINER_VPS_IP", "64.188.22.190")
BLOODSTONE_CONF = os.environ.get("BLOODSTONE_CONF", "/root/.bloodstone/bloodstone.conf")
YESPOWER_FORK_HEIGHT = int(os.environ.get("YESPOWER_FORK_HEIGHT", "1"))
MULTI_ALGO_FORK_HEIGHT = int(os.environ.get("MULTI_ALGO_FORK_HEIGHT", "1"))

OVERRIDES_PATH = os.environ.get(
    "MINER_SERVICE_OVERRIDES", "/root/bloodstone-miner-web/service-overrides.conf"
)

CPU_STRATUM_POOLS = frozenset({"neoscrypt", "yespower"})

_BASE_POOLS = {
    "neoscrypt": {
        "name": "Neoscrypt-Xaya",
        "algo": "neoscrypt-xaya",
        "port": 3437,
        "script": "bloodstone-stratum.py",
        "start_script": "/root/start-bloodstone-stratum-neoscrypt.sh",
        "restart_script": "/root/restart-bloodstone-stratum-neoscrypt.sh",
        "share_difficulty": 1e-8,
        "miner_hint": "nsgminer / sgminer / ccminer (-k neoscrypt-xaya)",
        "stratum_user": "YOUR_STONE_ADDRESS",
        "stratum_pass": "x",
        "example_cmd": (
            "nsgminer -k neoscrypt-xaya -o stratum+tcp://{ip}:{port} "
            "-u YOUR_STONE_ADDRESS -p x"
        ),
    },
    "sha256d": {
        "name": "SHA256d (ROD merge)",
        "algo": "sha256d",
        "port": 3429,
        "tls_port": 3430,
        "sv2_port": 3425,
        "script": "bloodstone-stratum-sha256.py",
        "start_script": "/root/start-bloodstone-stratum-sha256.sh",
        "restart_script": "/root/start-bloodstone-stratum-sha256.sh",
        "share_difficulty": 0.01,
        "miner_hint": "Bitaxe / ASIC — AuxPoW merge-mined on SpaceXpanse ROD (chain 1899)",
        "stratum_user": "YOUR_STONE_ADDRESS",
        "stratum_pass": "x",
        "example_cmd": (
            "Plain: stratum+tcp://{ip}:{port}  |  "
            "TLS: stratum+tcp://{ip}:{tls_port}  "
            "(worker YOUR_STONE_ADDRESS, password x)"
        ),
    },
    "yespower": {
        "name": "Yespower R16",
        "algo": "yespower",
        "port": 3438,
        "script": "bloodstone-stratum-yespower.py",
        "start_script": "/root/start-bloodstone-stratum-yespower.sh",
        "restart_script": "/root/restart-bloodstone-stratum-yespower.sh",
        "share_difficulty": 6e-8,
        "miner_hint": "cpuminer-opt (yespowerr16)",
        "stratum_user": "YOUR_STONE_ADDRESS",
        "stratum_pass": "x",
        "example_cmd": (
            "./cpuminer -a yespowerr16 -o stratum+tcp://{ip}:{port} "
            "-u YOUR_STONE_ADDRESS -p x"
        ),
    },
    "rod_neoscrypt": {
        "name": "ROD Neoscrypt",
        "algo": "neoscrypt",
        "reward_coin": "ROD",
        "port": 3440,
        "script": "bloodstone-stratum-rod-neoscrypt.py",
        "start_script": "/root/start-bloodstone-stratum-rod-neoscrypt.sh",
        "restart_script": "/root/restart-bloodstone-stratum-rod-neoscrypt.sh",
        "share_difficulty": 1e-6,
        "miner_hint": "SpaceXpanse ROD mainnet neoscrypt-xaya (browser + CPU)",
        "stratum_user": "YOUR_ROD_ADDRESS",
        "stratum_pass": "x",
        "example_cmd": (
            "sgminer -k neoscrypt -o stratum+tcp://{ip}:{port} "
            "-u YOUR_ROD_ADDRESS -p x"
        ),
    },
}


def _float_override(raw: dict, *keys, default: float) -> float:
    for key in keys:
        if key in raw and str(raw[key]).strip():
            return float(raw[key])
    return default


def _int_override(raw: dict, *keys, default: int) -> int:
    for key in keys:
        if key in raw and str(raw[key]).strip():
            return int(float(raw[key]))
    return default


def build_pools() -> dict:
    raw = read_kv(OVERRIDES_PATH)
    env = os.environ
    pools = copy.deepcopy(_BASE_POOLS)

    pools["neoscrypt"]["port"] = _int_override(
        raw,
        "BLOODSTONE_STRATUM_PORT",
        "neoscrypt_port",
        default=_int_override(
            env, "BLOODSTONE_STRATUM_PORT", default=pools["neoscrypt"]["port"]
        ),
    )
    pools["sha256d"]["port"] = _int_override(
        raw,
        "BLOODSTONE_SHA256_STRATUM_PORT",
        "sha256d_port",
        default=_int_override(
            env, "BLOODSTONE_SHA256_STRATUM_PORT", default=pools["sha256d"]["port"]
        ),
    )
    pools["yespower"]["port"] = _int_override(
        raw,
        "BLOODSTONE_YESPOWER_STRATUM_PORT",
        "yespower_port",
        default=_int_override(
            env, "BLOODSTONE_YESPOWER_STRATUM_PORT", default=pools["yespower"]["port"]
        ),
    )
    pools["rod_neoscrypt"]["port"] = _int_override(
        raw,
        "BLOODSTONE_ROD_NEOSCRYPT_STRATUM_PORT",
        "rod_neoscrypt_port",
        default=_int_override(
            env,
            "BLOODSTONE_ROD_NEOSCRYPT_STRATUM_PORT",
            default=pools["rod_neoscrypt"]["port"],
        ),
    )

    pools["neoscrypt"]["share_difficulty"] = _float_override(
        raw,
        "BLOODSTONE_NEOSCRYPT_SHARE_DIFFICULTY",
        "BLOODSTONE_SHARE_DIFFICULTY",
        "neoscrypt_share_difficulty",
        default=_float_override(
            env,
            "BLOODSTONE_NEOSCRYPT_SHARE_DIFFICULTY",
            "BLOODSTONE_SHARE_DIFFICULTY",
            default=pools["neoscrypt"]["share_difficulty"],
        ),
    )
    pools["sha256d"]["sv2_port"] = _int_override(
        raw,
        "BLOODSTONE_SHA256_SV2_PORT",
        "sha256d_sv2_port",
        default=_int_override(
            env, "BLOODSTONE_SHA256_SV2_PORT", default=pools["sha256d"].get("sv2_port", 3425)
        ),
    )
    pools["sha256d"]["share_difficulty"] = _float_override(
        raw,
        "BLOODSTONE_SHA256_SHARE_DIFFICULTY",
        "sha256d_share_difficulty",
        default=_float_override(
            env,
            "BLOODSTONE_SHA256_SHARE_DIFFICULTY",
            default=pools["sha256d"]["share_difficulty"],
        ),
    )
    pools["sha256d"]["asic_diff_min"] = _float_override(
        raw,
        "BLOODSTONE_SHA256_ASIC_DIFF_MIN",
        "sha256d_asic_diff_min",
        default=_float_override(
            env,
            "BLOODSTONE_SHA256_ASIC_DIFF_MIN",
            default=1_000_000.0,
        ),
    )
    pools["sha256d"]["asic_diff_max"] = _float_override(
        raw,
        "BLOODSTONE_SHA256_ASIC_DIFF_MAX",
        "sha256d_asic_diff_max",
        default=_float_override(
            env,
            "BLOODSTONE_SHA256_ASIC_DIFF_MAX",
            default=0.0,
        ),
    )
    pools["yespower"]["share_difficulty"] = _float_override(
        raw,
        "BLOODSTONE_YESPOWER_SHARE_DIFFICULTY",
        "yespower_share_difficulty",
        default=_float_override(
            env,
            "BLOODSTONE_YESPOWER_SHARE_DIFFICULTY",
            default=pools["yespower"]["share_difficulty"],
        ),
    )
    pools["rod_neoscrypt"]["share_difficulty"] = _float_override(
        raw,
        "BLOODSTONE_ROD_NEOSCRYPT_SHARE_DIFFICULTY",
        "rod_neoscrypt_share_difficulty",
        default=_float_override(
            env,
            "BLOODSTONE_ROD_NEOSCRYPT_SHARE_DIFFICULTY",
            default=pools["rod_neoscrypt"]["share_difficulty"],
        ),
    )

    pools["neoscrypt"]["gpu_share_difficulty"] = _float_override(
        raw,
        "BLOODSTONE_NEOSCRYPT_GPU_SHARE_DIFFICULTY",
        "neoscrypt_gpu_share_difficulty",
        default=_float_override(
            env,
            "BLOODSTONE_NEOSCRYPT_GPU_SHARE_DIFFICULTY",
            default=1e-6,
        ),
    )
    pools["yespower"]["gpu_share_difficulty"] = _float_override(
        raw,
        "BLOODSTONE_YESPOWER_GPU_SHARE_DIFFICULTY",
        "yespower_gpu_share_difficulty",
        default=_float_override(
            env,
            "BLOODSTONE_YESPOWER_GPU_SHARE_DIFFICULTY",
            default=1e-6,
        ),
    )

    return pools


def get_vps_ip() -> str:
    raw = read_kv(OVERRIDES_PATH)
    return raw.get("MINER_VPS_IP") or os.environ.get("MINER_VPS_IP") or VPS_IP


def get_cpu_stratum_host() -> str:
    """Secondary worker that runs neoscrypt/yespower stratum."""
    raw = read_kv(OVERRIDES_PATH)
    host = (
        raw.get("STRATUM_UPSTREAM_HOST")
        or os.environ.get("STRATUM_UPSTREAM_HOST", "")
    ).strip()
    return host or get_vps_ip()


def stratum_host_for_pool(pool_key: str) -> str:
    if pool_key in CPU_STRATUM_POOLS:
        return get_cpu_stratum_host()
    return get_vps_ip()


def stratum_hosts() -> dict:
    return {key: stratum_host_for_pool(key) for key in POOLS}


def stratum_client_host_for_pool(pool_key: str) -> str:
    """Public stratum host shown to external miners — never loopback."""
    host = stratum_host_for_pool(pool_key)
    if host in ("127.0.0.1", "localhost", "::1"):
        return get_vps_ip()
    return host


def stratum_client_hosts() -> dict:
    """Hosts for external miners (phones, browsers, Awesome Miner) — never loopback."""
    return {key: stratum_client_host_for_pool(key) for key in POOLS}


def reload_pools() -> dict:
    global POOLS, VPS_IP
    POOLS = build_pools()
    VPS_IP = get_vps_ip()
    return POOLS


POOLS = build_pools()
VPS_IP = get_vps_ip()


def load_service_overrides() -> dict:
    raw = read_kv(OVERRIDES_PATH)
    pools = POOLS
    return {
        "MINER_VPS_IP": get_vps_ip(),
        "BLOODSTONE_STRATUM_PORT": str(pools["neoscrypt"]["port"]),
        "BLOODSTONE_SHA256_STRATUM_PORT": str(pools["sha256d"]["port"]),
        "BLOODSTONE_YESPOWER_STRATUM_PORT": str(pools["yespower"]["port"]),
        "BLOODSTONE_ROD_NEOSCRYPT_STRATUM_PORT": str(pools["rod_neoscrypt"]["port"]),
        "BLOODSTONE_NEOSCRYPT_SHARE_DIFFICULTY": str(pools["neoscrypt"]["share_difficulty"]),
        "BLOODSTONE_SHA256_SHARE_DIFFICULTY": str(pools["sha256d"]["share_difficulty"]),
        "BLOODSTONE_SHA256_ASIC_DIFF_MIN": str(pools["sha256d"]["asic_diff_min"]),
        "BLOODSTONE_SHA256_ASIC_DIFF_MAX": str(pools["sha256d"]["asic_diff_max"]),
        "BLOODSTONE_YESPOWER_SHARE_DIFFICULTY": str(pools["yespower"]["share_difficulty"]),
        "BLOODSTONE_ROD_NEOSCRYPT_SHARE_DIFFICULTY": str(
            pools["rod_neoscrypt"]["share_difficulty"]
        ),
        "BLOODSTONE_NEOSCRYPT_GPU_SHARE_DIFFICULTY": str(
            pools["neoscrypt"]["gpu_share_difficulty"]
        ),
        "BLOODSTONE_YESPOWER_GPU_SHARE_DIFFICULTY": str(
            pools["yespower"]["gpu_share_difficulty"]
        ),
        "BLOODSTONE_NEOSCRYPT_GPU_DIFF_MAX": raw.get(
            "BLOODSTONE_NEOSCRYPT_GPU_DIFF_MAX", "1000"
        ),
        "BLOODSTONE_YESPOWER_GPU_DIFF_MAX": raw.get(
            "BLOODSTONE_YESPOWER_GPU_DIFF_MAX", "1000"
        ),
        "BLOODSTONE_PROPORTIONAL_SHARE_INTERVAL_SEC": raw.get(
            "BLOODSTONE_PROPORTIONAL_SHARE_INTERVAL_SEC", "30"
        ),
        "BLOODSTONE_NEOSCRYPT_GPU_SHARE_INTERVAL": raw.get(
            "BLOODSTONE_NEOSCRYPT_GPU_SHARE_INTERVAL", "30"
        ),
        "BLOODSTONE_YESPOWER_GPU_SHARE_INTERVAL": raw.get(
            "BLOODSTONE_YESPOWER_GPU_SHARE_INTERVAL", "30"
        ),
        "BLOODSTONE_SHA256_POOL_VARDIFF": raw.get(
            "BLOODSTONE_SHA256_POOL_VARDIFF", "1"
        ),
        "BLOODSTONE_SHA256_POOL_VARDIFF_INTERVAL": raw.get(
            "BLOODSTONE_SHA256_POOL_VARDIFF_INTERVAL", "30"
        ),
        "BLOODSTONE_SHA256_BLOCK_BUMP_ON_FIND": raw.get(
            "BLOODSTONE_SHA256_BLOCK_BUMP_ON_FIND", "0"
        ),
        "BLOODSTONE_MOBILE_CONTRIB_LOOP_SEC": raw.get(
            "BLOODSTONE_MOBILE_CONTRIB_LOOP_SEC", "30"
        ),
        "BLOODSTONE_GPU_VARDIFF_MAX_STEP": raw.get(
            "BLOODSTONE_GPU_VARDIFF_MAX_STEP", "16"
        ),
        "BLOODSTONE_GPU_SHARE_FLUSH_SEC": raw.get(
            "BLOODSTONE_GPU_SHARE_FLUSH_SEC", "90"
        ),
        "BLOODSTONE_GPU_SHARE_BATCH": raw.get("BLOODSTONE_GPU_SHARE_BATCH", "1"),
        **raw,
    }


def save_service_overrides(updates: dict) -> None:
    from settings_store import write_kv

    write_kv(
        OVERRIDES_PATH,
        updates,
        header="# Bloodstone stratum / mining overrides (edited via /mining/admin)",
    )
    reload_pools()