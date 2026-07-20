#!/usr/bin/env python3
"""Bloodstone Fork Builder - offline compiler for Fork Lab paid coins.

Home-computer toolkit:
  1. Load a Fork Lab manifest (JSON file or paste).
  2. **Adjust coin settings** (name, ticker, ports, algos, rewards, salt, ...)
     before compile - GUI form or CLI --set / --settings.
  3. Unpack Bloodstone core source (vendor/ or local path; auto-downloads if missing).
  4. Patch ports, network magic, branding, and salt into the tree.
  5. **Compile binaries locally now** - produce VPS server kit, Qt wallet kit,
     and the usual distribution items (conf, scripts, notes, bootstrap links).

Resilient builds: when configure/make fails on a missing library or tool, the
builder parses the error, apt-installs matching packages, and retries.

Works fully offline once core source and packages are cached.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

APP_VERSION = "1.5.1"

# Individual product kits — select what to build/package (not only full bundle).
PRODUCT_CHOICES = (
    "daemon",           # binary only: *d
    "cli",              # binary only: *-cli
    "vps",              # VPS / server kit (daemon+cli+conf+systemd)
    "qt",               # Qt desktop wallet kit
    "android-full-node",  # Full-node edge profile + Android starter pack (phone/tablet)
    "android-pruned-node",  # Pruned edge profile pack
    "edge-node",        # Generic multi-device edge profile kit
    "full",             # Full distribution (vps + qt + notes)
)
DEFAULT_PRODUCTS = ("vps", "qt", "full", "android-full-node", "edge-node")

# Human-readable labels for GUI + menu (product id → label).
PRODUCT_LABELS = {
    "android-full-node": "Make a full node on your device or phone",
    "android-pruned-node": "Pruned node on phone / device (lighter)",
    "edge-node": "Edge node on any device (phone, desktop, Pi)",
    "vps": "VPS / server kit (daemon + cli)",
    "qt": "Desktop Qt wallet kit",
    "daemon": "Daemon binary only",
    "cli": "CLI binary only",
    "full": "Full distribution bundle",
}
# Products that are profile kits only (no C++ compile required).
PROFILE_ONLY_PRODUCTS = frozenset(
    {"android-full-node", "android-pruned-node", "edge-node"}
)
APP_ROOT = Path(__file__).resolve().parent
VENDOR_DIR = APP_ROOT / "vendor"
DEFAULT_WORK = APP_ROOT / "work"
CORE_TARBALL_NAMES = (
    "bloodstone-core-source-latest.tar.gz",
    "bloodstone-core-0.7.2-source.tar.gz",
    "bloodstone-core-source.tar.gz",
)
PUBLIC_ROOT = os.environ.get(
    "BLOODSTONE_PUBLIC_ROOT", "https://bloodstonewallet.mytunnel.org"
).rstrip("/")
PUBLIC_DOWNLOADS = PUBLIC_ROOT + "/downloads"

# Max times we auto-install packages and retry a failed build step
MAX_DEP_RETRIES = 8

# Base toolchain + libraries required for bloodstoned / bloodstone-cli
BASE_BUILD_PACKAGES = (
    "build-essential",
    "libtool",
    "autotools-dev",
    "automake",
    "pkg-config",
    "bsdmainutils",
    "python3",
    "libssl-dev",
    "libevent-dev",
    "libboost-all-dev",
    "libdb5.3-dev",
    "libdb5.3++-dev",
    "libdb-dev",
    "libdb++-dev",
    "libminiupnpc-dev",
    "libzmq3-dev",
    "libsqlite3-dev",
    "curl",
    "ca-certificates",
)

# Qt desktop wallet
GUI_BUILD_PACKAGES = (
    "qtbase5-dev",
    "qttools5-dev",
    "qttools5-dev-tools",
    "libqt5gui5",
    "libqt5core5a",
    "libqt5dbus5",
    "libqrencode-dev",
    "libprotobuf-dev",
    "protobuf-compiler",
)

# Map error tokens (headers, -l flags, pkg-config names, tool names) → apt packages.
# First matching key wins for a given token; keep common aliases listed.
DEP_TOKEN_TO_PACKAGES: Dict[str, Tuple[str, ...]] = {
    # Compilers / autotools
    "g++": ("build-essential",),
    "gcc": ("build-essential",),
    "c++": ("build-essential",),
    "make": ("build-essential",),
    "automake": ("automake", "autotools-dev"),
    "autoconf": ("autoconf", "autotools-dev"),
    "libtool": ("libtool",),
    "pkg-config": ("pkg-config",),
    "pkgconf": ("pkg-config",),
    "autoreconf": ("autoconf", "automake", "libtool"),
    # OpenSSL
    "ssl": ("libssl-dev",),
    "openssl": ("libssl-dev",),
    "libssl": ("libssl-dev",),
    "libcrypto": ("libssl-dev",),
    "openssl/ssl.h": ("libssl-dev",),
    "openssl/evp.h": ("libssl-dev",),
    "openssl/err.h": ("libssl-dev",),
    # libevent
    "event": ("libevent-dev",),
    "libevent": ("libevent-dev",),
    "libevent_pthreads": ("libevent-dev",),
    "libevent_core": ("libevent-dev",),
    "libevent_extra": ("libevent-dev",),
    "event2/event.h": ("libevent-dev",),
    "event2/buffer.h": ("libevent-dev",),
    "event2/http.h": ("libevent-dev",),
    # Boost
    "boost": ("libboost-all-dev",),
    "libboost": ("libboost-all-dev",),
    "boost_system": ("libboost-all-dev",),
    "boost_filesystem": ("libboost-all-dev",),
    "boost_thread": ("libboost-all-dev",),
    "boost_chrono": ("libboost-all-dev",),
    "boost_program_options": ("libboost-all-dev",),
    "boost_unit_test_framework": ("libboost-all-dev",),
    "boost/version.hpp": ("libboost-all-dev",),
    "boost/filesystem.hpp": ("libboost-all-dev",),
    "boost/thread.hpp": ("libboost-all-dev",),
    # Berkeley DB
    "db_cxx": ("libdb5.3++-dev", "libdb++-dev", "libdb5.3-dev", "libdb-dev"),
    "db_cxx.h": ("libdb5.3++-dev", "libdb++-dev"),
    "db.h": ("libdb5.3-dev", "libdb-dev"),
    "libdb": ("libdb5.3-dev", "libdb-dev"),
    "libdb_cxx": ("libdb5.3++-dev", "libdb++-dev"),
    # MiniUPnP / NAT-PMP
    "miniupnpc": ("libminiupnpc-dev",),
    "miniupnpc.h": ("libminiupnpc-dev",),
    "libminiupnpc": ("libminiupnpc-dev",),
    "natpmp": ("libnatpmp-dev",),
    "natpmp.h": ("libnatpmp-dev",),
    # ZeroMQ
    "zmq": ("libzmq3-dev",),
    "libzmq": ("libzmq3-dev",),
    "zmq.h": ("libzmq3-dev",),
    "zmq.hpp": ("libzmq3-dev",),
    # SQLite
    "sqlite3": ("libsqlite3-dev",),
    "libsqlite3": ("libsqlite3-dev",),
    "sqlite3.h": ("libsqlite3-dev",),
    # Qt / GUI
    "qt5": ("qtbase5-dev", "qttools5-dev", "qttools5-dev-tools"),
    "qt": ("qtbase5-dev", "qttools5-dev"),
    "qtbase": ("qtbase5-dev",),
    "Qt5Core": ("qtbase5-dev",),
    "Qt5Gui": ("qtbase5-dev",),
    "Qt5Widgets": ("qtbase5-dev",),
    "Qt5Network": ("qtbase5-dev",),
    "Qt5DBus": ("qtbase5-dev",),
    "Qt5Test": ("qtbase5-dev",),
    "QtCore": ("qtbase5-dev",),
    "QtGui": ("qtbase5-dev",),
    "QtWidgets": ("qtbase5-dev",),
    "QApplication": ("qtbase5-dev",),
    "lrelease": ("qttools5-dev-tools", "qttools5-dev"),
    "moc": ("qtbase5-dev", "qttools5-dev"),
    "uic": ("qtbase5-dev", "qttools5-dev"),
    "rcc": ("qtbase5-dev",),
    "qrencode": ("libqrencode-dev",),
    "libqrencode": ("libqrencode-dev",),
    "qrencode.h": ("libqrencode-dev",),
    "protobuf": ("libprotobuf-dev", "protobuf-compiler"),
    "libprotobuf": ("libprotobuf-dev", "protobuf-compiler"),
    "google/protobuf": ("libprotobuf-dev", "protobuf-compiler"),
    "protoc": ("protobuf-compiler",),
    # Misc
    "hexdump": ("bsdmainutils", "bsdextrautils"),
    "gawk": ("gawk",),
    "python3": ("python3",),
    "curl": ("curl", "ca-certificates"),
}

# Parent-chain reference kits (users rebrand/rebuild for their fork)
USUAL_DOWNLOAD_ITEMS = (
    ("Core source (parent)", "bloodstone-core-source-latest.tar.gz"),
    ("Exchange / VPS node (parent reference)", "bloodstone-exchange-node-latest.tar.gz"),
    ("Chain bootstrap (sync faster)", "bloodstone-chain-bootstrap-latest.tar.gz"),
    ("Qt wallet Windows (parent reference)", "bloodstone-qt-0.7.4-win64.exe"),
    ("Qt wallet Linux aarch64 (parent)", "bloodstone-qt-linux-aarch64-latest.tar.gz"),
    ("Fork Builder (this toolkit)", "bloodstone-fork-builder-latest.tar.gz"),
)

# Editable fields before compile (shown in GUI + accepted by CLI)
EDITABLE_FIELDS = (
    ("name", "Coin name", "str"),
    ("ticker", "Ticker", "str"),
    ("p2p_port", "P2P port", "int"),
    ("rpc_port", "RPC port", "int"),
    ("block_time_seconds", "Block time (sec)", "int"),
    ("block_reward", "Block reward", "float"),
    ("premine", "Premine", "float"),
    ("network_salt", "Network salt (hex)", "str"),
    ("message_start_hint", "Magic hint (8 hex)", "str"),
    ("algos", "Algos (comma-separated)", "algos"),
    ("website", "Website", "str"),
    ("description", "Description", "str"),
    ("icon_url", "Icon URL (optional)", "str"),
    ("datadir_name", "Datadir folder name", "str"),
)


def _log(msg: str) -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(str(msg).encode("ascii", "replace").decode("ascii"), flush=True)


def _safe_stdio() -> None:
    """Avoid Windows cp1252 crashes on unicode in prints."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:
            pass


def load_manifest(path: Path) -> Dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("manifest must be a JSON object")
    # Accept raw API {fork: {...}, manifest: {...}} wrappers
    if "consensus" not in data and isinstance(data.get("manifest"), dict):
        data = data["manifest"]
    if "consensus" not in data and isinstance(data.get("fork"), dict):
        fork = data["fork"]
        data = {
            "schema": "bloodstone/fork-coin-manifest/v1",
            "fork_id": fork.get("fork_id"),
            "name": fork.get("name"),
            "ticker": fork.get("ticker"),
            "status": fork.get("status"),
            "website": fork.get("website") or "",
            "description": fork.get("description") or "",
            "consensus": {
                "pow_algorithms": fork.get("algos") or [],
                "block_time_seconds": fork.get("block_time_sec") or 90,
                "block_reward": fork.get("block_reward") or 100,
                "premine": fork.get("premine_stone") or 0,
                "network_salt": fork.get("network_salt"),
                "message_start_hint": fork.get("magic_hint"),
                "p2p_port_hint": fork.get("p2p_port"),
                "rpc_port_hint": fork.get("rpc_port"),
            },
            "branding": {
                "icon_url": (fork.get("icon") or {}).get("url")
                if isinstance(fork.get("icon"), dict)
                else fork.get("icon_url"),
            },
            "parent": {
                "source_core": "https://bloodstonewallet.mytunnel.org/downloads/bloodstone-core-source-latest.tar.gz",
                "github": "https://github.com/TheBloodStone/bloodstone",
            },
        }
    if "consensus" not in data:
        raise ValueError("manifest missing consensus block - export from Fork Lab")
    if not data.get("ticker") and not data.get("name"):
        raise ValueError("manifest missing name/ticker")
    # ensure branding dict
    if not isinstance(data.get("branding"), dict):
        data["branding"] = {}
    return data


def extract_settings(manifest: Dict[str, Any]) -> Dict[str, Any]:
    """Flat editable settings view of a manifest."""
    cons = manifest.get("consensus") or {}
    branding = manifest.get("branding") or {}
    algos = cons.get("pow_algorithms") or []
    if isinstance(algos, str):
        algos_s = algos
    else:
        algos_s = ",".join(str(a) for a in algos)
    ticker = str(manifest.get("ticker") or "FORK").upper()
    return {
        "name": str(manifest.get("name") or "ForkCoin"),
        "ticker": ticker,
        "p2p_port": int(cons.get("p2p_port_hint") or 17333),
        "rpc_port": int(cons.get("rpc_port_hint") or 18332),
        "block_time_seconds": int(cons.get("block_time_seconds") or 90),
        "block_reward": float(cons.get("block_reward") or 100),
        "premine": float(cons.get("premine") or 0),
        "network_salt": str(cons.get("network_salt") or ""),
        "message_start_hint": str(cons.get("message_start_hint") or ""),
        "algos": algos_s,
        "website": str(manifest.get("website") or ""),
        "description": str(manifest.get("description") or ""),
        "icon_url": str(branding.get("icon_url") or branding.get("qt_icon_url") or ""),
        "datadir_name": str(
            (manifest.get("builder") or {}).get("datadir_name")
            or f".{ticker.lower()}"
        ),
        "fork_id": str(manifest.get("fork_id") or ""),
    }


