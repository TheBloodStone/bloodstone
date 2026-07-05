"""Shared Bloodstone download metadata for portal and mining UI."""

from __future__ import annotations

import os
import subprocess
import threading
import time
from email.utils import parsedate_to_datetime
from typing import Any, Dict, Optional

import bloodstone_time

try:
    import requests
except ImportError:
    requests = None  # type: ignore

DOWNLOADS_DIR = os.environ.get(
    "BLOODSTONE_DOWNLOADS_DIR", "/var/www/bloodstone/downloads"
)
DOWNLOADS_WORKER = os.environ.get("BLOODSTONE_DOWNLOADS_WORKER", "192.119.82.145")
DOWNLOADS_SSH_KEY = os.environ.get(
    "BLOODSTONE_DOWNLOADS_SSH_KEY", "/root/.ssh/bloodstone_copy_key"
)
# When true, file metadata is read from worker if not present locally.
DOWNLOADS_REMOTE = os.environ.get("BLOODSTONE_DOWNLOADS_REMOTE", "1") == "1"
PUBLIC_DOWNLOADS_BASE = os.environ.get(
    "BLOODSTONE_PUBLIC_DOWNLOADS_BASE", ""
).rstrip("/")

NODE_VERSION = os.environ.get("BLOODSTONE_NODE_VERSION", "0.6.9.1")
NODE_GUI_VERSION = os.environ.get("BLOODSTONE_NODE_GUI_VERSION", "0.6.9.2")
WALLET_GUI_VERSION = os.environ.get("BLOODSTONE_WALLET_GUI_VERSION", "0.7.11")

NODE_PKG = f"bloodstone-node-{NODE_VERSION}-linux-x86_64.tar.gz"
NODE_WIN_PKG = f"bloodstone-node-{NODE_VERSION}-win64.zip"
GUI_WIN_INSTALLER = f"bloodstone-node-gui-{NODE_GUI_VERSION}-win64.exe"
WALLET_GUI_INSTALLER = f"bloodstone-wallet-node-gui-{WALLET_GUI_VERSION}-win64.exe"
WALLET_GUI_PORTABLE = (
    f"bloodstone-wallet-node-gui-{WALLET_GUI_VERSION}-win64-portable.exe"
)
MINER_PACK_VERSION = os.environ.get("BLOODSTONE_MINER_PACK_VERSION", "1.0.0")
MINER_WIN_PKG = f"bloodstone-miner-{MINER_PACK_VERSION}-win64.zip"
def _apk_version_tuple(version: str) -> tuple:
    parts = []
    for part in str(version or "0").split("."):
        num = ""
        for ch in part:
            if ch.isdigit():
                num += ch
            else:
                break
        parts.append(int(num) if num else 0)
    return tuple(parts)


def _apk_version_from_filename(filename: str) -> Optional[str]:
    prefix = "bloodstone-miner-android-"
    suffix = ".apk"
    if not filename.startswith(prefix) or not filename.endswith(suffix):
        return None
    version = filename[len(prefix) : -len(suffix)]
    return version or None


def _resolve_apk_from_latest_link(link_path: str) -> Optional[tuple]:
    if not os.path.islink(link_path):
        return None
    target = os.path.basename(os.readlink(link_path))
    version = _apk_version_from_filename(target)
    if version:
        return version, target
    return None


def _list_local_apk_filenames() -> list:
    try:
        return sorted(
            f
            for f in os.listdir(DOWNLOADS_DIR)
            if f.startswith("bloodstone-miner-android-")
            and f.endswith(".apk")
            and f != "bloodstone-miner-android-latest.apk"
        )
    except OSError:
        return []


def _remote_readlink(filename: str) -> Optional[str]:
    if not DOWNLOADS_REMOTE:
        return None
    remote = f"/var/www/bloodstone/downloads/{filename}"
    timeout = os.environ.get("BLOODSTONE_SSH_TIMEOUT", "5")
    cmd = [
        "ssh",
        "-i",
        DOWNLOADS_SSH_KEY,
        "-o",
        "BatchMode=yes",
        "-o",
        f"ConnectTimeout={timeout}",
        "-o",
        "StrictHostKeyChecking=accept-new",
        f"root@{DOWNLOADS_WORKER}",
        f"readlink '{remote}' 2>/dev/null || true",
    ]
    try:
        out = subprocess.check_output(
            cmd, stderr=subprocess.DEVNULL, text=True, timeout=8
        ).strip()
    except (subprocess.CalledProcessError, OSError, subprocess.TimeoutExpired):
        return None
    return os.path.basename(out) if out else None


def _list_remote_apk_filenames() -> list:
    if not DOWNLOADS_REMOTE:
        return []
    timeout = os.environ.get("BLOODSTONE_SSH_TIMEOUT", "5")
    cmd = [
        "ssh",
        "-i",
        DOWNLOADS_SSH_KEY,
        "-o",
        "BatchMode=yes",
        "-o",
        f"ConnectTimeout={timeout}",
        "-o",
        "StrictHostKeyChecking=accept-new",
        f"root@{DOWNLOADS_WORKER}",
        "ls -1 /var/www/bloodstone/downloads/bloodstone-miner-android-*.apk 2>/dev/null || true",
    ]
    try:
        out = subprocess.check_output(
            cmd, stderr=subprocess.DEVNULL, text=True, timeout=8
        )
    except (subprocess.CalledProcessError, OSError, subprocess.TimeoutExpired):
        return []
    files = []
    for line in out.splitlines():
        name = os.path.basename(line.strip())
        if name and name != "bloodstone-miner-android-latest.apk":
            files.append(name)
    return files


def _resolve_android_apk() -> tuple:
    """Pick newest published miner APK (latest symlink, else highest version on worker/local)."""
    env_version = os.environ.get("BLOODSTONE_MINER_ANDROID_VERSION", "").strip()
    env_apk = os.environ.get("BLOODSTONE_MINER_ANDROID_APK", "").strip()
    if env_version and env_apk:
        return env_version, env_apk

    latest_link = os.path.join(DOWNLOADS_DIR, "bloodstone-miner-android-latest.apk")
    resolved = _resolve_apk_from_latest_link(latest_link)
    if resolved:
        return resolved

    remote_target = _remote_readlink("bloodstone-miner-android-latest.apk")
    if remote_target:
        version = _apk_version_from_filename(remote_target)
        if version:
            return version, remote_target

    candidates = []
    seen = set()
    for filename in _list_remote_apk_filenames() + _list_local_apk_filenames():
        if filename in seen:
            continue
        seen.add(filename)
        version = _apk_version_from_filename(filename)
        if version:
            candidates.append((version, filename))
    if candidates:
        candidates.sort(key=lambda item: _apk_version_tuple(item[0]), reverse=True)
        return candidates[0]

    version = env_version or "1.3.39"
    return version, f"bloodstone-miner-android-{version}.apk"


MINER_ANDROID_VERSION, MINER_ANDROID_APK = _resolve_android_apk()


def _resolve_android_web_bundle() -> tuple:
    """Pick newest published miner web OTA bundle (env override, else latest symlink)."""
    env_version = os.environ.get("BLOODSTONE_MINER_ANDROID_WEB_VERSION", "").strip()
    env_bundle = os.environ.get("BLOODSTONE_MINER_ANDROID_WEB_BUNDLE", "").strip()
    if env_version and env_bundle:
        return env_version, env_bundle
    latest_link = os.path.join(DOWNLOADS_DIR, "bloodstone-miner-android-web-latest.zip")
    if os.path.islink(latest_link):
        target = os.path.basename(os.readlink(latest_link))
        if target.startswith("bloodstone-miner-android-web-") and target.endswith(".zip"):
            version = target[len("bloodstone-miner-android-web-") : -len(".zip")]
            return version, target
    try:
        candidates = sorted(
            (
                f
                for f in os.listdir(DOWNLOADS_DIR)
                if f.startswith("bloodstone-miner-android-web-") and f.endswith(".zip")
            ),
            reverse=True,
        )
        if candidates:
            bundle = candidates[0]
            version = bundle[len("bloodstone-miner-android-web-") : -len(".zip")]
            return version, bundle
    except OSError:
        pass
    version = env_version or "1.3.41-web"
    bundle = env_bundle or f"bloodstone-miner-android-web-{version}.zip"
    return version, bundle


MINER_ANDROID_WEB_VERSION, MINER_ANDROID_WEB_BUNDLE = _resolve_android_web_bundle()
MINER_ANDROID_SRC = f"bloodstone-miner-android-{MINER_ANDROID_VERSION}-source.zip"

_META_CACHE_TTL_SEC = float(os.environ.get("BLOODSTONE_DOWNLOADS_META_CACHE_SEC", "300"))
_META_CACHE: Dict[str, tuple] = {}
_META_CACHE_LOCK = threading.Lock()
_META_CACHE_MISS = object()
_RUN_LOCALLY_CACHE: Optional[tuple] = None
_RUN_LOCALLY_CACHE_LOCK = threading.Lock()


def downloads_public_base(public_root: str) -> str:
    if PUBLIC_DOWNLOADS_BASE:
        return PUBLIC_DOWNLOADS_BASE
    return (public_root or "").rstrip("/")