def apply_settings_to_manifest(
    manifest: Dict[str, Any], settings: Dict[str, Any]
) -> Dict[str, Any]:
    """Return a deep-copied manifest with creator-adjusted settings applied."""
    m = copy.deepcopy(manifest)
    cons = m.setdefault("consensus", {})
    branding = m.setdefault("branding", {})
    builder = m.setdefault("builder", {})

    name = str(settings.get("name") or m.get("name") or "ForkCoin").strip()
    ticker = str(settings.get("ticker") or m.get("ticker") or "FORK").strip().upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9]{1,9}", ticker):
        raise ValueError("ticker must be 2-10 chars A-Z/0-9 starting with a letter")
    if not name or len(name) > 48:
        raise ValueError("name required (max 48 chars)")

    try:
        p2p = int(settings.get("p2p_port") or cons.get("p2p_port_hint") or 17333)
        rpc = int(settings.get("rpc_port") or cons.get("rpc_port_hint") or 18332)
    except (TypeError, ValueError) as exc:
        raise ValueError("p2p_port and rpc_port must be integers") from exc
    p2p = max(1024, min(65535, p2p))
    rpc = max(1024, min(65535, rpc))
    if rpc == p2p:
        rpc = min(65535, p2p + 1)

    try:
        block_time = int(settings.get("block_time_seconds") or cons.get("block_time_seconds") or 90)
    except (TypeError, ValueError) as exc:
        raise ValueError("block_time_seconds must be an integer") from exc
    block_time = max(30, min(600, block_time))

    try:
        block_reward = float(settings.get("block_reward") if settings.get("block_reward") is not None else cons.get("block_reward") or 100)
        premine = float(settings.get("premine") if settings.get("premine") is not None else cons.get("premine") or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError("block_reward / premine must be numbers") from exc
    if block_reward <= 0:
        raise ValueError("block_reward must be positive")
    if premine < 0:
        raise ValueError("premine cannot be negative")

    salt = str(settings.get("network_salt") if settings.get("network_salt") is not None else cons.get("network_salt") or "").strip()
    magic_hint = str(
        settings.get("message_start_hint")
        if settings.get("message_start_hint") is not None
        else cons.get("message_start_hint")
        or ""
    ).strip().lower()
    if magic_hint and not re.fullmatch(r"[0-9a-f]{8}", magic_hint):
        raise ValueError("message_start_hint must be 8 hex chars (e.g. a1b2c3d4)")
    if salt and not re.fullmatch(r"[0-9a-fA-F]{8,64}", salt):
        raise ValueError("network_salt must be 8-64 hex characters")

    algos_raw = settings.get("algos")
    if algos_raw is None:
        algos = list(cons.get("pow_algorithms") or ["neoscrypt", "yespower", "sha256d"])
    elif isinstance(algos_raw, str):
        algos = [a.strip().lower() for a in algos_raw.replace(";", ",").split(",") if a.strip()]
    else:
        algos = [str(a).strip().lower() for a in algos_raw if str(a).strip()]
    allowed = {"neoscrypt", "yespower", "sha256d"}
    algos = [a for a in algos if a in allowed]
    if not algos:
        raise ValueError("select at least one algo: neoscrypt, yespower, sha256d")

    datadir = str(settings.get("datadir_name") or f".{ticker.lower()}").strip()
    datadir = re.sub(r"[^A-Za-z0-9._-]", "", datadir) or f".{ticker.lower()}"
    if not datadir.startswith("."):
        datadir = "." + datadir

    m["name"] = name
    m["ticker"] = ticker
    m["website"] = str(settings.get("website") if settings.get("website") is not None else m.get("website") or "")[:200]
    m["description"] = str(
        settings.get("description") if settings.get("description") is not None else m.get("description") or ""
    )[:500]
    cons["p2p_port_hint"] = p2p
    cons["rpc_port_hint"] = rpc
    cons["block_time_seconds"] = block_time
    cons["block_reward"] = block_reward
    cons["premine"] = premine
    cons["network_salt"] = salt
    cons["message_start_hint"] = magic_hint
    cons["pow_algorithms"] = algos
    icon_url = str(settings.get("icon_url") if settings.get("icon_url") is not None else branding.get("icon_url") or "").strip()
    if icon_url:
        branding["icon_url"] = icon_url
        branding["qt_icon_url"] = icon_url
    builder["datadir_name"] = datadir
    builder["settings_adjusted"] = True
    builder["settings_tool"] = f"bloodstone-fork-builder/{APP_VERSION}"
    m["consensus"] = cons
    m["branding"] = branding
    m["builder"] = builder
    return m


def parse_set_overrides(items: List[str]) -> Dict[str, Any]:
    """Parse CLI --set key=value pairs."""
    out: Dict[str, Any] = {}
    for item in items or []:
        if "=" not in item:
            raise ValueError(f"--set expects key=value, got: {item}")
        k, v = item.split("=", 1)
        k = k.strip()
        v = v.strip()
        if k in ("p2p_port", "rpc_port", "block_time_seconds"):
            out[k] = int(v)
        elif k in ("block_reward", "premine"):
            out[k] = float(v)
        else:
            out[k] = v
    return out


def find_core_tarball(search_dirs: Optional[List[Path]] = None) -> Optional[Path]:
    dirs = search_dirs or [VENDOR_DIR, APP_ROOT, Path.cwd(), Path.home() / "Downloads"]
    for d in dirs:
        if not d.is_dir():
            continue
        for name in CORE_TARBALL_NAMES:
            p = d / name
            if p.is_file():
                return p
        for p in sorted(d.glob("bloodstone-core-*-source.tar.gz")):
            return p
    return None


def extract_core(tarball: Path, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    for child in list(dest.iterdir()):
        if child.is_dir() and ((child / "src").is_dir() or (child / "core" / "src").is_dir()):
            shutil.rmtree(child)
    with tarfile.open(tarball, "r:gz") as tf:
        tf.extractall(dest)
    for child in dest.iterdir():
        if child.is_dir() and (child / "src").is_dir():
            return child
        if child.is_dir() and (child / "core" / "src").is_dir():
            return child / "core"
    if (dest / "src").is_dir():
        return dest
    raise RuntimeError(f"could not find core source root inside {tarball}")


def _magic_bytes(hint: str, salt: str) -> List[int]:
    h = (hint or "").strip().lower()
    if re.fullmatch(r"[0-9a-f]{8}", h):
        return list(bytes.fromhex(h))
    digest = hashlib.sha256(f"magic:{(salt or 'fork')}".encode()).digest()
    return list(digest[:4])


def apply_manifest_to_tree(core_root: Path, manifest: Dict[str, Any]) -> Dict[str, Any]:
    """Patch Bloodstone core tree for this fork. Returns summary of changes."""
    cons = manifest.get("consensus") or {}
    builder = manifest.get("builder") or {}
    name = str(manifest.get("name") or "ForkCoin")
    ticker = str(manifest.get("ticker") or "FORK").upper()
    salt = str(cons.get("network_salt") or "")
    magic = _magic_bytes(str(cons.get("message_start_hint") or ""), salt)
    p2p = int(cons.get("p2p_port_hint") or 17333)
    rpc = int(cons.get("rpc_port_hint") or 18332)
    p2p = max(1024, min(65535, p2p))
    rpc = max(1024, min(65535, rpc))
    if rpc == p2p:
        rpc = min(65535, p2p + 1)
    datadir = str(builder.get("datadir_name") or f".{ticker.lower()}")
    reward = float(cons.get("block_reward") or 100)

    chainparams = core_root / "src" / "chainparams.cpp"
    if not chainparams.is_file():
        raise RuntimeError(f"missing {chainparams}")

    text = chainparams.read_text(encoding="utf-8", errors="replace")
    original = text

    text, _ = re.subn(
        r"pchMessageStart\[0\] = 0x[0-9a-fA-F]+;\s*\n\s*"
        r"pchMessageStart\[1\] = 0x[0-9a-fA-F]+;\s*\n\s*"
        r"pchMessageStart\[2\] = 0x[0-9a-fA-F]+;\s*\n\s*"
        r"pchMessageStart\[3\] = 0x[0-9a-fA-F]+;",
        (
            f"pchMessageStart[0] = 0x{magic[0]:02x};\n"
            f"        pchMessageStart[1] = 0x{magic[1]:02x};\n"
            f"        pchMessageStart[2] = 0x{magic[2]:02x};\n"
            f"        pchMessageStart[3] = 0x{magic[3]:02x}"
        ),
        text,
        count=1,
    )
    text, n2 = re.subn(r"nDefaultPort = 17333;", f"nDefaultPort = {p2p};", text, count=1)
    if n2 == 0:
        text, _ = re.subn(r"nDefaultPort = \d+;", f"nDefaultPort = {p2p};", text, count=1)

    # Block reward (era-0) if present
    text, _ = re.subn(
        r"consensus\.initialSubsidy = [^;]+;",
        f"consensus.initialSubsidy = {reward:g} * COIN;",
        text,
        count=1,
    )

    text = text.replace("Bloodstone independent chain relaunch", f"{name} fork of Bloodstone")
    text = text.replace("Bloodstone relaunch PoW era-0 reward", f"{name} PoW era-0 reward")
    if salt:
        text = re.sub(
            r'( = ")22/Jun/2026: Bloodstone[^"]*(")',
            rf'\1{name} fork salt={salt[:16]}\2',
            text,
            count=1,
        )

    if text != original:
        chainparams.write_text(text, encoding="utf-8")
    else:
        _log("warning: no textual patches applied - check source layout")

    conf_out = core_root / "fork-coin.conf.example"
    conf_body = f"""# {name} ({ticker}) - generated by Bloodstone Fork Builder {APP_VERSION}
# Fork ID: {manifest.get('fork_id','')}
# Network salt: {salt}
# Settings adjusted before compile: {bool(builder.get('settings_adjusted'))}

server=1
daemon=1
listen=1
txindex=1
port={p2p}
rpcport={rpc}
rpcbind=127.0.0.1
rpcallowip=127.0.0.1
rpcuser={ticker.lower()}rpc
rpcpassword=CHANGE_ME_{salt[:12] if salt else 'secret'}

# Parent lineage: Bloodstone multi-algo PoW
# Algorithms: {', '.join(cons.get('pow_algorithms') or [])}
# Datadir suggestion: {datadir}
"""
    conf_out.write_text(conf_body, encoding="utf-8")
    for c in (
        core_root / "share" / "examples" / "spacexpanse.conf",
        core_root / "share" / "examples" / "bloodstone.conf",
    ):
        if c.is_file():
            try:
                (c.parent / f"{ticker.lower()}.conf.example").write_text(conf_body, encoding="utf-8")
            except OSError:
                pass
            break

    branding = manifest.get("branding") or {}
    icon_url = branding.get("icon_url") or branding.get("qt_icon_url")
    # Local icon override
    local_icon = builder.get("local_icon_path")
    icon_bytes = None
    if local_icon and Path(local_icon).is_file():
        icon_bytes = Path(local_icon).read_bytes()
        _log(f"using local coin icon {local_icon}")
    elif icon_url:
        try:
            import urllib.request

            icon_bytes = urllib.request.urlopen(icon_url, timeout=30).read()
            _log(f"installed coin icon from {icon_url}")
        except Exception as exc:
            _log(f"warning: could not fetch coin icon ({exc})")
    if icon_bytes:
        targets = [
            core_root / "share" / "pixmaps" / "bitcoin.png",
            core_root / "src" / "qt" / "res" / "icons" / "bitcoin.png",
            core_root / "src" / "qt" / "res" / "icons" / "about.png",
            core_root / "FORK_COIN_ICON.png",
        ]
        for t in targets:
            t.parent.mkdir(parents=True, exist_ok=True)
            if t.suffix.lower() == ".png" and not icon_bytes.startswith(b"\x89PNG"):
                (core_root / "FORK_COIN_ICON.bin").write_bytes(icon_bytes)
                continue
            t.write_bytes(icon_bytes)

    (core_root / "FORK_MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (core_root / "FORK_BUILD_NOTES.txt").write_text(
        f"""{name} ({ticker}) - offline fork build notes
================================================

Fork Builder: {APP_VERSION}
Fork ID: {manifest.get('fork_id','')}
Status: {manifest.get('status','')}
Settings adjusted pre-compile: {bool(builder.get('settings_adjusted'))}

Consensus
---------
P2P port:     {p2p}
RPC port:     {rpc}
Magic bytes:  {' '.join(f'0x{b:02x}' for b in magic)}
Network salt: {salt}
Algos:        {', '.join(cons.get('pow_algorithms') or [])}
Block time:   {cons.get('block_time_seconds')} s
Block reward: {cons.get('block_reward')}
Premine:      {cons.get('premine')}
Datadir:      {datadir}

Build (Linux)
-------------
  ./autogen.sh
  ./configure --disable-tests --disable-bench --without-gui
  make -j$(nproc)

Run
---
  ./src/bloodstoned -conf=./fork-coin.conf.example -datadir=$HOME/{datadir}

Paid registration / store: https://bloodstonewallet.mytunnel.org/fork-lab/
""",
        encoding="utf-8",
    )

    return {
        "name": name,
        "ticker": ticker,
        "p2p_port": p2p,
        "rpc_port": rpc,
        "magic": [f"0x{b:02x}" for b in magic],
        "algos": cons.get("pow_algorithms") or [],
        "block_reward": reward,
        "datadir_name": datadir,
        "core_root": str(core_root),
        "conf_example": str(conf_out),
        "settings_adjusted": bool(builder.get("settings_adjusted")),
        "patched_chainparams": text != original,
    }


def _find_binaries(core_root: Path) -> Dict[str, Path]:
    """Locate built binaries under src/ (Bloodstone or SpaceXpanse names)."""
    src = core_root / "src"
    qt_src = src / "qt"
    mapping = {
        "daemon": ["bloodstoned", "spacexpansed", "bitcoind"],
        "cli": ["bloodstone-cli", "spacexpanse-cli", "bitcoin-cli"],
        "wallet_tool": ["bloodstone-wallet", "spacexpanse-wallet", "bitcoin-wallet"],
        "qt": ["bloodstone-qt", "spacexpanse-qt", "bitcoin-qt"],
    }
    found: Dict[str, Path] = {}
    for key, names in mapping.items():
        for name in names:
            for base in (src, qt_src):
                p = base / name
                if p.is_file() and os.access(p, os.X_OK):
                    found[key] = p
                    break
                # Windows .exe
                pexe = base / f"{name}.exe"
                if pexe.is_file():
                    found[key] = pexe
                    break
            if key in found:
                break
    return found


# ---------------------------------------------------------------------------
# Resilient dependency install: download missing libs as build errors appear
# ---------------------------------------------------------------------------

_INSTALLED_PACKAGES: set = set()
_APT_UPDATED = False


def _which_sudo() -> List[str]:
    """Return prefix for privileged commands (sudo when not root)."""
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        return []
    if shutil.which("sudo"):
        return ["sudo"]
    return []


def parse_missing_dep_tokens(output: str) -> List[str]:
    """Extract library / tool / header tokens from compiler & configure output."""
    if not output:
        return []
    tokens: List[str] = []
    patterns = [
        # pkg-config
        r"No package ['\"]([^'\"]+)['\"] found",
        r"Package ['\"]([^'\"]+)['\"], required by",
        r"Package requirements \(([^)]+)\) were not met",
        # missing headers
        r"fatal error:\s*([^\s:]+):\s*No such file or directory",
        r"fatal error:\s*['\"]([^'\"]+)['\"]:\s*No such file",
        r"([A-Za-z0-9_+\-./]+\.h(?:pp)?):\s*No such file or directory",
        r"Cannot find ([^\s]+)\.h\b",
        # linker
        r"cannot find -l([A-Za-z0-9_+\-.]+)",
        r"library not found for -l([A-Za-z0-9_+\-.]+)",
        r"ld:.*-l([A-Za-z0-9_+\-.]+).*not found",
        # configure / boost / bdb
        r"checking for ([A-Za-z0-9_+\-./]+)\.\.\. no",
        r"Could not find a? ?(?:usable )?(?:package |library )?([A-Za-z0-9_+\-./]+)",
        r"Unable to find (?:the )?([A-Za-z0-9_+\-./]+) (?:library|headers?|development)",
        r"cannot find ([A-Za-z0-9_+\-./]+) headers?",
        r"cannot find (?:the )?([A-Za-z0-9_+\-./]+) (?:library|headers?|development files)",
        r"(?:lib)?boost[_ ]?([a-z0-9_]+).*not found",
        r"Berkeley DB[^\n]*not found",
        r"libdb_cxx[^\n]*not found",
        # missing tools
        r"command not found:\s*([A-Za-z0-9_+\-]+)",
        r"([A-Za-z0-9_+\-]+):\s*command not found",
        r"No such file or directory: ['\"]?([A-Za-z0-9_+\-]+)['\"]?",
        r"error while loading shared libraries: lib([A-Za-z0-9_+\-]+)\.so",
        # apt-style
        r"Unable to locate package ([A-Za-z0-9_+\-.]+)",
        r"E: Package ['\"]([^'\"]+)['\"] has no installation candidate",
    ]
    for pat in patterns:
        for m in re.finditer(pat, output, re.IGNORECASE | re.MULTILINE):
            # Patterns without a capture group are whole-line flags handled below
            if not m.lastindex:
                continue
            raw = m.group(1).strip()
            if not raw or len(raw) > 80:
                continue
            # Drop noise words from accidental captures
            if raw.lower() in {"not", "found", "error", "the", "a", "an", "for", "and", "or"}:
                continue
            # Package requirements (a >= 1, b >= 2) → split names only
            if "," in raw:
                for part in re.split(r"[\s,]+", raw):
                    part = re.sub(r"[><=].*$", "", part).strip()
                    if part and part[0].isalpha() and len(part) > 1:
                        tokens.append(part)
                continue
            # Single token may still contain version ops: libevent >= 2.0
            if re.search(r"[><=]", raw):
                raw = re.sub(r"\s*[><=].*$", "", raw).strip()
            if " " in raw:
                # Prefer last path-like or library-looking word
                bits = [b for b in raw.split() if b[0].isalpha() and len(b) > 1]
                if not bits:
                    continue
                raw = bits[0] if len(bits) == 1 else bits[-1]
            tokens.append(raw)
    # Explicit whole-string flags for common configure failures
    low = output.lower()
    if "berkeley db" in low and ("not found" in low or "error" in low):
        tokens.extend(["db_cxx", "db_cxx.h"])
    if "boost" in low and (
        "not found" in low or "too old" in low or "cannot find" in low or "error" in low
    ):
        tokens.append("boost")
    if re.search(r"\bqt5?\b.*(?:not found|missing|required)", low) or "qmake" in low:
        tokens.append("qt5")
    if "openssl" in low and ("not found" in low or "cannot find" in low or "error" in low):
        tokens.append("openssl")
    if "libevent" in low and ("not found" in low or "cannot find" in low or "error" in low):
        tokens.append("libevent")
    if "miniupnpc" in low and ("not found" in low or "error" in low):
        tokens.append("miniupnpc")
    if ("zmq" in low or "zeromq" in low) and ("not found" in low or "error" in low):
        tokens.append("zmq")
    if "sqlite" in low and ("not found" in low or "error" in low):
        tokens.append("sqlite3")
    # de-dupe preserving order
    seen = set()
    out: List[str] = []
    for t in tokens:
        key = t.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(t)
    return out


def tokens_to_packages(tokens: List[str], *, with_gui: bool = False) -> List[str]:
    """Map free-form error tokens to apt package names."""
    pkgs: List[str] = []
    seen = set()

    def add(*names: str) -> None:
        for n in names:
            if n and n not in seen:
                seen.add(n)
                pkgs.append(n)

    for tok in tokens:
        t = tok.strip().strip("'\"")
        if not t:
            continue
        # strip version suffixes from pkg-config names: libevent_pthreads >= 2.0
        t = re.sub(r"\s*[><=].*$", "", t).strip()
        low = t.lower()
        # direct map
        if t in DEP_TOKEN_TO_PACKAGES:
            add(*DEP_TOKEN_TO_PACKAGES[t])
            continue
        if low in DEP_TOKEN_TO_PACKAGES:
            add(*DEP_TOKEN_TO_PACKAGES[low])
            continue
        # header path: event2/event.h → try full then basename
        if "/" in t or t.endswith(".h") or t.endswith(".hpp"):
            if t in DEP_TOKEN_TO_PACKAGES:
                add(*DEP_TOKEN_TO_PACKAGES[t])
                continue
            base = t.rsplit("/", 1)[-1]
            if base in DEP_TOKEN_TO_PACKAGES:
                add(*DEP_TOKEN_TO_PACKAGES[base])
                continue
            if low in DEP_TOKEN_TO_PACKAGES:
                add(*DEP_TOKEN_TO_PACKAGES[low])
                continue
        # libfoo → try libfoo-dev
        bare = low
        if bare.startswith("lib"):
            bare = bare[3:]
        bare = bare.replace("_", "-")
        candidates = [
            low,
            f"lib{bare}-dev" if not low.startswith("lib") else f"{low}-dev",
            f"lib{bare}-dev",
            f"{bare}-dev",
        ]
        matched = False
        for c in candidates:
            if c in DEP_TOKEN_TO_PACKAGES:
                add(*DEP_TOKEN_TO_PACKAGES[c])
                matched = True
                break
        if matched:
            continue
        # Heuristic: if it looks like a library name, try apt -dev package
        if re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_+\-.]{1,40}", t):
            if low.startswith("lib") and low.endswith("-dev"):
                add(low)
            elif low.startswith("lib"):
                add(f"{low}-dev")
            elif low.startswith("qt"):
                add("qtbase5-dev", "qttools5-dev")
            else:
                add(f"lib{low}-dev")

    if with_gui:
        for g in GUI_BUILD_PACKAGES:
            add(g)
    return pkgs


def apt_update(*, via_wsl: bool = False, distro: Optional[str] = None) -> None:
    """Run apt-get update once per process (best-effort)."""
    global _APT_UPDATED
    if _APT_UPDATED:
        return
    env_prefix = "export DEBIAN_FRONTEND=noninteractive; "
    if via_wsl or _is_windows():
        script = (
            env_prefix
            + "sudo apt-get update -qq || apt-get update -qq || true"
        )
        try:
            _run_wsl_bash(script, distro=distro, check=False)
            _APT_UPDATED = True
        except Exception as exc:
            _log(f"apt update via WSL skipped: {exc}")
        return
    if not shutil.which("apt-get"):
        return
    cmd = _which_sudo() + ["apt-get", "update", "-qq"]
    _log("$ " + " ".join(cmd))
    try:
        subprocess.run(cmd, check=False, env={**os.environ, "DEBIAN_FRONTEND": "noninteractive"})
        _APT_UPDATED = True
    except Exception as exc:
        _log(f"apt-get update failed (continuing): {exc}")


def install_apt_packages(
    packages: List[str],
    *,
    via_wsl: bool = False,
    distro: Optional[str] = None,
) -> List[str]:
    """Install apt packages that are not yet known-installed. Returns newly attempted list."""
    global _INSTALLED_PACKAGES, _APT_UPDATED
    to_install = [p for p in packages if p and p not in _INSTALLED_PACKAGES]
    if not to_install:
        return []
    # de-dupe preserve order
    seen = set()
    uniq: List[str] = []
    for p in to_install:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    to_install = uniq

    apt_update(via_wsl=via_wsl or _is_windows(), distro=distro)
    _log(f"Installing missing packages: {' '.join(to_install)}")

    if via_wsl or _is_windows():
        # Install one batch; tolerate individual failures for alternate package names
        pkg_str = " ".join(to_install)
        script = f"""
set +e
export DEBIAN_FRONTEND=noninteractive
sudo apt-get install -y -qq {pkg_str} 2>/tmp/fork-builder-apt.err
rc=$?
if [[ $rc -ne 0 ]]; then
  # try packages one-by-one so alternate names still install
  for p in {pkg_str}; do
    sudo apt-get install -y -qq "$p" 2>/dev/null || true
  done
fi
# enable universe if packages still missing (common on minimal WSL)
if ! dpkg -s build-essential >/dev/null 2>&1; then
  sudo add-apt-repository -y universe 2>/dev/null || true
  sudo apt-get update -qq || true
  sudo apt-get install -y -qq {pkg_str} || true
fi
exit 0
"""
        try:
            _run_wsl_bash(script, distro=distro, check=False)
        except Exception as exc:
            _log(f"WSL apt install warning: {exc}")
        _INSTALLED_PACKAGES.update(to_install)
        return to_install

    if not shutil.which("apt-get"):
        _log(
            "apt-get not available; cannot auto-install: "
            + ", ".join(to_install)
            + " — install these packages with your system package manager and re-run."
        )
        return []

    env = {**os.environ, "DEBIAN_FRONTEND": "noninteractive"}
    cmd = _which_sudo() + ["apt-get", "install", "-y", "-qq"] + to_install
    _log("$ " + " ".join(cmd))
    proc = subprocess.run(cmd, check=False, env=env, capture_output=True, text=True)
    if proc.returncode != 0:
        # Fall back to one-by-one so optional alternate names don't block others
        _log("batch apt install had errors; retrying packages individually…")
        if proc.stdout:
            _log(proc.stdout[-2000:])
        if proc.stderr:
            _log(proc.stderr[-2000:])
        for p in to_install:
            one = _which_sudo() + ["apt-get", "install", "-y", "-qq", p]
            r = subprocess.run(one, check=False, env=env, capture_output=True, text=True)
            if r.returncode == 0:
                _log(f"  installed {p}")
            else:
                _log(f"  could not install {p} (may be alternate name or already present)")
        # Try enabling universe once (minimal Ubuntu / WSL images)
        if shutil.which("add-apt-repository"):
            subprocess.run(
                _which_sudo() + ["add-apt-repository", "-y", "universe"],
                check=False,
                env=env,
                capture_output=True,
            )
            _APT_UPDATED = False
            apt_update(via_wsl=False)
            subprocess.run(cmd, check=False, env=env)
    _INSTALLED_PACKAGES.update(to_install)
    return to_install


def ensure_build_dependencies(*, with_gui: bool = False, via_wsl: bool = False, distro: Optional[str] = None) -> None:
    """Proactively install the known base (and optional Qt) toolchain."""
    pkgs = list(BASE_BUILD_PACKAGES)
    if with_gui:
        pkgs.extend(GUI_BUILD_PACKAGES)
    # Skip if make+g++ already present on native Linux and we already installed once
    if not via_wsl and not _is_windows():
        if shutil.which("make") and shutil.which("g++") and _INSTALLED_PACKAGES.issuperset(BASE_BUILD_PACKAGES[:5]):
            if with_gui and not any(p.startswith("qt") for p in _INSTALLED_PACKAGES):
                install_apt_packages(list(GUI_BUILD_PACKAGES), via_wsl=False)
            return
    install_apt_packages(pkgs, via_wsl=via_wsl or _is_windows(), distro=distro)


def install_deps_from_build_error(
    output: str,
    *,
    with_gui: bool = False,
    via_wsl: bool = False,
    distro: Optional[str] = None,
) -> List[str]:
    """Parse a failed build log, map to packages, install them. Returns packages attempted."""
    tokens = parse_missing_dep_tokens(output)
    if not tokens:
        # No specific token — still try a broader base set once
        _log("Build error had no clear missing-library token; ensuring base build packages…")
        pkgs = list(BASE_BUILD_PACKAGES)
        if with_gui:
            pkgs.extend(GUI_BUILD_PACKAGES)
    else:
        _log(f"Detected missing dep tokens: {', '.join(tokens[:20])}")
        pkgs = tokens_to_packages(tokens, with_gui=with_gui)
    if not pkgs:
        return []
    return install_apt_packages(pkgs, via_wsl=via_wsl, distro=distro)


def run_build_step_with_dep_retry(
    cmd: List[str],
    *,
    cwd: Path,
    env: Optional[Dict[str, str]] = None,
    with_gui: bool = False,
    via_wsl: bool = False,
    distro: Optional[str] = None,
    allow_configure_fallback: Optional[List[str]] = None,
    max_retries: int = MAX_DEP_RETRIES,
) -> None:
    """Run a build command; on failure install missing deps from the log and retry."""
    env = env or os.environ.copy()
    last_output = ""
    attempted_empty = 0
    for attempt in range(1, max_retries + 1):
        _log(f"$ {' '.join(cmd)}  (cwd={cwd}, attempt {attempt}/{max_retries})")
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(cwd),
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError as exc:
            missing = exc.filename or (cmd[0] if cmd else "tool")
            _log(f"missing executable: {missing}")
            installed = install_deps_from_build_error(
                f"{missing}: command not found\nNo such file or directory: {missing}",
                with_gui=with_gui,
                via_wsl=via_wsl,
                distro=distro,
            )
            if not installed:
                raise RuntimeError(
                    f"missing build tool {missing}. Could not auto-install dependencies."
                ) from exc
            continue

        out = (proc.stdout or "") + "\n" + (proc.stderr or "")
        last_output = out
        # Stream tail so users see progress
        for line in (proc.stdout or "").splitlines()[-30:]:
            _log(line)
        if proc.returncode == 0:
            return

        err_tail = (proc.stderr or proc.stdout or "")[-4000:]
        for line in err_tail.splitlines()[-40:]:
            _log(line)

        # configure-specific alternate flags (e.g. drop --with-incompatible-bdb)
        if allow_configure_fallback and attempt == 1:
            # still try deps first; fallback used after dep loop if needed
            pass

        installed = install_deps_from_build_error(
            out,
            with_gui=with_gui,
            via_wsl=via_wsl,
            distro=distro,
        )
        if not installed:
            attempted_empty += 1
            if attempted_empty >= 2 and allow_configure_fallback:
                _log(f"retry with fallback configure: {' '.join(allow_configure_fallback)}")
                cmd = allow_configure_fallback
                allow_configure_fallback = None
                attempted_empty = 0
                continue
            if attempted_empty >= 2:
                break
            # One more chance: force-install full base set
            install_apt_packages(
                list(BASE_BUILD_PACKAGES) + (list(GUI_BUILD_PACKAGES) if with_gui else []),
                via_wsl=via_wsl,
                distro=distro,
            )
            continue
        attempted_empty = 0

    # Final configure fallback if provided
    if allow_configure_fallback:
        _log(f"final fallback: {' '.join(allow_configure_fallback)}")
        proc = subprocess.run(
            allow_configure_fallback,
            cwd=str(cwd),
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
        if proc.returncode == 0:
            for line in (proc.stdout or "").splitlines()[-20:]:
                _log(line)
            return
        last_output = (proc.stdout or "") + "\n" + (proc.stderr or "")

    raise RuntimeError(
        f"build step failed after {max_retries} dep-install retries: {' '.join(cmd)}\n"
        f"Last output (tail):\n{(last_output or '')[-3000:]}"
    )


def download_url_to(url: str, dest: Path, *, timeout: int = 300) -> Path:
    """Download a URL to dest (creates parent dirs)."""
    import urllib.request

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".partial")
    _log(f"Downloading {url}")
    _log(f"  → {dest}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": f"BloodstoneForkBuilder/{APP_VERSION}"})
        with urllib.request.urlopen(req, timeout=timeout) as resp, open(tmp, "wb") as fh:
            shutil.copyfileobj(resp, fh)
        tmp.replace(dest)
    except Exception:
        if tmp.is_file():
            try:
                tmp.unlink()
            except OSError:
                pass
        raise
    _log(f"Downloaded {dest.stat().st_size} bytes")
    return dest


def ensure_core_tarball(search_dirs: Optional[List[Path]] = None) -> Path:
    """Find core source tarball locally, or download it into vendor/ when online."""
    found = find_core_tarball(search_dirs)
    if found:
        return found
    dest = VENDOR_DIR / CORE_TARBALL_NAMES[0]
    url = f"{PUBLIC_DOWNLOADS}/{CORE_TARBALL_NAMES[0]}"
    _log("Core source tarball not found locally — downloading…")
    try:
        return download_url_to(url, dest)
    except Exception as exc:
        raise RuntimeError(
            "No core source tarball found and download failed.\n"
            f"Place {CORE_TARBALL_NAMES[0]} in {VENDOR_DIR} or pass --tarball / --source.\n"
            f"Manual download: {url}\n"
            f"Error: {exc}"
        ) from exc


def _is_windows() -> bool:
    return platform.system() == "Windows" or sys.platform.startswith("win")


def _windows_to_wsl_path(path: Path) -> str:
    """C:\\Users\\x\\y -> /mnt/c/Users/x/y"""
    s = str(path.resolve())
    # Already a Unix path
    if s.startswith("/"):
        return s.replace("\\", "/")
    # Drive letter
    m = re.match(r"^([A-Za-z]):[\\/](.*)$", s)
    if m:
        drive = m.group(1).lower()
        rest = m.group(2).replace("\\", "/")
        return f"/mnt/{drive}/{rest}"
    return s.replace("\\", "/")