def _read_sha256(sidecar_path: str) -> Optional[str]:
    if not os.path.isfile(sidecar_path):
        return None
    with open(sidecar_path, encoding="utf-8") as fh:
        line = fh.readline().strip()
    return line.split()[0] if line else None


def _downloads_http_base() -> str:
    port = os.environ.get("BLOODSTONE_DOWNLOADS_HTTP_PORT", "8088")
    return f"http://{DOWNLOADS_WORKER}:{port}/downloads"


def _http_timeout_sec() -> float:
    try:
        return max(1.0, float(os.environ.get("BLOODSTONE_DOWNLOADS_HTTP_TIMEOUT", "4")))
    except (TypeError, ValueError):
        return 4.0


def _remote_stat_http(filename: str) -> Optional[Dict[str, Any]]:
    if requests is None:
        return None
    base = _downloads_http_base()
    url = f"{base}/{filename}"
    try:
        resp = requests.head(url, timeout=_http_timeout_sec(), allow_redirects=True)
    except Exception:
        return None
    if resp.status_code != 200:
        return None
    try:
        size_bytes = int(resp.headers.get("Content-Length") or 0)
    except (TypeError, ValueError):
        size_bytes = 0
    mtime = time.time()
    last_mod = resp.headers.get("Last-Modified")
    if last_mod:
        try:
            mtime = parsedate_to_datetime(last_mod).timestamp()
        except (TypeError, ValueError, OverflowError):
            pass
    sha256 = None
    try:
        sha_resp = requests.get(
            f"{url}.sha256", timeout=_http_timeout_sec(), allow_redirects=True
        )
        if sha_resp.ok and sha_resp.text.strip():
            sha256 = sha_resp.text.strip().split()[0]
    except Exception:
        pass
    return {"size_bytes": size_bytes, "mtime": mtime, "sha256": sha256}


def _remote_stat_ssh(filename: str) -> Optional[Dict[str, Any]]:
    remote = f"/var/www/bloodstone/downloads/{filename}"
    timeout = os.environ.get("BLOODSTONE_SSH_TIMEOUT", "5")
    cmd = [
        "ssh",
        "-i",
        DOWNLOADS_SSH_KEY,
        "-o",
        "BatchMode=yes",
        "-o",
        f"ConnectTimeout={timeout}",
        "-o",
        "StrictHostKeyChecking=accept-new",
        f"root@{DOWNLOADS_WORKER}",
        f"test -f '{remote}' && stat -c '%s %Y' '{remote}' || echo MISSING",
    ]
    try:
        out = subprocess.check_output(
            cmd, stderr=subprocess.DEVNULL, text=True, timeout=8
        ).strip()
    except (subprocess.CalledProcessError, OSError, subprocess.TimeoutExpired):
        return None
    if not out or out == "MISSING":
        return None
    parts = out.split()
    if len(parts) < 2:
        return None
    size_bytes = int(parts[0])
    mtime = float(parts[1])
    sha256 = None
    sha_cmd = [
        "ssh",
        "-i",
        DOWNLOADS_SSH_KEY,
        "-o",
        "BatchMode=yes",
        "-o",
        f"ConnectTimeout={timeout}",
        "-o",
        "StrictHostKeyChecking=accept-new",
        f"root@{DOWNLOADS_WORKER}",
        f"test -f '{remote}.sha256' && head -1 '{remote}.sha256' || true",
    ]
    try:
        sha_line = subprocess.check_output(
            sha_cmd, stderr=subprocess.DEVNULL, text=True, timeout=8
        ).strip()
        if sha_line:
            sha256 = sha_line.split()[0]
    except (subprocess.CalledProcessError, OSError, subprocess.TimeoutExpired):
        pass
    return {"size_bytes": size_bytes, "mtime": mtime, "sha256": sha256}


def _remote_stat(filename: str) -> Optional[Dict[str, Any]]:
    if not DOWNLOADS_REMOTE:
        return None
    stat = _remote_stat_http(filename)
    if stat:
        return stat
    return _remote_stat_ssh(filename)


def _meta_cache_get(filename: str):
    now = time.time()
    with _META_CACHE_LOCK:
        entry = _META_CACHE.get(filename)
        if entry and now - entry[0] < _META_CACHE_TTL_SEC:
            return entry[1]
    return _META_CACHE_MISS


def _meta_cache_put(filename: str, value: Optional[Dict[str, Any]]) -> None:
    with _META_CACHE_LOCK:
        _META_CACHE[filename] = (time.time(), value)


def download_meta(public_root: str, filename: str) -> Optional[Dict[str, Any]]:
    cached = _meta_cache_get(filename)
    if cached is not _META_CACHE_MISS:
        return cached
    path = os.path.join(DOWNLOADS_DIR, filename)
    base = downloads_public_base(public_root)
    stat = None
    sha256 = None
    if os.path.isfile(path):
        st = os.stat(path)
        stat = {"size_bytes": st.st_size, "mtime": st.st_mtime}
        sha256 = _read_sha256(f"{path}.sha256")
    else:
        remote = _remote_stat(filename)
        if remote:
            stat = remote
            sha256 = remote.get("sha256")
    if not stat:
        _meta_cache_put(filename, None)
        return None
    meta = {
        "filename": filename,
        "url": f"{base}/downloads/{filename}",
        "size_bytes": stat["size_bytes"],
        "sha256": sha256,
        "mtime": stat["mtime"],
        "built_utc": bloodstone_time.format_pacific(
            stat["mtime"], "%Y-%m-%d %H:%M %Z"
        ),
    }
    _meta_cache_put(filename, meta)
    return meta


def run_locally_context(public_root: str) -> Dict[str, Any]:
    global _RUN_LOCALLY_CACHE
    now = time.time()
    with _RUN_LOCALLY_CACHE_LOCK:
        if _RUN_LOCALLY_CACHE and now - _RUN_LOCALLY_CACHE[0] < _META_CACHE_TTL_SEC:
            return _RUN_LOCALLY_CACHE[1]
    base = downloads_public_base(public_root)
    wallet_gui = download_meta(public_root, WALLET_GUI_INSTALLER)
    wallet_gui_portable = download_meta(public_root, WALLET_GUI_PORTABLE)
    node_gui = download_meta(public_root, GUI_WIN_INSTALLER)
    linux_node = download_meta(public_root, NODE_PKG)
    win_node = download_meta(public_root, NODE_WIN_PKG)
    miner_win = download_meta(public_root, MINER_WIN_PKG)
    android_miner_src = download_meta(public_root, MINER_ANDROID_SRC)
    android_miner_apk = download_meta(public_root, MINER_ANDROID_APK)
    downloads = [
        wallet_gui,
        wallet_gui_portable,
        node_gui,
        linux_node,
        win_node,
        miner_win,
        android_miner_src,
        android_miner_apk,
    ]
    payload = {
        "wallet_gui": wallet_gui,
        "wallet_gui_portable": wallet_gui_portable,
        "node_gui": node_gui,
        "linux_node": linux_node,
        "win_node": win_node,
        "miner_win": miner_win,
        "miner_pack_version": MINER_PACK_VERSION,
        "android_miner_src": android_miner_src,
        "android_miner_apk": android_miner_apk,
        "android_miner_version": MINER_ANDROID_VERSION,
        "downloads_page": f"{base}/downloads/",
        "node_version": NODE_VERSION,
        "node_gui_version": NODE_GUI_VERSION,
        "wallet_gui_version": WALLET_GUI_VERSION,
        "has_downloads": any(downloads),
        "downloads_host": DOWNLOADS_WORKER if DOWNLOADS_REMOTE else "local",
    }
    with _RUN_LOCALLY_CACHE_LOCK:
        _RUN_LOCALLY_CACHE = (time.time(), payload)
    return payload


def _android_mesh_asset_meta(asset_key: str) -> Optional[Dict[str, Any]]:
    """Chain mesh fallback metadata for a published APK asset."""
    try:
        import chain_mesh.db as mesh_db

        mesh_db.init_db()
        asset = mesh_db.get_asset(asset_key=asset_key)
        if not asset:
            return None
        return {
            "asset_key": asset["asset_key"],
            "asset_id": asset["asset_id"],
            "merkle_root": asset["merkle_root"],
            "file_sha256": asset["file_sha256"],
            "file_size": asset["file_size"],
            "chunk_count": asset["chunk_count"],
            "anchor_txid": asset.get("anchor_txid"),
            "anchor_height": asset.get("anchor_height"),
        }
    except Exception:
        return None


def node_patch_update_manifest(public_root: str) -> Dict[str, Any]:
    """Metadata for live VPS node hot-patch auto-update checks."""
    import node_live_patch as nlp

    return nlp.update_manifest(public_root=public_root)