def detect_wsl() -> Dict[str, Any]:
    """Return whether Windows WSL has a usable Linux distro."""
    info: Dict[str, Any] = {
        "windows": _is_windows(),
        "wsl_exe": False,
        "has_distro": False,
        "default_distro": None,
        "distros": [],
        "error": None,
    }
    if not _is_windows():
        info["has_distro"] = True  # native Linux
        return info
    wsl = shutil.which("wsl") or shutil.which("wsl.exe")
    if not wsl:
        info["error"] = "wsl.exe not found — install Windows Subsystem for Linux"
        return info
    info["wsl_exe"] = True
    try:
        # -l -q lists distro names (one per line); may need UTF-16 decode on older WSL
        proc = subprocess.run(
            [wsl, "-l", "-q"],
            capture_output=True,
            timeout=20,
        )
        raw = proc.stdout or b""
        # WSL often emits UTF-16LE
        text = ""
        try:
            text = raw.decode("utf-16-le")
        except Exception:
            text = raw.decode("utf-8", errors="replace")
        # strip nulls leftover
        text = text.replace("\x00", "")
        names = [
            ln.strip()
            for ln in text.splitlines()
            if ln.strip() and not ln.strip().startswith("Windows Subsystem")
        ]
        # Filter junk lines
        names = [n for n in names if n and "no installed" not in n.lower()]
        info["distros"] = names
        if names:
            info["has_distro"] = True
            info["default_distro"] = names[0]
        else:
            # confirm empty
            err = (proc.stderr or b"").decode("utf-8", errors="replace")
            if "no installed distributions" in (text + err).lower():
                info["error"] = "WSL has no installed distributions"
            else:
                # try running a simple command
                t = subprocess.run(
                    [wsl, "-e", "echo", "ok"],
                    capture_output=True,
                    timeout=15,
                    text=True,
                )
                if t.returncode == 0 and "ok" in (t.stdout or ""):
                    info["has_distro"] = True
                    info["default_distro"] = None
                else:
                    info["error"] = (
                        (t.stderr or text or err or "WSL not usable").strip()[:300]
                    )
    except Exception as exc:
        info["error"] = str(exc)
    return info


def wsl_setup_instructions(core_root: Optional[Path] = None) -> str:
    wsl_path = _windows_to_wsl_path(core_root) if core_root else "/mnt/c/path/to/core"
    return f"""
================================================================
  Windows cannot compile C++ core natively in this toolkit.
  Install WSL2 + Ubuntu once, then re-run "Compile binaries".
================================================================

1) Open PowerShell or CMD **as Administrator** and run:

     wsl --install -d Ubuntu

   (Or: wsl --install   then reboot when prompted)

2) Reboot if Windows asks. Open "Ubuntu" from the Start menu,
   create a UNIX username/password when asked.

3) Build deps: Fork Builder installs them automatically as errors appear
   (sudo may ask once for your **Ubuntu** password — not Windows; typing is invisible).

   Optional one-shot pre-install inside Ubuntu:

     sudo apt update
     sudo apt install -y build-essential libtool autotools-dev automake \\
       pkg-config bsdmainutils python3 libssl-dev libevent-dev \\
       libboost-all-dev libdb5.3-dev libdb5.3++-dev
     # Qt optional: sudo apt install -y qtbase5-dev qttools5-dev libqrencode-dev
     # Forgot Ubuntu password? From Windows: wsl -u root → passwd USER → exit

4) Come back to Fork Builder and choose menu **9** again
   (Compile binaries locally now). It builds **inside WSL** and retries after
   apt-installing any missing libraries from the error log.

   Or from Ubuntu (resilient script):

     cd {wsl_path}
     bash /path/to/BloodstoneForkBuilder/scripts/wsl-build.sh

5) After binaries exist under src/, use menu **9 → c) Package only**
   to build VPS + Qt kits under work\\dist\\

Helper scripts next to this app:
  - SETUP-WSL-BUILD.bat   (prints these steps / launches wsl --install)
  - scripts\\wsl-build.sh  (resilient build inside Ubuntu on the patched tree)

Docs: https://learn.microsoft.com/windows/wsl/install
""".strip()


def _run_wsl_bash(
    script: str,
    *,
    distro: Optional[str] = None,
    check: bool = True,
) -> subprocess.CompletedProcess:
    wsl = shutil.which("wsl") or shutil.which("wsl.exe")
    if not wsl:
        raise RuntimeError("wsl.exe not found")
    cmd = [wsl]
    if distro:
        cmd.extend(["-d", distro])
    cmd.extend(["-e", "bash", "-lc", script])
    _log(f"$ wsl {'-d ' + distro + ' ' if distro else ''}bash -lc …")
    return subprocess.run(cmd, check=check)


def build_via_wsl(
    core_root: Path, jobs: int = 0, *, with_gui: bool = False
) -> Dict[str, Path]:
    """Compile the patched core inside WSL2 Ubuntu (Windows host).

    Resilient: pre-installs base deps, then on configure/make failures parses the
    log, apt-installs missing libraries, and retries (up to MAX_DEP_RETRIES).
    """
    wsl_info = detect_wsl()
    if not wsl_info.get("has_distro"):
        raise RuntimeError(wsl_setup_instructions(core_root))

    distro = wsl_info.get("default_distro")
    jobs = jobs or max(1, (os.cpu_count() or 2) // 2)
    wsl_core = _windows_to_wsl_path(core_root)
    gui_flag = "--with-gui=qt5" if with_gui else "--without-gui"
    base_pkgs = " ".join(BASE_BUILD_PACKAGES)
    gui_pkgs = " ".join(GUI_BUILD_PACKAGES) if with_gui else ""
    qt_targets = "bloodstone-qt" if with_gui else ""

    # Resilient bash build loop: install missing packages as errors appear
    prep = f"""
set +e
export DEBIAN_FRONTEND=noninteractive
MAX_RETRIES={MAX_DEP_RETRIES}
CORE="{wsl_core}"
JOBS={jobs}
GUI_FLAG="{gui_flag}"
BASE_PKGS="{base_pkgs}"
GUI_PKGS="{gui_pkgs}"

install_pkgs() {{
  local pkgs="$1"
  [[ -z "$pkgs" ]] && return 0
  echo ">>> Installing packages: $pkgs"
  sudo apt-get update -qq 2>/dev/null || apt-get update -qq 2>/dev/null || true
  # batch first
  sudo apt-get install -y -qq $pkgs 2>/tmp/fb-apt.err
  if [[ $? -ne 0 ]]; then
    for p in $pkgs; do
      sudo apt-get install -y -qq "$p" 2>/dev/null && echo "  ok $p" || echo "  skip $p"
    done
    sudo add-apt-repository -y universe 2>/dev/null || true
    sudo apt-get update -qq 2>/dev/null || true
    sudo apt-get install -y -qq $pkgs 2>/dev/null || true
  fi
}}

map_error_to_pkgs() {{
  # stdin: build log → stdout: space-separated apt packages
  local log
  log=$(cat)
  local pkgs=""
  echo "$log" | grep -Eiq "openssl|libssl|ssl\\.h" && pkgs="$pkgs libssl-dev"
  echo "$log" | grep -Eiq "libevent|event2/" && pkgs="$pkgs libevent-dev"
  echo "$log" | grep -Eiq "boost" && pkgs="$pkgs libboost-all-dev"
  echo "$log" | grep -Eiq "db_cxx|berkeley db|libdb" && pkgs="$pkgs libdb5.3++-dev libdb5.3-dev libdb++-dev libdb-dev"
  echo "$log" | grep -Eiq "miniupnpc" && pkgs="$pkgs libminiupnpc-dev"
  echo "$log" | grep -Eiq "zmq\\.h|libzmq" && pkgs="$pkgs libzmq3-dev"
  echo "$log" | grep -Eiq "sqlite3" && pkgs="$pkgs libsqlite3-dev"
  echo "$log" | grep -Eiq "qrencode" && pkgs="$pkgs libqrencode-dev"
  echo "$log" | grep -Eiq "protobuf|protoc" && pkgs="$pkgs libprotobuf-dev protobuf-compiler"
  echo "$log" | grep -Eiq "qt5|qmake|Qt5|lrelease|QApplication" && pkgs="$pkgs qtbase5-dev qttools5-dev qttools5-dev-tools"
  echo "$log" | grep -Eiq "g\\+\\+|gcc:|build-essential|make: command" && pkgs="$pkgs build-essential"
  echo "$log" | grep -Eiq "automake|autoconf|libtool|autoreconf|aclocal" && pkgs="$pkgs automake autoconf libtool autotools-dev"
  echo "$log" | grep -Eiq "pkg-config|pkgconf" && pkgs="$pkgs pkg-config"
  echo "$log" | grep -Eiq "hexdump" && pkgs="$pkgs bsdmainutils bsdextrautils"
  # pkg-config: No package 'foo' found
  local pc
  pc=$(echo "$log" | sed -n "s/.*No package '\\([^']*\\)' found.*/\\1/p" | head -20)
  for name in $pc; do
    case "$name" in
      libssl|openssl) pkgs="$pkgs libssl-dev" ;;
      libevent*) pkgs="$pkgs libevent-dev" ;;
      Qt5*|Qt*) pkgs="$pkgs qtbase5-dev qttools5-dev" ;;
      libzmq*) pkgs="$pkgs libzmq3-dev" ;;
      sqlite3) pkgs="$pkgs libsqlite3-dev" ;;
      *) pkgs="$pkgs lib${{name}}-dev ${{name}}-dev" ;;
    esac
  done
  # fatal error: foo.h
  local hdrs
  hdrs=$(echo "$log" | sed -n "s/.*fatal error: \\([^:]*\\): No such file.*/\\1/p" | head -20)
  for h in $hdrs; do
    case "$h" in
      openssl/*) pkgs="$pkgs libssl-dev" ;;
      event2/*) pkgs="$pkgs libevent-dev" ;;
      boost/*) pkgs="$pkgs libboost-all-dev" ;;
      db_cxx.h|db.h) pkgs="$pkgs libdb5.3++-dev libdb++-dev" ;;
      zmq.h) pkgs="$pkgs libzmq3-dev" ;;
      sqlite3.h) pkgs="$pkgs libsqlite3-dev" ;;
      miniupnpc.h) pkgs="$pkgs libminiupnpc-dev" ;;
      qrencode.h) pkgs="$pkgs libqrencode-dev" ;;
    esac
  done
  # cannot find -lfoo
  local libs
  libs=$(echo "$log" | sed -n "s/.*cannot find -l\\([A-Za-z0-9_+-]*\\).*/\\1/p" | head -20)
  for l in $libs; do
    pkgs="$pkgs lib${{l}}-dev"
  done
  echo "$pkgs" | tr ' ' '\\n' | sed '/^$/d' | sort -u | tr '\\n' ' '
}}

echo ">>> Pre-installing base build dependencies (sudo may ask for Ubuntu password)…"
install_pkgs "$BASE_PKGS $GUI_PKGS"

cd "$CORE" || {{ echo "ERROR: cannot cd to $CORE"; ls -la; exit 2; }}
if [[ ! -f autogen.sh ]]; then
  echo "ERROR: autogen.sh not found in $CORE"
  ls -la
  exit 2
fi
chmod +x autogen.sh || true

run_step() {{
  local label="$1"
  shift
  local attempt=1
  local logf="/tmp/fb-build-$$.log"
  while [[ $attempt -le $MAX_RETRIES ]]; do
    echo ">>> $label (attempt $attempt/$MAX_RETRIES): $*"
    "$@" >"$logf" 2>&1
    local rc=$?
    tail -n 40 "$logf"
    if [[ $rc -eq 0 ]]; then
      return 0
    fi
    echo ">>> $label failed (exit $rc); scanning log for missing libraries…"
    local need
    need=$(map_error_to_pkgs < "$logf")
    if [[ -z "$need" ]]; then
      echo ">>> No package mapping from log; reinstalling base toolchain…"
      need="$BASE_PKGS $GUI_PKGS"
    fi
    echo ">>> Missing deps mapped to: $need"
    install_pkgs "$need"
    attempt=$((attempt + 1))
  done
  echo ">>> $label failed after $MAX_RETRIES retries"
  tail -n 80 "$logf"
  return 1
}}

run_step "autogen" ./autogen.sh || exit 1

# configure with BDB flag, then without
if ! run_step "configure" ./configure --disable-tests --disable-bench $GUI_FLAG --with-incompatible-bdb; then
  echo ">>> configure with --with-incompatible-bdb failed; trying without…"
  run_step "configure-fallback" ./configure --disable-tests --disable-bench $GUI_FLAG || exit 1
fi

run_step "make" make -j"$JOBS" || exit 1
make -j"$JOBS" bloodstoned bloodstone-cli {qt_targets} || true

echo "WSL build finished in $CORE"
ls -la src/bloodstoned src/bloodstone-cli src/qt/bloodstone-qt 2>/dev/null || ls -la src/ | head
"""
    _log(f"Building inside WSL at {wsl_core}")
    _log(f"with_gui={with_gui} jobs={jobs} distro={distro or '(default)'}")
    _log("Resilient mode: missing libraries will be apt-installed as errors appear.")
    try:
        _run_wsl_bash(prep, distro=distro, check=True)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            "WSL build failed after auto-installing dependencies.\n\n"
            + wsl_setup_instructions(core_root)
            + f"\n\n(exit code {exc.returncode})"
        ) from exc
    except FileNotFoundError as exc:
        raise RuntimeError(wsl_setup_instructions(core_root)) from exc

    found = _find_binaries(core_root)
    for key, path in found.items():
        _log(f"built {key}: {path}")
    if "daemon" not in found and "cli" not in found:
        raise RuntimeError(
            "WSL compile finished but no bloodstoned/bloodstone-cli under src/.\n"
            "Open Ubuntu, cd to the core path, and run make manually — see SETUP-WSL-BUILD.bat"
        )
    return found