def _resolve_chain_bootstrap() -> tuple:
    """Latest pre-downloaded chain snapshot for Android node bootstrap."""
    env_height = os.environ.get("BLOODSTONE_CHAIN_BOOTSTRAP_HEIGHT", "").strip()
    env_bundle = os.environ.get("BLOODSTONE_CHAIN_BOOTSTRAP_BUNDLE", "").strip()
    if env_height and env_bundle:
        return env_height, env_bundle
    latest_link = os.path.join(DOWNLOADS_DIR, "bloodstone-chain-bootstrap-latest.tar.gz")
    if os.path.islink(latest_link):
        target = os.path.basename(os.readlink(latest_link))
        prefix = "bloodstone-chain-bootstrap-"
        suffix = ".tar.gz"
        if target.startswith(prefix) and target.endswith(suffix):
            height = target[len(prefix) : -len(suffix)]
            return height, target
    try:
        candidates = sorted(
            (
                f
                for f in os.listdir(DOWNLOADS_DIR)
                if f.startswith("bloodstone-chain-bootstrap-") and f.endswith(".tar.gz")
            ),
            reverse=True,
        )
        if candidates:
            bundle = candidates[0]
            height = bundle[len("bloodstone-chain-bootstrap-") : -len(".tar.gz")]
            return height, bundle
    except OSError:
        pass
    remote_target = _remote_readlink("bloodstone-chain-bootstrap-latest.tar.gz")
    if remote_target:
        prefix = "bloodstone-chain-bootstrap-"
        suffix = ".tar.gz"
        if remote_target.startswith(prefix) and remote_target.endswith(suffix):
            height = remote_target[len(prefix) : -len(suffix)]
            return height, remote_target
    return "9080", "bloodstone-chain-bootstrap-9080.tar.gz"


CHAIN_BOOTSTRAP_HEIGHT, CHAIN_BOOTSTRAP_BUNDLE = _resolve_chain_bootstrap()


def android_miner_update_manifest(public_root: str) -> Dict[str, Any]:
    """Metadata for sideload Android miner auto-update checks."""
    base = downloads_public_base(public_root)
    apk_meta = download_meta(public_root, MINER_ANDROID_APK) or {}
    web_meta = download_meta(public_root, MINER_ANDROID_WEB_BUNDLE) or {}
    chain_meta = download_meta(public_root, CHAIN_BOOTSTRAP_BUNDLE) or {}
    mesh_key = f"downloads/{MINER_ANDROID_APK}"
    mesh = _android_mesh_asset_meta(mesh_key)
    payload: Dict[str, Any] = {
        "ok": True,
        "version": MINER_ANDROID_VERSION,
        "apk_version": MINER_ANDROID_VERSION,
        "apk_filename": MINER_ANDROID_APK,
        "apk_url": f"{base}/downloads/{MINER_ANDROID_APK}",
        "apk_url_latest": f"{base}/downloads/bloodstone-miner-android-latest.apk",
        "sha256": apk_meta.get("sha256"),
        "size_bytes": apk_meta.get("size_bytes"),
        "web_bundle_version": MINER_ANDROID_WEB_VERSION,
        "web_bundle_filename": MINER_ANDROID_WEB_BUNDLE,
        "web_bundle_url": f"{base}/downloads/{MINER_ANDROID_WEB_BUNDLE}",
        "web_bundle_url_latest": f"{base}/downloads/bloodstone-miner-android-web-latest.zip",
        "web_bundle_sha256": web_meta.get("sha256"),
        "web_bundle_size_bytes": web_meta.get("size_bytes"),
        "chain_bootstrap_height": CHAIN_BOOTSTRAP_HEIGHT,
        "chain_bootstrap_filename": CHAIN_BOOTSTRAP_BUNDLE,
        "chain_bootstrap_url": f"{base}/downloads/{CHAIN_BOOTSTRAP_BUNDLE}",
        "chain_bootstrap_url_latest": f"{base}/downloads/bloodstone-chain-bootstrap-latest.tar.gz",
        "chain_bootstrap_sha256": chain_meta.get("sha256"),
        "chain_bootstrap_size_bytes": chain_meta.get("size_bytes"),
        "downloads_page": f"{base}/downloads/",
        "update_mode": "web_bundle_first",
        "note": (
            "UI changes ship as web_bundle (live OTA, no APK reinstall). "
            "apk_version is only for native plugin / Capacitor updates."
        ),
    }
    if mesh:
        payload["mesh_asset_key"] = mesh["asset_key"]
        payload["mesh_merkle_root"] = mesh["merkle_root"]
        payload["mesh_file_sha256"] = mesh["file_sha256"]
        payload["mesh_file_size"] = mesh["file_size"]
        payload["mesh_chunk_count"] = mesh["chunk_count"]
        payload["mesh_anchor_txid"] = mesh.get("anchor_txid")
        payload["mesh"] = mesh
    return payload