def build_linux(
    core_root: Path, jobs: int = 0, *, with_gui: bool = False
) -> Dict[str, Path]:
    """Compile core. On Windows this uses WSL2 Ubuntu (required).

    On Linux: proactively installs base deps, then on each failed step parses the
    error log, downloads/installs missing libraries via apt, and retries.
    """
    if _is_windows():
        _log("Windows host detected — compiling via WSL2 (not native MSVC).")
        return build_via_wsl(core_root, jobs=jobs, with_gui=with_gui)

    jobs = jobs or max(1, (os.cpu_count() or 2) // 2)
    env = os.environ.copy()

    _log("Ensuring build dependencies (will auto-install missing libs as errors appear)…")
    try:
        ensure_build_dependencies(with_gui=with_gui, via_wsl=False)
    except Exception as exc:
        _log(f"Pre-install warning (will still try and fix from errors): {exc}")

    configure = [
        "bash",
        "configure",
        "--disable-tests",
        "--disable-bench",
        "--with-incompatible-bdb",
    ]
    if with_gui:
        configure.append("--with-gui=qt5")
    else:
        configure.append("--without-gui")
    configure_fallback = [
        "bash",
        "configure",
        "--disable-tests",
        "--disable-bench",
        "--with-gui=qt5" if with_gui else "--without-gui",
    ]
    make_targets = ["bloodstoned", "bloodstone-cli"]
    if with_gui:
        make_targets.append("bloodstone-qt")

    run_build_step_with_dep_retry(
        ["bash", "autogen.sh"],
        cwd=core_root,
        env=env,
        with_gui=with_gui,
    )
    run_build_step_with_dep_retry(
        configure,
        cwd=core_root,
        env=env,
        with_gui=with_gui,
        allow_configure_fallback=configure_fallback,
    )
    run_build_step_with_dep_retry(
        ["make", f"-j{jobs}"],
        cwd=core_root,
        env=env,
        with_gui=with_gui,
    )
    # Optional focused make of named targets (ignore failure if names differ)
    try:
        subprocess.run(
            ["make", f"-j{jobs}"] + make_targets,
            cwd=str(core_root),
            env=env,
            check=False,
        )
    except Exception:
        pass
    found = _find_binaries(core_root)
    for key, path in found.items():
        _log(f"built {key}: {path}")
    if "daemon" not in found and "cli" not in found:
        # Last-ditch: one more dep sweep + make
        _log("No binaries yet — final dependency sweep + make…")
        install_apt_packages(
            list(BASE_BUILD_PACKAGES) + (list(GUI_BUILD_PACKAGES) if with_gui else []),
            via_wsl=False,
        )
        try:
            run_build_step_with_dep_retry(
                ["make", f"-j{jobs}"] + make_targets,
                cwd=core_root,
                env=env,
                with_gui=with_gui,
                max_retries=3,
            )
        except RuntimeError:
            pass
        found = _find_binaries(core_root)
    if "daemon" not in found and "cli" not in found:
        raise RuntimeError(
            "compile finished but no bloodstoned/bloodstone-cli found under src/. "
            "Check the log above for unresolved missing libraries."
        )
    return found


def _write_text(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _copy_binary(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    try:
        os.chmod(dest, 0o755)
    except OSError:
        pass
    # strip if available (Linux)
    if platform.system() == "Linux" and dest.suffix != ".exe":
        try:
            subprocess.run(["strip", "-s", str(dest)], check=False, capture_output=True)
        except Exception:
            pass


def parse_products(raw: Any) -> List[str]:
    """Normalize product list from CLI/env/JSON."""
    if raw is None or raw == "" or raw is False:
        return list(DEFAULT_PRODUCTS)
    if isinstance(raw, (list, tuple, set)):
        items = [str(x).strip().lower() for x in raw if str(x).strip()]
    else:
        items = [
            p.strip().lower()
            for p in str(raw).replace(";", ",").split(",")
            if p.strip()
        ]
    # aliases
    aliases = {
        "server": "vps",
        "vps-server": "vps",
        "server-kit": "vps",
        "wallet": "qt",
        "qt-wallet": "qt",
        "desktop": "qt",
        "android": "android-full-node",
        "android-full": "android-full-node",
        "android-node": "android-full-node",
        "full-node-apk": "android-full-node",
        "apk": "android-full-node",
        "apk-full": "android-full-node",
        "pruned-apk": "android-pruned-node",
        "android-pruned": "android-pruned-node",
        "edge": "edge-node",
        "mobile": "edge-node",
        "all": "full",
        "everything": "full",
        "binaries": "daemon",
    }
    out: List[str] = []
    for p in items:
        p = aliases.get(p, p)
        if p not in PRODUCT_CHOICES:
            raise ValueError(
                f"unknown product {p!r}; choose from: {', '.join(PRODUCT_CHOICES)}"
            )
        if p not in out:
            out.append(p)
    if not out:
        return list(DEFAULT_PRODUCTS)
    # full implies vps+qt packaging
    if "full" in out:
        for extra in ("vps", "qt"):
            if extra not in out:
                out.append(extra)
    return out


def package_distribution_kits(
    core_root: Path,
    manifest: Dict[str, Any],
    work: Path,
    *,
    binaries: Optional[Dict[str, Path]] = None,
    products: Optional[Any] = None,
) -> Dict[str, Any]:
    """Build selected product kits (individual apps/binaries or full bundle).

    Products (select with --products / --only):
      daemon, cli, vps, qt, android-full-node, android-pruned-node, edge-node, full

    Layout under work/dist/ (only selected kits are written):
      {TICKER}-vps-server-kit/
      {TICKER}-qt-wallet-kit/
      {TICKER}-android-full-node-kit/   start the coin from a phone (full node)
      {TICKER}-android-pruned-node-kit/
      {TICKER}-edge-node-kit/           multi-device edge profile
      {TICKER}-binaries/                raw daemon/cli only
      {TICKER}-full-distribution/
    """
    want = set(parse_products(products))
    cons = manifest.get("consensus") or {}
    name = str(manifest.get("name") or "ForkCoin")
    ticker = str(manifest.get("ticker") or "FORK").upper()
    p2p = int(cons.get("p2p_port_hint") or 17333)
    rpc = int(cons.get("rpc_port_hint") or 18332)
    datadir = str((manifest.get("builder") or {}).get("datadir_name") or f".{ticker.lower()}")
    salt = str(cons.get("network_salt") or "")
    algos = cons.get("pow_algorithms") or []
    if isinstance(algos, str):
        algos_s = algos
    else:
        algos_s = ", ".join(str(a) for a in algos)

    bins = binaries or _find_binaries(core_root)
    dist = work / "dist"
    if dist.is_dir():
        shutil.rmtree(dist)
    dist.mkdir(parents=True, exist_ok=True)

    conf_body = f"""# {name} ({ticker}) — generated by Bloodstone Fork Builder {APP_VERSION}
# Fork ID: {manifest.get('fork_id', '')}
# Network salt: {salt}

server=1
daemon=1
listen=1
txindex=1
port={p2p}
rpcport={rpc}
rpcbind=127.0.0.1
rpcallowip=127.0.0.1
rpcuser={ticker.lower()}rpc
rpcpassword=CHANGE_ME_{salt[:12] if salt else 'secret'}

# Optional seed (your VPS later):
# addnode=YOUR.VPS.IP:{p2p}

# Algorithms: {algos_s}
# Datadir: ~/{datadir}
"""

    systemd_unit = f"""[Unit]
Description={name} ({ticker}) full node
After=network.target

[Service]
Type=simple
User={ticker.lower()}
WorkingDirectory=/home/{ticker.lower()}
ExecStart=/usr/local/bin/{ticker.lower()}d -conf=/etc/{ticker.lower()}/{ticker.lower()}.conf -datadir=/var/lib/{ticker.lower()}
Restart=on-failure
RestartSec=5
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
"""

    start_sh = f"""#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
DATADIR="${{DATADIR:-$HOME/{datadir}}}"
mkdir -p "$DATADIR"
CONF="$ROOT/{ticker.lower()}.conf"
if [[ ! -f "$CONF" ]]; then
  cp "$ROOT/{ticker.lower()}.conf.example" "$CONF"
  echo "Edit $CONF (rpcpassword) then re-run."
fi
exec "$ROOT/bin/{ticker.lower()}d" -conf="$CONF" -datadir="$DATADIR" "$@"
"""

    cli_sh = f"""#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
DATADIR="${{DATADIR:-$HOME/{datadir}}}"
CONF="$ROOT/{ticker.lower()}.conf"
if [[ ! -f "$CONF" ]]; then CONF="$ROOT/{ticker.lower()}.conf.example"; fi
exec "$ROOT/bin/{ticker.lower()}-cli" -conf="$CONF" -datadir="$DATADIR" "$@"
"""

    def kit_readme(kind: str) -> str:
        return f"""{name} ({ticker}) — {kind}
====================================
Built with Bloodstone Fork Builder {APP_VERSION}
Fork ID: {manifest.get('fork_id', '')}
Parent: Bloodstone multi-algo PoW ({algos_s})

Ports: P2P {p2p} · RPC {rpc}
Datadir: ~/{datadir}

VPS server kit
--------------
  bin/{ticker.lower()}d          full node daemon
  bin/{ticker.lower()}-cli       RPC CLI
  {ticker.lower()}.conf.example  sample conf
  start-{ticker.lower()}.sh      start daemon
  {ticker.lower()}-cli.sh        wrapper for CLI
  systemd/{ticker.lower()}.service

Qt wallet kit
-------------
  bin/{ticker.lower()}-qt        desktop wallet (when compiled with GUI)
  On Windows: build Qt under MSYS2/WSL, or patch parent Qt kit branding.

Usual extras
------------
  FORK_MANIFEST.json   consensus + branding from Fork Lab
  DOWNLOADS.txt        parent-chain reference downloads
  BOOTSTRAP.txt        how to seed chain data
  MINING.txt           stratum / pool notes for your fork

Quick start (Linux VPS)
-----------------------
  1. Upload this folder to your VPS
  2. chmod +x bin/* *.sh
  3. Edit {ticker.lower()}.conf (set rpcpassword)
  4. ./start-{ticker.lower()}.sh
  5. ./{ticker.lower()}-cli.sh getblockchaininfo

Fork Lab: {PUBLIC_ROOT}/fork-lab/
Downloads: {PUBLIC_DOWNLOADS}/
"""

    downloads_txt = "Parent Bloodstone reference downloads (not your fork binaries):\n\n"
    for label, fn in USUAL_DOWNLOAD_ITEMS:
        downloads_txt += f"  - {label}\n    {PUBLIC_DOWNLOADS}/{fn}\n"
    downloads_txt += f"\nFork Lab store: {PUBLIC_ROOT}/fork-lab/store/\n"
    downloads_txt += f"Your coin compile profile: {PUBLIC_ROOT}/wallet/profile\n"

    bootstrap_txt = f"""Bootstrap / first sync for {ticker}
================================

Your fork has a unique network salt / magic — do NOT copy Bloodstone mainnet
blocks/ onto this coin's datadir (chain will reject foreign genesis).

For parent STONE bootstrap only (reference):
  {PUBLIC_DOWNLOADS}/bloodstone-chain-bootstrap-latest.tar.gz

For {ticker}:
  1. Start your own seed node on a VPS with open P2P port {p2p}
  2. Point other nodes: addnode=YOUR.SEED.IP:{p2p}
  3. Mine the first blocks (solo or your pool) to grow the chain
  4. Optionally publish a snapshot of blocks+chainstate once live
"""

    mining_txt = f"""Mining {ticker}
==============

PoW algorithms: {algos_s}
Block time hint: {cons.get('block_time_seconds')} s
Block reward: {cons.get('block_reward')}

After your VPS node is syncing:
  - Solo: point a miner at 127.0.0.1:{rpc} (getblocktemplate) or use stratum you host
  - Pool: run your own stratum against {ticker.lower()}d RPC
  - Do not use Bloodstone public pool ports for a separate fork chain

Parent pool reference (STONE only): {PUBLIC_ROOT}/mining/
"""

    kits: Dict[str, Path] = {}
    vps: Optional[Path] = None
    qt_dir: Optional[Path] = None
    qt_notes = ""

    # --- Raw binaries only ---
    if "daemon" in want or "cli" in want:
        bin_name = f"{ticker.lower()}-binaries"
        bdir = dist / bin_name
        (bdir / "bin").mkdir(parents=True)
        if "daemon" in want and bins.get("daemon"):
            _copy_binary(bins["daemon"], bdir / "bin" / f"{ticker.lower()}d")
        if "cli" in want and bins.get("cli"):
            _copy_binary(bins["cli"], bdir / "bin" / f"{ticker.lower()}-cli")
        _write_text(
            bdir / "README.txt",
            f"{name} ({ticker}) — raw binaries only\n"
            f"Products: {', '.join(sorted(want & {'daemon', 'cli'}))}\n"
            f"P2P {p2p} · RPC {rpc}\n",
        )
        (bdir / "FORK_MANIFEST.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        kits["binaries"] = bdir

    # --- VPS server kit ---
    if "vps" in want or "full" in want:
        vps_name = f"{ticker.lower()}-vps-server-kit"
        vps = dist / vps_name
        (vps / "bin").mkdir(parents=True)
        (vps / "systemd").mkdir(parents=True)
        if bins.get("daemon"):
            _copy_binary(bins["daemon"], vps / "bin" / f"{ticker.lower()}d")
        if bins.get("cli"):
            _copy_binary(bins["cli"], vps / "bin" / f"{ticker.lower()}-cli")
        if bins.get("wallet_tool"):
            _copy_binary(bins["wallet_tool"], vps / "bin" / f"{ticker.lower()}-wallet")
        _write_text(vps / f"{ticker.lower()}.conf.example", conf_body)
        _write_text(vps / f"start-{ticker.lower()}.sh", start_sh)
        _write_text(vps / f"{ticker.lower()}-cli.sh", cli_sh)
        try:
            os.chmod(vps / f"start-{ticker.lower()}.sh", 0o755)
            os.chmod(vps / f"{ticker.lower()}-cli.sh", 0o755)
        except OSError:
            pass
        _write_text(vps / "systemd" / f"{ticker.lower()}.service", systemd_unit)
        _write_text(vps / "README.txt", kit_readme("VPS server kit"))
        _write_text(vps / "DOWNLOADS.txt", downloads_txt)
        _write_text(vps / "BOOTSTRAP.txt", bootstrap_txt)
        _write_text(vps / "MINING.txt", mining_txt)
        (vps / "FORK_MANIFEST.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        conf_src = core_root / "fork-coin.conf.example"
        if conf_src.is_file():
            shutil.copy2(conf_src, vps / "fork-coin.conf.example")
        kits["vps_server"] = vps

    # --- Qt wallet kit ---
    if "qt" in want or "full" in want:
        qt_name = f"{ticker.lower()}-qt-wallet-kit"
        qt_dir = dist / qt_name
        (qt_dir / "bin").mkdir(parents=True)
        if bins.get("qt"):
            _copy_binary(bins["qt"], qt_dir / "bin" / f"{ticker.lower()}-qt")
            qt_notes = f"Desktop wallet binary included: bin/{ticker.lower()}-qt\n"
        else:
            qt_notes = (
                "Qt wallet binary not present yet.\n"
                "Compile with GUI on Linux:\n"
                "  sudo apt install qtbase5-dev qttools5-dev libqrencode-dev\n"
                f"  cd {core_root}\n"
                "  ./configure --disable-tests --disable-bench --with-gui=qt5 --with-incompatible-bdb\n"
                "  make -j$(nproc) bloodstone-qt\n"
                "Then re-run: python3 fork_builder.py package --products qt\n"
                f"Or use parent reference Qt and rebrand: {PUBLIC_DOWNLOADS}/bloodstone-qt-0.7.4-win64.exe\n"
            )
        if bins.get("cli"):
            _copy_binary(bins["cli"], qt_dir / "bin" / f"{ticker.lower()}-cli")
        _write_text(qt_dir / f"{ticker.lower()}.conf.example", conf_body)
        _write_text(qt_dir / "README.txt", kit_readme("Qt wallet kit") + "\n" + qt_notes)
        _write_text(qt_dir / "DOWNLOADS.txt", downloads_txt)
        _write_text(qt_dir / "QT-BUILD.txt", qt_notes)
        (qt_dir / "FORK_MANIFEST.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        icon = core_root / "FORK_COIN_ICON.png"
        if icon.is_file():
            shutil.copy2(icon, qt_dir / "coin-icon.png")
        kits["qt_wallet"] = qt_dir

    # --- Edge / Android node kits (individual apps — no full dist required) ---
    edge_profile = (
        (manifest.get("edge_node") or manifest.get("mobile_node") or {})
        if isinstance(manifest, dict)
        else {}
    )
    if not edge_profile:
        edge_profile = {
            "schema": "bloodstone/edge-node-profile/v1",
            "fork_id": manifest.get("fork_id"),
            "name": name,
            "ticker": ticker,
            "network": {
                "p2p_port": p2p,
                "rpc_port": rpc,
                "network_salt": salt,
                "message_start_hint": cons.get("message_start_hint"),
                "pow_algorithms": algos,
            },
            "local_node_modes": ["lan-client", "pruned", "full", "mesh"],
            "device_agnostic": True,
            "multi_device": True,
        }

    def _write_edge_kit(product: str, mode: str, title: str) -> None:
        kit_key = product.replace("-", "_")
        folder = dist / f"{ticker.lower()}-{product}-kit"
        folder.mkdir(parents=True, exist_ok=True)
        prof = dict(edge_profile)
        prof["recommended_edge_mode"] = mode
        prof["recommended_phone_mode"] = mode  # legacy
        prof["product"] = product
        prof["start_mode"] = mode
        prof["client_download"] = f"{PUBLIC_DOWNLOADS}/"
        (folder / "FORK_EDGE_PROFILE.json").write_text(
            json.dumps(prof, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (folder / "FORK_MANIFEST.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        readme = f"""{name} ({ticker}) — {title}
====================================
Product: {product}
Start mode: {mode}  (full node | pruned | mesh)

This kit is an *individual app deliverable* — you do not need the full
distribution or a VPS to start the coin on a phone / tablet / desktop client.

Quick start (Android full node example)
---------------------------------------
  1. Install Bloodstone miner APK (or your rebranded fork client) from Downloads
  2. Open the app → Coordinator / Fork profile (or edge-node import)
  3. Load FORK_EDGE_PROFILE.json (or paste the profile URL from Fork Lab)
  4. Set Local node mode → Full chain  (for android-full-node)
  5. Tap Start full node — chain syncs on-device; LAN stratum opens for rigs

Rebuild a branded full-node APK (optional advanced)
---------------------------------------------------
  Parent project: bloodstone-miner-android (Capacitor)
  - Copy FORK_EDGE_PROFILE.json into app assets or deep-link import
  - Brand name/ticker/icon from FORK_MANIFEST.json
  - Build only the full-node shell (same local bloodstoned binary path as Bloodstone)
  - Ship as: {ticker.lower()}-android-full-node.apk

No VPS required to launch. Public seed servers are optional later.

Fork Lab: {PUBLIC_ROOT}/fork-lab/
Edge profile API: {PUBLIC_ROOT}/api/fork-lab/coins/{manifest.get('fork_id') or ''}/mobile-profile
"""
        _write_text(folder / "README.txt", readme)
        _write_text(
            folder / "IMPORT.txt",
            "Import FORK_EDGE_PROFILE.json into any Bloodstone client that supports\n"
            "edge-node / mobile-profile load. Multi-device: phone, tablet, desktop, Pi.\n",
        )
        # tiny import helper
        helper = f"""#!/usr/bin/env bash
# Print profile path for adb push / copy into client
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
echo "Profile: $ROOT/FORK_EDGE_PROFILE.json"
echo "Mode: {mode}"
echo "Import in Bloodstone client → Fork profile / edge-node load"
"""
        _write_text(folder / "show-profile.sh", helper)
        try:
            os.chmod(folder / "show-profile.sh", 0o755)
        except OSError:
            pass
        kits[kit_key] = folder

    if "android-full-node" in want:
        _write_edge_kit(
            "android-full-node",
            "full",
            "Android FULL NODE starter (start the coin from a phone)",
        )
    if "android-pruned-node" in want:
        _write_edge_kit(
            "android-pruned-node",
            "pruned",
            "Android pruned node starter",
        )
    if "edge-node" in want:
        _write_edge_kit(
            "edge-node",
            str(edge_profile.get("recommended_edge_mode") or "pruned"),
            "Multi-device edge node profile kit",
        )

    # --- Full distribution ---
    if "full" in want and vps is not None and vps.is_dir():
        full_name = f"{ticker.lower()}-full-distribution"
        full = dist / full_name
        if full.exists():
            shutil.rmtree(full)
        shutil.copytree(vps, full)
        if bins.get("qt"):
            _copy_binary(bins["qt"], full / "bin" / f"{ticker.lower()}-qt")
        _write_text(full / "QT-BUILD.txt", qt_notes or "Qt not included in this build.\n")
        _write_text(
            full / "README.txt",
            kit_readme("full distribution (VPS + wallet + usual items)"),
        )
        # bundle edge profile for convenience
        if "android-full-node" in kits:
            shutil.copy2(
                kits["android_full_node"] / "FORK_EDGE_PROFILE.json",
                full / "FORK_EDGE_PROFILE.full.json",
            )
        kits["full"] = full

    # Archives
    archives: Dict[str, str] = {}
    for key, folder in kits.items():
        tar_path = dist / f"{folder.name}.tar.gz"
        with tarfile.open(tar_path, "w:gz") as tf:
            tf.add(folder, arcname=folder.name)
        archives[f"{key}_tar"] = str(tar_path)
        try:
            zip_path = dist / f"{folder.name}.zip"
            shutil.make_archive(str(dist / folder.name), "zip", dist, folder.name)
            archives[f"{key}_zip"] = str(zip_path)
        except Exception as exc:
            _log(f"zip skipped for {folder.name}: {exc}")

    index = {
        "ok": True,
        "app": "bloodstone-fork-builder",
        "version": APP_VERSION,
        "ticker": ticker,
        "name": name,
        "products": sorted(want),
        "product_choices": list(PRODUCT_CHOICES),
        "core_root": str(core_root),
        "binaries_found": {k: str(v) for k, v in bins.items()},
        "kits": {k: str(v) for k, v in kits.items()},
        "archives": archives,
        "dist_dir": str(dist),
        "usual_downloads": [
            {"label": a, "url": f"{PUBLIC_DOWNLOADS}/{b}"} for a, b in USUAL_DOWNLOAD_ITEMS
        ],
        "note": (
            "Select individual products with --products / --only. "
            "Examples: --only android-full-node  |  --products vps,cli  |  --products full. "
            "android-full-node = start the coin from a phone (full chain on device)."
        ),
    }
    (dist / "INDEX.json").write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    _log(f"distribution kits ready under {dist} (products={sorted(want)})")
    for k, p in archives.items():
        _log(f"  archive {k}: {p}")
    return index


def resolve_core_root(work: Path) -> Path:
    summary = work / "apply-summary.json"
    if summary.is_file():
        data = json.loads(summary.read_text(encoding="utf-8"))
        root = Path(data.get("core_root") or "")
        if root.is_dir() and (root / "src").is_dir():
            return root
    # search extract dir
    extract = work / "src-extract"
    if extract.is_dir():
        for child in extract.iterdir():
            if child.is_dir() and (child / "src").is_dir():
                return child
    raise RuntimeError(
        "No patched core tree found. Run prepare first (menu 4) so work/src-extract/ exists."
    )


def cmd_compile_local(args: argparse.Namespace) -> int:
    """Compile binaries locally and package VPS + Qt + full kits."""
    work = Path(args.work or DEFAULT_WORK)
    work.mkdir(parents=True, exist_ok=True)
    # Ensure prepare has been done
    if getattr(args, "manifest", None):
        # allow one-shot prepare+compile
        ns = argparse.Namespace(
            manifest=args.manifest,
            tarball=getattr(args, "tarball", None),
            source=getattr(args, "source", None),
            work=str(work),
            settings=getattr(args, "settings", None),
            set=getattr(args, "set", None) or [],
            interactive=bool(getattr(args, "interactive", False)),
            local_icon=getattr(args, "local_icon", None),
        )
        if not (work / "apply-summary.json").is_file() or getattr(args, "reprepare", False):
            cmd_prepare(ns)

    core_root = Path(args.source).resolve() if getattr(args, "source", None) else resolve_core_root(work)
    with_gui = bool(getattr(args, "with_gui", False))
    jobs = int(getattr(args, "jobs", 0) or 0)
    package_only = bool(getattr(args, "package_only", False))

    binaries: Dict[str, Path] = {}
    if not package_only:
        _log("=== Compile binaries locally now ===")
        _log(f"core: {core_root}")
        _log(f"with_gui (Qt wallet): {with_gui}")
        if _is_windows():
            wsl_info = detect_wsl()
            if not wsl_info.get("has_distro"):
                guide = wsl_setup_instructions(core_root)
                try:
                    (work / "WSL-BUILD-GUIDE.txt").write_text(guide + "\n", encoding="utf-8")
                    (APP_ROOT / "WSL-BUILD-GUIDE.txt").write_text(guide + "\n", encoding="utf-8")
                except OSError:
                    pass
                raise RuntimeError(guide)
            _log(
                f"WSL distro: {wsl_info.get('default_distro') or 'default'} "
                f"(path {_windows_to_wsl_path(core_root)})"
            )
        binaries = build_linux(core_root, jobs=jobs, with_gui=with_gui)
    else:
        binaries = _find_binaries(core_root)
        _log(f"package-only; found binaries: {list(binaries.keys())}")
        if not binaries and _is_windows():
            _log(
                "No binaries found yet. Install WSL Ubuntu, compile, then package — "
                "see SETUP-WSL-BUILD.bat or menu 9 → w."
            )

    # Load manifest for packaging
    manifest_path = work / "edited-manifest.json"
    if getattr(args, "manifest", None) and Path(args.manifest).is_file():
        manifest = load_manifest(Path(args.manifest))
        if (work / "coin-settings.json").is_file():
            settings = json.loads((work / "coin-settings.json").read_text(encoding="utf-8"))
            if isinstance(settings, dict):
                manifest = apply_settings_to_manifest(manifest, settings)
    elif manifest_path.is_file():
        manifest = load_manifest(manifest_path)
    else:
        # minimal from summary
        summary = json.loads((work / "apply-summary.json").read_text(encoding="utf-8"))
        manifest = {
            "name": summary.get("name") or "ForkCoin",
            "ticker": summary.get("ticker") or "FORK",
            "fork_id": "",
            "consensus": {
                "p2p_port_hint": summary.get("p2p_port"),
                "rpc_port_hint": summary.get("rpc_port"),
                "pow_algorithms": summary.get("algos") or [],
                "block_reward": summary.get("block_reward"),
            },
            "builder": {"datadir_name": summary.get("datadir_name")},
        }

    products = getattr(args, "products", None) or getattr(args, "only", None)
    if getattr(args, "only", None) and not getattr(args, "products", None):
        products = args.only
    index = package_distribution_kits(
        core_root, manifest, work, binaries=binaries, products=products
    )
    _log("")
    _log("=== Kits ready ===")
    _log(f"  Dist folder: {index['dist_dir']}")
    _log(f"  Products: {', '.join(index.get('products') or [])}")
    for k, v in (index.get("kits") or {}).items():
        _log(f"  {k}: {v}")
    _log("")
    _log("Individual products (examples):")
    _log("  --only android-full-node     # phone full-node starter kit only")
    _log("  --products vps,cli           # server node + cli only")
    _log("  --products qt                # desktop wallet kit only")
    _log("  --products full              # classic full distribution")
    (work / "compile-local-result.json").write_text(
        json.dumps(index, indent=2) + "\n", encoding="utf-8"
    )
    return 0


def cmd_package(args: argparse.Namespace) -> int:
    """Package selected kits from already-compiled binaries (no rebuild)."""
    args.package_only = True
    if not getattr(args, "with_gui", False):
        args.with_gui = False
    return cmd_compile_local(args)


def _resolve_manifest(args: argparse.Namespace) -> Tuple[Dict[str, Any], Path]:
    """Load manifest and apply any CLI settings overrides; save edited copy."""
    work = Path(args.work or DEFAULT_WORK)
    work.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest(Path(args.manifest))
    settings = extract_settings(manifest)

    if getattr(args, "settings", None):
        sp = Path(args.settings)
        extra = json.loads(sp.read_text(encoding="utf-8"))
        if not isinstance(extra, dict):
            raise ValueError("--settings must be a JSON object")
        settings.update(extra)

    if getattr(args, "set", None):
        settings.update(parse_set_overrides(list(args.set)))

    if getattr(args, "local_icon", None):
        settings["local_icon_path"] = str(Path(args.local_icon).resolve())
        # pass through builder
        manifest.setdefault("builder", {})["local_icon_path"] = settings["local_icon_path"]

    if getattr(args, "interactive", False):
        settings = interactive_edit_settings(settings)

    manifest = apply_settings_to_manifest(manifest, settings)
    if getattr(args, "local_icon", None):
        manifest.setdefault("builder", {})["local_icon_path"] = str(Path(args.local_icon).resolve())

    edited_path = work / "edited-manifest.json"
    edited_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    settings_path = work / "coin-settings.json"
    settings_path.write_text(
        json.dumps(extract_settings(manifest), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _log(f"saved adjusted settings -> {settings_path}")
    _log(f"saved edited manifest -> {edited_path}")
    return manifest, work


def interactive_edit_settings(settings: Dict[str, Any]) -> Dict[str, Any]:
    """CLI interactive editor (readline prompts)."""
    print("\n=== Adjust coin settings before compile ===")
    print("Press Enter to keep the current value.\n")
    out = dict(settings)
    for key, label, kind in EDITABLE_FIELDS:
        cur = out.get(key, "")
        raw = input(f"  {label} [{cur}]: ").strip()
        if not raw:
            continue
        if kind == "int":
            out[key] = int(raw)
        elif kind == "float":
            out[key] = float(raw)
        else:
            out[key] = raw
    print()
    return out


def cmd_prepare(args: argparse.Namespace) -> int:
    manifest, work = _resolve_manifest(args)

    if args.source:
        core_root = Path(args.source).resolve()
        if not (core_root / "src").is_dir():
            raise SystemExit(f"--source must point at core tree with src/: {core_root}")
    else:
        if args.tarball:
            tarball = Path(args.tarball).resolve()
            if not tarball.is_file():
                raise SystemExit(f"--tarball not found: {tarball}")
        else:
            # Local search, then auto-download into vendor/ when online
            try:
                tarball = ensure_core_tarball()
            except RuntimeError as exc:
                raise SystemExit(str(exc)) from exc
        _log(f"extracting {tarball}")
        core_root = extract_core(tarball, work / "src-extract")

    summary = apply_manifest_to_tree(core_root, manifest)
    out_json = work / "apply-summary.json"
    out_json.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    _log(json.dumps(summary, indent=2))
    _log(f"patched tree ready: {core_root}")
    _log(f"next: python3 fork_builder.py build --source {core_root}")
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    core_root = Path(args.source).resolve()
    if not (core_root / "src").is_dir():
        raise SystemExit(f"invalid --source {core_root}")
    build_linux(
        core_root,
        jobs=int(args.jobs or 0),
        with_gui=bool(getattr(args, "with_gui", False)),
    )
    return 0


def cmd_all(args: argparse.Namespace) -> int:
    rc = cmd_prepare(args)
    if rc != 0:
        return rc
    work = Path(args.work or DEFAULT_WORK)
    summary_path = work / "apply-summary.json"
    core_root = Path(json.loads(summary_path.read_text())["core_root"])
    args.source = str(core_root)
    return cmd_build(args)


def cmd_show(args: argparse.Namespace) -> int:
    manifest = load_manifest(Path(args.manifest))
    settings = extract_settings(manifest)
    print(json.dumps(settings, indent=2, sort_keys=True))
    return 0


def cmd_menu(_args: argparse.Namespace = None) -> int:
    """Interactive console wizard - works on Windows embeddable Python (no tkinter)."""
    print()
    print("=" * 60)
    print(f"  Bloodstone Fork Builder {APP_VERSION}")
    print("  Offline settings editor + source patcher for Fork Lab coins")
    print("=" * 60)
    print(f"  App folder: {APP_ROOT}")
    core = find_core_tarball()
    print(f"  Core source: {core if core else 'NOT FOUND (place tarball in vendor/)'}")
    print()

    manifest_path: Optional[Path] = None
    # Prefer examples or work
    for cand in (
        DEFAULT_WORK / "edited-manifest.json",
        APP_ROOT / "examples" / "sample-manifest.json",
        APP_ROOT / "my-fork.json",
    ):
        if cand.is_file():
            manifest_path = cand
            break

    while True:
        print("-" * 60)
        print("Menu:")
        print("  1) Load Fork Lab manifest JSON")
        print("  2) Show current coin settings")
        print("  3) Edit coin settings (interactive)")
        print("  4) Apply settings + patch core source  (prepare)")
        print("  5) Fetch / verify core source tarball info")
        print("  6) Save compile profile JSON only")
        print("  7) Open README / build help")
        print("  8) Download LRGK sample from Fork Lab API (needs internet)")
        print("  9) Compile / package products  -> VPS, Qt, full node on device/phone, …")
        print("     (auto-installs missing libraries as build errors appear)")
        print("  a) Make a full node on your device or phone  (Android full-node kit only)")
        print("  0) Exit")
        print("-" * 60)
        if manifest_path:
            print(f"  Active manifest: {manifest_path}")
        else:
            print("  Active manifest: (none - choose 1)")
        choice = input("Select [0-9 / a]: ").strip() or "0"

        if choice == "0":
            print("Bye.")
            return 0

        if choice == "1":
            raw = input(
                f"Path to manifest JSON [{manifest_path or 'examples/sample-manifest.json'}]: "
            ).strip()
            p = Path(raw) if raw else (manifest_path or APP_ROOT / "examples" / "sample-manifest.json")
            if not p.is_file():
                print(f"  ERROR: file not found: {p}")
                continue
            try:
                load_manifest(p)
            except Exception as exc:
                print(f"  ERROR: invalid manifest: {exc}")
                continue
            manifest_path = p.resolve()
            print(f"  Loaded OK: {manifest_path}")
            continue

        if choice == "5":
            t = find_core_tarball()
            if t:
                print(f"  Found: {t} ({t.stat().st_size} bytes)")
                try:
                    with tarfile.open(t, "r:gz") as tf:
                        names = tf.getnames()[:5]
                    print(f"  Looks like a valid .tar.gz (e.g. {names[0] if names else '?'})")
                except Exception as exc:
                    print(f"  WARNING: could not read tarball: {exc}")
            else:
                print("  No core tarball in vendor/.")
                print(f"  Download: {PUBLIC_DOWNLOADS}/bloodstone-core-source-latest.tar.gz")
                print("  Save as: vendor/bloodstone-core-source-latest.tar.gz")
            continue

        if choice == "7":
            readme = APP_ROOT / "README.md"
            win = APP_ROOT / "README-WINDOWS.txt"
            for p in (win, readme):
                if p.is_file():
                    print(p.read_text(encoding="utf-8", errors="replace")[:4000])
                    break
            print()
            print("Linux full compile after prepare:")
            print("  cd work/src-extract/<core>/ && ./autogen.sh && ./configure --disable-tests --without-gui && make -j$(nproc)")
            print("Windows: use WSL2 Ubuntu for the C++ compile step; prepare/patch works natively.")
            continue

        if choice == "8":
            fid = input("Fork id (default LRGK e9d304f3379e96859acd131f): ").strip() or (
                "e9d304f3379e96859acd131f"
            )
            url = (
                os.environ.get("BLOODSTONE_PUBLIC_ROOT", "https://bloodstonewallet.mytunnel.org")
                .rstrip("/")
                + f"/api/fork-lab/coins/{fid}"
            )
            try:
                import urllib.request

                raw = urllib.request.urlopen(url, timeout=30).read()
                data = json.loads(raw.decode())
                fork = data.get("fork") or data
                # Build a minimal manifest file
                out = DEFAULT_WORK
                out.mkdir(parents=True, exist_ok=True)
                mp = out / f"{fork.get('ticker') or fid}-manifest.json"
                if data.get("fork") and not data.get("consensus"):
                    # wrap API fork into manifest-ish shape for load_manifest
                    payload = data
                else:
                    payload = data
                mp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
                # validate via loader
                load_manifest(mp)
                manifest_path = mp
                print(f"  Saved {mp}")
            except Exception as exc:
                print(f"  ERROR: {exc}")
            continue

        if not manifest_path or not manifest_path.is_file():
            print("  Load a manifest first (option 1).")
            continue

        if choice == "2":
            try:
                m = load_manifest(manifest_path)
                print(json.dumps(extract_settings(m), indent=2, sort_keys=True))
            except Exception as exc:
                print(f"  ERROR: {exc}")
            continue

        if choice == "3":
            try:
                m = load_manifest(manifest_path)
                s = interactive_edit_settings(extract_settings(m))
                m2 = apply_settings_to_manifest(m, s)
                DEFAULT_WORK.mkdir(parents=True, exist_ok=True)
                sp = DEFAULT_WORK / "coin-settings.json"
                mp = DEFAULT_WORK / "edited-manifest.json"
                sp.write_text(json.dumps(extract_settings(m2), indent=2, sort_keys=True) + "\n", encoding="utf-8")
                mp.write_text(json.dumps(m2, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                manifest_path = mp
                print(f"  Saved settings -> {sp}")
                print(f"  Saved manifest -> {mp}")
            except Exception as exc:
                print(f"  ERROR: {exc}")
            continue

        if choice == "6":
            try:
                m = load_manifest(manifest_path)
                s = extract_settings(m)
                DEFAULT_WORK.mkdir(parents=True, exist_ok=True)
                sp = DEFAULT_WORK / "coin-settings.json"
                sp.write_text(json.dumps(s, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                print(f"  Wrote {sp}")
            except Exception as exc:
                print(f"  ERROR: {exc}")
            continue

        if choice == "4":
            try:
                # Build a fake args namespace for prepare
                ns = argparse.Namespace(
                    manifest=str(manifest_path),
                    tarball=None,
                    source=None,
                    work=str(DEFAULT_WORK),
                    settings=None,
                    set=[],
                    interactive=False,
                    local_icon=None,
                )
                # If edited settings exist, prefer them
                sp = DEFAULT_WORK / "coin-settings.json"
                if sp.is_file():
                    ns.settings = str(sp)
                rc = cmd_prepare(ns)
                if rc == 0:
                    print()
                    print("  PREPARE OK - source tree patched.")
                    print("  Next: menu 9) Compile binaries locally now")
                    print("  (produces VPS server kit + Qt wallet kit + usual items)")
                else:
                    print(f"  prepare failed with code {rc}")
            except SystemExit as exc:
                print(f"  ERROR: {exc}")
            except Exception as exc:
                print(f"  ERROR: {exc}")
            continue

        if choice in ("9", "a", "A"):
            # Option a = one-shot "full node on device/phone" (no sub-menu).
            direct_device_full_node = choice.lower() == "a"
            with_gui = False
            package_only = False
            products: Optional[str] = None
            if direct_device_full_node:
                print()
                print("=== Make a full node on your device or phone ===")
                print("  Packaging android-full-node kit (profile + import docs).")
                print("  No VPS required. No C++ compile required for this kit.")
                products = "android-full-node"
                package_only = True
            else:
                print()
                print("=== Compile / package individual products ===")
                print("  Pick only what you need:")
                print("    1) Make a full node on your device or phone  (android-full-node)")
                print("    2) Pruned node on phone / device             (android-pruned-node)")
                print("    3) Edge node on any device (phone/desktop/Pi) (edge-node)")
                print("    4) VPS / server kit                           (vps)")
                print("    5) Desktop Qt wallet kit                      (qt)")
                print("    6) Raw binaries only                          (daemon,cli)")
                print("    7) Full distribution bundle                   (full)")
                print("    8) Default set (vps + qt + full + phone full-node + edge)")
                print()
                if _is_windows():
                    wsl_info = detect_wsl()
                    if wsl_info.get("has_distro"):
                        print(
                            f"  Windows + WSL OK — will build inside "
                            f"{wsl_info.get('default_distro') or 'default distro'}."
                        )
                    else:
                        print("  *** WSL is not ready on this PC ***")
                        print("  " + (wsl_info.get("error") or "No Linux distro installed."))
                        print("  You can still package profile kits (1/2/3) without compiling.")
                if not (DEFAULT_WORK / "apply-summary.json").is_file():
                    print("  No patched tree yet — will run prepare first when compiling…")
                print("  Extra:")
                print("    g) also build Qt GUI when compiling (for products that need qt)")
                print("    c) package only (skip compile)")
                if _is_windows():
                    print("    w) Print WSL2 install guide")
                print("    q) Cancel")
                sub = input(
                    "  Product choice [1-8/g/c/w/q] (default 1 = full node on device/phone): "
                ).strip().lower() or "1"
                if sub == "q":
                    continue
                if sub == "w":
                    core_hint = None
                    try:
                        core_hint = resolve_core_root(DEFAULT_WORK)
                    except Exception:
                        pass
                    print()
                    print(wsl_setup_instructions(core_hint))
                    try:
                        guide = APP_ROOT / "WSL-BUILD-GUIDE.txt"
                        guide.write_text(wsl_setup_instructions(core_hint) + "\n", encoding="utf-8")
                        print(f"\n  Also saved: {guide}")
                    except OSError:
                        pass
                    continue
                product_map = {
                    "1": "android-full-node",
                    "2": "android-pruned-node",
                    "3": "edge-node",
                    "4": "vps",
                    "5": "qt",
                    "6": "daemon,cli",
                    "7": "full",
                    "8": ",".join(DEFAULT_PRODUCTS),
                    "a": "android-full-node",
                }
                products = product_map.get(sub)
                if sub == "g":
                    products = "vps,qt,full"
                    with_gui = True
                elif sub == "c":
                    products = input(
                        f"  Products to package [{','.join(DEFAULT_PRODUCTS)}]: "
                    ).strip() or ",".join(DEFAULT_PRODUCTS)
                    package_only = True
                elif products is None:
                    products = sub
            try:
                prods = parse_products(products)
            except ValueError as exc:
                print(f"  ERROR: {exc}")
                continue
            needs_compile = any(p in prods for p in ("vps", "qt", "full", "daemon", "cli"))
            if needs_compile and not package_only and _is_windows() and not detect_wsl().get("has_distro"):
                print()
                print(wsl_setup_instructions())
                print()
                print("  Tip: choose profile-only products (1/2/3) or install WSL to compile daemons.")
                continue
            if not manifest_path:
                print("  Load a manifest first (menu 1).")
                continue
            try:
                ns = argparse.Namespace(
                    manifest=str(manifest_path),
                    tarball=None,
                    source=None,
                    work=str(DEFAULT_WORK),
                    settings=str(DEFAULT_WORK / "coin-settings.json")
                    if (DEFAULT_WORK / "coin-settings.json").is_file()
                    else None,
                    set=[],
                    interactive=False,
                    local_icon=None,
                    with_gui=with_gui or ("qt" in prods),
                    package_only=package_only or not needs_compile,
                    jobs=0,
                    reprepare=False,
                    products=products,
                    only=None,
                )
                rc = cmd_compile_local(ns)
                if rc == 0:
                    print()
                    print("  DONE. Open work/dist/ for selected product kits.")
                    print(
                        "  Full node on device/phone: open *-android-full-node-kit/, "
                        "import FORK_EDGE_PROFILE.json → Start full node."
                    )
            except SystemExit as exc:
                print(f"  ERROR: {exc}")
            except Exception as exc:
                print(f"  ERROR: {exc}")
            continue

        print("  Unknown choice.")


def cmd_gui(_args: argparse.Namespace) -> int:
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, scrolledtext, ttk
    except ImportError:
        _log("tkinter not available - starting console menu instead")
        return cmd_menu(_args)

    root = tk.Tk()
    root.title(f"Bloodstone Fork Builder {APP_VERSION}")
    root.geometry("860x820")
    try:
        root.minsize(760, 680)
    except tk.TclError:
        pass

    main = tk.Frame(root, padx=10, pady=10)
    main.pack(fill=tk.BOTH, expand=True)

    tk.Label(main, text="Fork Builder - adjust settings, then compile", font=("", 13, "bold")).pack(
        anchor="w"
    )
    tk.Label(
        main,
        text=(
            "Load your Fork Lab manifest, tweak coin settings, pick products "
            "(including full node on your device/phone), then patch/compile offline."
        ),
        wraplength=820,
        justify="left",
    ).pack(anchor="w", pady=(0, 6))

    paths = tk.Frame(main)
    paths.pack(fill=tk.X)
    manifest_var = tk.StringVar()
    tarball_var = tk.StringVar()
    found = find_core_tarball()
    if found:
        tarball_var.set(str(found))

    def path_row(parent, label, var, browse):
        r = tk.Frame(parent)
        r.pack(fill=tk.X, pady=2)
        tk.Label(r, text=label, width=12, anchor="w").pack(side=tk.LEFT)
        tk.Entry(r, textvariable=var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        tk.Button(r, text="Browse...", command=browse).pack(side=tk.LEFT)

    def browse_manifest():
        p = filedialog.askopenfilename(filetypes=[("JSON", "*.json"), ("All", "*.*")])
        if p:
            manifest_var.set(p)
            load_settings_into_form()

    def browse_tarball():
        p = filedialog.askopenfilename(filetypes=[("tar.gz", "*.tar.gz"), ("All", "*.*")])
        if p:
            tarball_var.set(p)

    path_row(paths, "Manifest", manifest_var, browse_manifest)
    path_row(paths, "Core source", tarball_var, browse_tarball)

    # --- Settings form ---
    settings_frame = tk.LabelFrame(main, text="Coin settings (edit before compile)", padx=8, pady=6)
    settings_frame.pack(fill=tk.X, pady=8)

    field_vars: Dict[str, Any] = {}
    algo_vars = {
        "neoscrypt": tk.BooleanVar(value=True),
        "yespower": tk.BooleanVar(value=True),
        "sha256d": tk.BooleanVar(value=True),
    }

    grid = tk.Frame(settings_frame)
    grid.pack(fill=tk.X)

    def add_field(row: int, key: str, label: str, width: int = 28):
        tk.Label(grid, text=label, anchor="w", width=18).grid(row=row, column=0, sticky="w", pady=2)
        var = tk.StringVar()
        ent = tk.Entry(grid, textvariable=var, width=width)
        ent.grid(row=row, column=1, sticky="we", pady=2, padx=4)
        field_vars[key] = var
        return var

    add_field(0, "name", "Coin name")
    add_field(1, "ticker", "Ticker")
    add_field(2, "p2p_port", "P2P port")
    add_field(3, "rpc_port", "RPC port")
    add_field(4, "block_time_seconds", "Block time (sec)")
    add_field(5, "block_reward", "Block reward")
    add_field(6, "premine", "Premine")
    add_field(7, "network_salt", "Network salt")
    add_field(8, "message_start_hint", "Magic (8 hex)")
    add_field(9, "datadir_name", "Datadir name")
    add_field(10, "website", "Website")
    add_field(11, "description", "Description")
    add_field(12, "icon_url", "Icon URL")

    local_icon_var = tk.StringVar()
    field_vars["local_icon_path"] = local_icon_var
    ir = tk.Frame(grid)
    ir.grid(row=13, column=0, columnspan=2, sticky="we", pady=2)
    tk.Label(ir, text="Local icon file", width=18, anchor="w").pack(side=tk.LEFT)
    tk.Entry(ir, textvariable=local_icon_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)

    def browse_icon():
        p = filedialog.askopenfilename(
            filetypes=[("Images", "*.png *.jpg *.jpeg *.webp *.gif"), ("All", "*.*")]
        )
        if p:
            local_icon_var.set(p)

    tk.Button(ir, text="Browse...", command=browse_icon).pack(side=tk.LEFT)

    ar = tk.Frame(settings_frame)
    ar.pack(fill=tk.X, pady=4)
    tk.Label(ar, text="Algorithms").pack(side=tk.LEFT)
    for algo, var in algo_vars.items():
        tk.Checkbutton(ar, text=algo, variable=var).pack(side=tk.LEFT, padx=6)

    def settings_from_form() -> Dict[str, Any]:
        s = {k: v.get().strip() for k, v in field_vars.items()}
        # ints/floats
        for k in ("p2p_port", "rpc_port", "block_time_seconds"):
            if s.get(k) != "":
                s[k] = int(s[k])
        for k in ("block_reward", "premine"):
            if s.get(k) != "":
                s[k] = float(s[k])
        s["algos"] = [a for a, v in algo_vars.items() if v.get()]
        if s.get("local_icon_path"):
            s["local_icon_path"] = s["local_icon_path"]
        return s

    def load_settings_into_form():
        try:
            if not manifest_var.get():
                return
            m = load_manifest(Path(manifest_var.get()))
            s = extract_settings(m)
            for k, var in field_vars.items():
                if k == "local_icon_path":
                    continue
                var.set(str(s.get(k, "")))
            algos = [a.strip().lower() for a in str(s.get("algos") or "").split(",") if a.strip()]
            for a, var in algo_vars.items():
                var.set(a in algos if algos else True)
            append(f"Loaded settings for {s.get('ticker')} from manifest.")
        except Exception as exc:
            messagebox.showerror("Load failed", str(exc))

    tk.Button(settings_frame, text="Reload settings from manifest", command=load_settings_into_form).pack(
        anchor="w", pady=4
    )

    log = scrolledtext.ScrolledText(main, height=12)
    log.pack(fill=tk.BOTH, expand=True, pady=6)

    def append(msg: str):
        log.insert(tk.END, msg + "\n")
        log.see(tk.END)
        root.update_idletasks()

    def run_prepare_build(do_build: bool):
        try:
            if not manifest_var.get():
                raise ValueError("choose a Fork Lab manifest JSON")
            # Build a temporary settings file from the form
            work = DEFAULT_WORK
            work.mkdir(parents=True, exist_ok=True)
            form_settings = settings_from_form()
            settings_path = work / "coin-settings.json"
            settings_path.write_text(json.dumps(form_settings, indent=2) + "\n", encoding="utf-8")

            ns = argparse.Namespace(
                manifest=manifest_var.get(),
                tarball=tarball_var.get() or None,
                source=None,
                work=str(work),
                jobs=max(1, (os.cpu_count() or 2) // 2),
                settings=str(settings_path),
                set=[],
                interactive=False,
                local_icon=form_settings.get("local_icon_path") or None,
            )
            import builtins

            real_print = builtins.print

            def gui_print(*a, **k):
                append(" ".join(str(x) for x in a))

            builtins.print = gui_print
            try:
                cmd_prepare(ns)
                if do_build:
                    summary = json.loads((work / "apply-summary.json").read_text())
                    ns.source = summary["core_root"]
                    cmd_build(ns)
            finally:
                builtins.print = real_print
            messagebox.showinfo(
                "Done",
                "Finished.\n\n"
                f"Edited settings: {work / 'coin-settings.json'}\n"
                f"Edited manifest: {work / 'edited-manifest.json'}\n"
                f"Work folder: {work}",
            )
        except Exception as exc:
            append(f"ERROR: {exc}")
            messagebox.showerror("Error", str(exc))

    def save_settings_only():
        try:
            if not manifest_var.get():
                raise ValueError("load a manifest first")
            work = DEFAULT_WORK
            work.mkdir(parents=True, exist_ok=True)
            form_settings = settings_from_form()
            m = load_manifest(Path(manifest_var.get()))
            if form_settings.get("local_icon_path"):
                m.setdefault("builder", {})["local_icon_path"] = form_settings["local_icon_path"]
            m = apply_settings_to_manifest(m, form_settings)
            (work / "coin-settings.json").write_text(
                json.dumps(extract_settings(m), indent=2) + "\n", encoding="utf-8"
            )
            (work / "edited-manifest.json").write_text(
                json.dumps(m, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            # also offer save-as
            p = filedialog.asksaveasfilename(
                defaultextension=".json",
                initialfile=f"{form_settings.get('ticker','coin')}-settings.json",
                filetypes=[("JSON", "*.json")],
            )
            if p:
                Path(p).write_text(json.dumps(extract_settings(m), indent=2) + "\n", encoding="utf-8")
                append(f"Saved settings to {p}")
            messagebox.showinfo("Saved", f"Settings written to {work}")
        except Exception as exc:
            messagebox.showerror("Error", str(exc))

    # --- Product selection (what to package / compile) ---
    products_frame = tk.LabelFrame(
        main,
        text="What to build / package (select products)",
        padx=8,
        pady=6,
    )
    products_frame.pack(fill=tk.X, pady=(4, 6))
    tk.Label(
        products_frame,
        text=(
            "Check what you need. Phone / device full node does not require a VPS. "
            "Profile kits (device/phone) can package without compiling daemons."
        ),
        wraplength=820,
        justify="left",
        fg="#333",
    ).pack(anchor="w", pady=(0, 4))

    # Default: phone full-node + edge + vps so the device option is visible and selected.
    product_vars: Dict[str, Any] = {}
    # Order products with device/phone options first for discoverability.
    gui_product_order = (
        "android-full-node",
        "android-pruned-node",
        "edge-node",
        "vps",
        "qt",
        "daemon",
        "cli",
        "full",
    )
    default_checked = set(DEFAULT_PRODUCTS)
    # Always default-check the full-node-on-device product so it is hard to miss.
    default_checked.add("android-full-node")

    prod_grid = tk.Frame(products_frame)
    prod_grid.pack(fill=tk.X)
    for idx, pid in enumerate(gui_product_order):
        if pid not in PRODUCT_CHOICES:
            continue
        var = tk.BooleanVar(value=pid in default_checked)
        product_vars[pid] = var
        label = PRODUCT_LABELS.get(pid, pid)
        # Emphasize full node on device/phone
        font = ("", 10, "bold") if pid == "android-full-node" else ("", 10)
        cb = tk.Checkbutton(
            prod_grid,
            text=f"{label}  ({pid})",
            variable=var,
            anchor="w",
            font=font,
        )
        cb.grid(row=idx // 2, column=idx % 2, sticky="w", padx=6, pady=1)

    opts_row = tk.Frame(products_frame)
    opts_row.pack(fill=tk.X, pady=(6, 0))
    with_gui_var = tk.BooleanVar(value=False)
    package_only_var = tk.BooleanVar(value=False)
    tk.Checkbutton(
        opts_row,
        text="Also compile Qt GUI (needed for desktop wallet kit)",
        variable=with_gui_var,
    ).pack(side=tk.LEFT, padx=(0, 12))
    tk.Checkbutton(
        opts_row,
        text="Package only (skip C++ compile — use for phone/device profile kits)",
        variable=package_only_var,
    ).pack(side=tk.LEFT)

    def selected_products() -> List[str]:
        chosen = [pid for pid, var in product_vars.items() if var.get()]
        if not chosen:
            raise ValueError(
                "select at least one product — e.g. “Make a full node on your device or phone”"
            )
        return chosen

    def set_products_only(pids: List[str], *, package_only: bool = False, with_gui: bool = False):
        want = set(pids)
        for pid, var in product_vars.items():
            var.set(pid in want)
        package_only_var.set(package_only)
        with_gui_var.set(with_gui)

    def run_compile_local_kits(
        with_gui: Optional[bool] = None,
        products: Optional[List[str]] = None,
        package_only: Optional[bool] = None,
    ):
        try:
            if not manifest_var.get():
                raise ValueError("choose a Fork Lab manifest JSON")
            work = DEFAULT_WORK
            work.mkdir(parents=True, exist_ok=True)
            form_settings = settings_from_form()
            settings_path = work / "coin-settings.json"
            settings_path.write_text(json.dumps(form_settings, indent=2) + "\n", encoding="utf-8")
            prods = products if products is not None else selected_products()
            do_gui = bool(with_gui_var.get() if with_gui is None else with_gui)
            # Auto Qt GUI flag when qt product is selected
            if "qt" in prods:
                do_gui = True
            pkg_only = bool(package_only_var.get() if package_only is None else package_only)
            # Profile-only selections default to package-only when no compile products.
            if package_only is None and not pkg_only:
                if prods and all(p in PROFILE_ONLY_PRODUCTS for p in prods):
                    pkg_only = True
            products_csv = ",".join(prods)
            append(f"Products: {products_csv}  package_only={pkg_only} with_gui={do_gui}")
            ns = argparse.Namespace(
                manifest=manifest_var.get(),
                tarball=tarball_var.get() or None,
                source=None,
                work=str(work),
                jobs=max(1, (os.cpu_count() or 2) // 2),
                settings=str(settings_path),
                set=[],
                interactive=False,
                local_icon=form_settings.get("local_icon_path") or None,
                with_gui=do_gui,
                package_only=pkg_only,
                reprepare=not (work / "apply-summary.json").is_file() and not pkg_only,
                products=products_csv,
                only=None,
            )
            import builtins

            real_print = builtins.print

            def gui_print(*a, **k):
                append(" ".join(str(x) for x in a))

            builtins.print = gui_print
            try:
                cmd_compile_local(ns)
            finally:
                builtins.print = real_print
            dist = work / "dist"
            labels = ", ".join(PRODUCT_LABELS.get(p, p) for p in prods)
            messagebox.showinfo(
                "Kits ready",
                "Selected products packaged.\n\n"
                f"Products: {labels}\n"
                f"Folder: {dist}\n\n"
                "Phone/device full node: open the *-android-full-node-kit folder,\n"
                "import FORK_EDGE_PROFILE.json, then start full node on the device.\n"
                "See INDEX.json and *.tar.gz / *.zip inside dist/.",
            )
        except Exception as exc:
            append(f"ERROR: {exc}")
            messagebox.showerror("Error", str(exc))

    def run_device_full_node_only():
        """One-click: make a full node on your device or phone."""
        set_products_only(["android-full-node"], package_only=True, with_gui=False)
        run_compile_local_kits(
            with_gui=False,
            products=["android-full-node"],
            package_only=True,
        )

    def run_qt_vps_compile():
        set_products_only(["qt", "vps"], package_only=False, with_gui=True)
        run_compile_local_kits(
            with_gui=True,
            products=["qt", "vps"],
            package_only=False,
        )

    btns = tk.Frame(main)
    btns.pack(fill=tk.X, pady=4)
    tk.Button(btns, text="Save settings...", command=save_settings_only).pack(side=tk.LEFT, padx=3)
    tk.Button(btns, text="1) Apply settings + patch", command=lambda: run_prepare_build(False)).pack(
        side=tk.LEFT, padx=3
    )
    tk.Button(
        btns,
        text="Make full node on device/phone",
        command=run_device_full_node_only,
        font=("", 10, "bold"),
    ).pack(side=tk.LEFT, padx=3)
    tk.Button(
        btns,
        text="Compile / package selected",
        command=lambda: run_compile_local_kits(),
    ).pack(side=tk.LEFT, padx=3)
    tk.Button(
        btns,
        text="Compile + Qt wallet",
        command=run_qt_vps_compile,
    ).pack(side=tk.LEFT, padx=3)
    tk.Button(btns, text="Quit", command=root.destroy).pack(side=tk.RIGHT, padx=3)

    if manifest_var.get():
        load_settings_into_form()

    root.mainloop()
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    _safe_stdio()
    p = argparse.ArgumentParser(
        description=f"Bloodstone Fork Builder {APP_VERSION} - edit settings, then compile offline"
    )
    p.add_argument("--version", action="version", version=APP_VERSION)
    sub = p.add_subparsers(dest="cmd", required=False)

    def add_common(sp):
        sp.add_argument("--manifest", required=True, help="Fork Lab manifest JSON")
        sp.add_argument("--tarball", help="bloodstone-core-*-source.tar.gz")
        sp.add_argument("--source", help="existing unpacked core tree")
        sp.add_argument("--work", default=str(DEFAULT_WORK), help="work directory")
        sp.add_argument(
            "--settings",
            help="JSON file of coin settings overrides (from Save settings or coin-settings.json)",
        )
        sp.add_argument(
            "--set",
            action="append",
            default=[],
            metavar="KEY=VALUE",
            help="override one setting (repeatable), e.g. --set ticker=LRGK --set p2p_port=33685",
        )
        sp.add_argument(
            "--interactive",
            action="store_true",
            help="prompt to edit each setting in the terminal before compile",
        )
        sp.add_argument("--local-icon", help="path to local coin image for Qt branding")

    sp = sub.add_parser("prepare", help="edit settings + extract core + patch")
    add_common(sp)
    sp.set_defaults(func=cmd_prepare)

    sb = sub.add_parser("build", help="compile patched core (Linux)")
    sb.add_argument("--source", required=True)
    sb.add_argument("--jobs", type=int, default=0)
    sb.add_argument("--with-gui", action="store_true", help="also build Qt wallet")
    sb.set_defaults(func=cmd_build)

    sa = sub.add_parser("all", help="prepare (with settings) + build")
    add_common(sa)
    sa.add_argument("--jobs", type=int, default=0)
    sa.add_argument("--with-gui", action="store_true")
    sa.set_defaults(func=cmd_all)

    sc = sub.add_parser(
        "compile-local",
        help="compile binaries + package selected products (or full default set)",
    )
    add_common(sc)
    sc.add_argument("--jobs", type=int, default=0)
    sc.add_argument("--with-gui", action="store_true", help="build Qt wallet too")
    sc.add_argument(
        "--package-only",
        action="store_true",
        help="skip compile; package whatever binaries already exist",
    )
    sc.add_argument(
        "--reprepare",
        action="store_true",
        help="force re-run prepare before compile",
    )
    sc.add_argument(
        "--products",
        help=(
            "comma-separated products to package: "
            + ",".join(PRODUCT_CHOICES)
            + " (default: common set including android-full-node)"
        ),
    )
    sc.add_argument(
        "--only",
        dest="only",
        help="shorthand for a single product, e.g. --only android-full-node",
    )
    sc.set_defaults(func=cmd_compile_local)

    spk = sub.add_parser(
        "package",
        help="package selected kits from already-built binaries",
    )
    spk.add_argument("--work", default=str(DEFAULT_WORK))
    spk.add_argument("--source", help="patched core root")
    spk.add_argument("--manifest", help="manifest JSON")
    spk.add_argument(
        "--products",
        help="comma-separated products (see compile-local --products)",
    )
    spk.add_argument("--only", help="single product shorthand")
    spk.add_argument("--with-gui", action="store_true")
    spk.set_defaults(func=cmd_package)

    ss = sub.add_parser("show", help="print editable settings from a manifest")
    ss.add_argument("--manifest", required=True)
    ss.set_defaults(func=cmd_show)

    sg = sub.add_parser("gui", help="desktop GUI with settings editor (falls back to menu)")
    sg.set_defaults(func=cmd_gui)

    sm = sub.add_parser("menu", help="interactive console wizard (works without tkinter)")
    sm.set_defaults(func=cmd_menu)

    args = p.parse_args(argv)
    if not args.cmd:
        # Default: console menu everywhere (reliable offline; GUI available via `gui`)
        return cmd_menu(args)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
