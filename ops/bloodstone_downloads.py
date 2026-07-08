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


def _desktop_version_from_filename(filename: str) -> Optional[str]:
    for prefix, suffix in (
        ("bloodstone-miner-desktop-", "-win64-portable.exe"),
        ("bloodstone-miner-desktop-", "-win64.exe"),
        ("bloodstone-miner-desktop-", "-linux-x86_64.tar.gz"),
    ):
        if filename.startswith(prefix) and filename.endswith(suffix):
            version = filename[len(prefix) : -len(suffix)]
            return version or None
    return None


def _resolve_miner_desktop() -> str:
    env_version = os.environ.get("BLOODSTONE_MINER_DESKTOP_VERSION", "").strip()
    if env_version:
        return env_version
    try:
        candidates = []
        for name in os.listdir(DOWNLOADS_DIR):
            version = _desktop_version_from_filename(name)
            if version:
                candidates.append((_apk_version_tuple(version), version, name))
        if candidates:
            candidates.sort(reverse=True)
            return candidates[0][1]
    except OSError:
        pass
    return "1.3.75"


MINER_DESKTOP_VERSION = _resolve_miner_desktop()
MINER_DESKTOP_LINUX = f"bloodstone-miner-desktop-{MINER_DESKTOP_VERSION}-linux-x86_64.tar.gz"
MINER_DESKTOP_WIN_PORTABLE = (
    f"bloodstone-miner-desktop-{MINER_DESKTOP_VERSION}-win64-portable.exe"
)
MINER_DESKTOP_WIN_INSTALLER = f"bloodstone-miner-desktop-{MINER_DESKTOP_VERSION}-win64.exe"
MINER_DESKTOP_SRC = f"bloodstone-miner-desktop-{MINER_DESKTOP_VERSION}-source.zip"


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


RELEASE_CHANNELS = ("stable", "beta")

_APK_CHANNEL_LINKS = {
    "stable": "bloodstone-miner-android-latest.apk",
    "beta": "bloodstone-miner-android-beta.apk",
}
_WEB_CHANNEL_LINKS = {
    "stable": "bloodstone-miner-android-web-latest.zip",
    "beta": "bloodstone-miner-android-web-beta.zip",
}


def _normalize_release_channel(channel: str) -> str:
    value = str(channel or "stable").strip().lower()
    return value if value in RELEASE_CHANNELS else "stable"


def _channel_apk_link_name(channel: str) -> str:
    return _APK_CHANNEL_LINKS[_normalize_release_channel(channel)]


def _channel_web_link_name(channel: str) -> str:
    return _WEB_CHANNEL_LINKS[_normalize_release_channel(channel)]


def _list_local_apk_filenames(channel: str = "stable") -> list:
    skip = {
        _APK_CHANNEL_LINKS["stable"],
        _APK_CHANNEL_LINKS["beta"],
    }
    try:
        return sorted(
            f
            for f in os.listdir(DOWNLOADS_DIR)
            if f.startswith("bloodstone-miner-android-")
            and f.endswith(".apk")
            and f not in skip
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
        if name and name not in {
            _APK_CHANNEL_LINKS["stable"],
            _APK_CHANNEL_LINKS["beta"],
        }:
            files.append(name)
    return files


def _resolve_android_apk(channel: str = "stable") -> tuple:
    """Pick published miner APK for stable or beta release channel."""
    channel = _normalize_release_channel(channel)
    env_version = os.environ.get("BLOODSTONE_MINER_ANDROID_VERSION", "").strip()
    env_apk = os.environ.get("BLOODSTONE_MINER_ANDROID_APK", "").strip()
    if channel == "stable" and env_version and env_apk:
        return env_version, env_apk
    if channel == "beta":
        beta_version = os.environ.get("BLOODSTONE_MINER_ANDROID_BETA_VERSION", "").strip()
        beta_apk = os.environ.get("BLOODSTONE_MINER_ANDROID_BETA_APK", "").strip()
        if beta_version and beta_apk:
            return beta_version, beta_apk

    link_name = _channel_apk_link_name(channel)
    latest_link = os.path.join(DOWNLOADS_DIR, link_name)
    resolved = _resolve_apk_from_latest_link(latest_link)
    if resolved:
        return resolved

    remote_target = _remote_readlink(link_name)
    if remote_target:
        version = _apk_version_from_filename(remote_target)
        if version:
            return version, remote_target

    if channel == "beta":
        return _resolve_android_apk("stable")

    candidates = []
    seen = set()
    for filename in _list_remote_apk_filenames() + _list_local_apk_filenames(channel):
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


def _web_bundle_version_from_filename(filename: str) -> Optional[str]:
    prefix = "bloodstone-miner-android-web-"
    suffix = ".zip"
    if not filename.startswith(prefix) or not filename.endswith(suffix):
        return None
    version = filename[len(prefix) : -len(suffix)]
    return version or None


def _web_bundle_version_tuple(version: str) -> tuple:
    parts = []
    for part in str(version or "0").replace("-web", "").split("."):
        num = ""
        for ch in part:
            if ch.isdigit():
                num += ch
            else:
                break
        parts.append(int(num) if num else 0)
    return tuple(parts)


def _list_remote_web_bundle_filenames() -> list:
    if not DOWNLOADS_REMOTE:
        return []
    cmd = [
        "ssh",
        "-i",
        DOWNLOADS_SSH_KEY,
        "-o",
        "BatchMode=yes",
        "-o",
        f"ConnectTimeout={os.environ.get('BLOODSTONE_SSH_TIMEOUT', '5')}",
        "-o",
        "StrictHostKeyChecking=accept-new",
        f"root@{DOWNLOADS_WORKER}",
        "ls -1 /var/www/bloodstone/downloads/bloodstone-miner-android-web-*.zip 2>/dev/null || true",
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
        if (
            name
            and name not in {
                _WEB_CHANNEL_LINKS["stable"],
                _WEB_CHANNEL_LINKS["beta"],
            }
            and _web_bundle_version_from_filename(name)
        ):
            files.append(name)
    return files


def _resolve_android_web_bundle(channel: str = "stable") -> tuple:
    """Pick miner web OTA bundle for stable or beta release channel."""
    channel = _normalize_release_channel(channel)
    env_version = os.environ.get("BLOODSTONE_MINER_ANDROID_WEB_VERSION", "").strip()
    env_bundle = os.environ.get("BLOODSTONE_MINER_ANDROID_WEB_BUNDLE", "").strip()
    if channel == "stable" and env_version and env_bundle:
        return env_version, env_bundle
    if channel == "beta":
        beta_version = os.environ.get(
            "BLOODSTONE_MINER_ANDROID_WEB_BETA_VERSION", ""
        ).strip()
        beta_bundle = os.environ.get(
            "BLOODSTONE_MINER_ANDROID_WEB_BETA_BUNDLE", ""
        ).strip()
        if beta_version and beta_bundle:
            return beta_version, beta_bundle

    link_name = _channel_web_link_name(channel)
    latest_link = os.path.join(DOWNLOADS_DIR, link_name)
    if os.path.islink(latest_link):
        target = os.path.basename(os.readlink(latest_link))
        version = _web_bundle_version_from_filename(target)
        if version:
            return version, target
    remote_target = _remote_readlink(link_name)
    if remote_target:
        version = _web_bundle_version_from_filename(remote_target)
        if version:
            return version, remote_target

    if channel == "beta":
        return _resolve_android_web_bundle("stable")

    skip_links = set(_WEB_CHANNEL_LINKS.values())
    try:
        candidates = sorted(
            (
                f
                for f in os.listdir(DOWNLOADS_DIR)
                if f.startswith("bloodstone-miner-android-web-")
                and f.endswith(".zip")
                and f not in skip_links
            ),
            key=lambda name: _web_bundle_version_tuple(
                _web_bundle_version_from_filename(name) or "0"
            ),
            reverse=True,
        )
        if candidates:
            bundle = candidates[0]
            version = _web_bundle_version_from_filename(bundle) or "0"
            return version, bundle
    except OSError:
        pass
    remote_candidates = []
    seen = set()
    for filename in _list_remote_web_bundle_filenames():
        if filename in seen:
            continue
        seen.add(filename)
        version = _web_bundle_version_from_filename(filename)
        if version:
            remote_candidates.append((version, filename))
    if remote_candidates:
        remote_candidates.sort(
            key=lambda item: _web_bundle_version_tuple(item[0]), reverse=True
        )
        return remote_candidates[0]
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


def invalidate_download_meta_cache(filename: Optional[str] = None) -> None:
    """Drop cached download metadata (e.g. after publishing a new web bundle)."""
    with _META_CACHE_LOCK:
        if filename:
            _META_CACHE.pop(filename, None)
            _META_CACHE.pop(f"{filename}.sha256", None)
        else:
            _META_CACHE.clear()
    with _RUN_LOCALLY_CACHE_LOCK:
        global _RUN_LOCALLY_CACHE
        _RUN_LOCALLY_CACHE = None


def download_meta(public_root: str, filename: str) -> Optional[Dict[str, Any]]:
    cached = _meta_cache_get(filename)
    if cached is not _META_CACHE_MISS:
        return cached
    path = os.path.join(DOWNLOADS_DIR, filename)
    base = downloads_public_base(public_root)
    stat = None
    sha256 = None
    remote = _remote_stat(filename) if DOWNLOADS_REMOTE else None
    if remote:
        stat = remote
        sha256 = remote.get("sha256")
    elif os.path.isfile(path):
        st = os.stat(path)
        stat = {"size_bytes": st.st_size, "mtime": st.st_mtime}
        sha256 = _read_sha256(f"{path}.sha256")
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
    miner_desktop_linux = download_meta(public_root, MINER_DESKTOP_LINUX)
    miner_desktop_win = download_meta(public_root, MINER_DESKTOP_WIN_PORTABLE)
    if not miner_desktop_win:
        miner_desktop_win = download_meta(public_root, MINER_DESKTOP_WIN_INSTALLER)
    miner_desktop_src = download_meta(public_root, MINER_DESKTOP_SRC)
    android_miner_src = download_meta(public_root, MINER_ANDROID_SRC)
    android_miner_apk = download_meta(public_root, MINER_ANDROID_APK)
    downloads = [
        wallet_gui,
        wallet_gui_portable,
        node_gui,
        linux_node,
        win_node,
        miner_win,
        miner_desktop_linux,
        miner_desktop_win,
        miner_desktop_src,
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
        "miner_desktop_linux": miner_desktop_linux,
        "miner_desktop_win": miner_desktop_win,
        "miner_desktop_src": miner_desktop_src,
        "miner_desktop_version": MINER_DESKTOP_VERSION,
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


def _resolve_miner_desktop_for_channel(channel: str = "stable") -> str:
    channel = _normalize_release_channel(channel)
    if channel == "beta":
        beta_link = os.path.join(DOWNLOADS_DIR, "bloodstone-miner-desktop-beta-win64.exe")
        if os.path.islink(beta_link):
            target = os.path.basename(os.readlink(beta_link))
            version = _desktop_version_from_filename(target)
            if version:
                return version
        remote_target = _remote_readlink("bloodstone-miner-desktop-beta-win64.exe")
        if remote_target:
            version = _desktop_version_from_filename(remote_target)
            if version:
                return version
    return MINER_DESKTOP_VERSION


def desktop_miner_update_manifest(
    public_root: str, *, release_channel: str = "stable"
) -> Dict[str, Any]:
    """Metadata for Bloodstone desktop miner (.exe / .tar.gz) update checks."""
    channel = _normalize_release_channel(release_channel)
    base = downloads_public_base(public_root)
    version = _resolve_miner_desktop_for_channel(channel)
    linux_filename = f"bloodstone-miner-desktop-{version}-linux-x86_64.tar.gz"
    win_portable_filename = f"bloodstone-miner-desktop-{version}-win64-portable.exe"
    win_installer_filename = f"bloodstone-miner-desktop-{version}-win64.exe"
    linux_meta = download_meta(public_root, linux_filename) or {}
    win_portable_meta = download_meta(public_root, win_portable_filename) or {}
    win_installer_meta = download_meta(public_root, win_installer_filename) or {}
    return {
        "ok": True,
        "release_channel": channel,
        "version": version,
        "desktop_version": version,
        "linux_filename": linux_filename,
        "linux_url": f"{base}/downloads/{linux_filename}",
        "win_portable_filename": win_portable_filename,
        "win_portable_url": f"{base}/downloads/{win_portable_filename}",
        "win_installer_filename": win_installer_filename,
        "win_installer_url": f"{base}/downloads/{win_installer_filename}",
        "linux_sha256": linux_meta.get("sha256"),
        "linux_size_bytes": linux_meta.get("size_bytes"),
        "win_portable_sha256": win_portable_meta.get("sha256"),
        "win_portable_size_bytes": win_portable_meta.get("size_bytes"),
        "win_installer_sha256": win_installer_meta.get("sha256"),
        "win_installer_size_bytes": win_installer_meta.get("size_bytes"),
        "downloads_page": f"{base}/downloads/",
        "update_mode": "desktop_installer",
        "note": (
            "Desktop miner updates are platform installers — not APK or Android web bundles."
        ),
    }


def _resolve_lan_stable_android_release(lan_ip: str) -> Optional[tuple]:
    """LAN-scoped stable: only after beta testers on that LAN validate."""
    try:
        import bloodstone_beta_codes as beta
    except ImportError:
        return None
    lan_key = beta.lan_key_from_ip(lan_ip)
    if not lan_key:
        return None
    row = beta.get_lan_validated_release(lan_key)
    if not row:
        return None
    apk_version = str(row.get("apk_version") or "").strip()
    apk_filename = str(row.get("apk_filename") or "").strip()
    web_version = str(row.get("web_bundle_version") or "").strip()
    web_filename = str(row.get("web_bundle_filename") or "").strip()
    if apk_version and apk_filename and web_version and web_filename:
        return apk_version, apk_filename, web_version, web_filename, lan_key
    return None


def android_miner_update_manifest(
    public_root: str,
    *,
    release_channel: str = "stable",
    lan_ip: str = "",
) -> Dict[str, Any]:
    """Metadata for sideload Android miner auto-update checks."""
    channel = _normalize_release_channel(release_channel)
    base = downloads_public_base(public_root)
    lan_key = None
    if channel == "stable":
        lan_release = _resolve_lan_stable_android_release(lan_ip)
        if lan_release:
            apk_version, apk_filename, web_version, web_filename, lan_key = lan_release
        else:
            apk_version, apk_filename = _resolve_android_apk(channel)
            web_version, web_filename = _resolve_android_web_bundle(channel)
    else:
        apk_version, apk_filename = _resolve_android_apk(channel)
        web_version, web_filename = _resolve_android_web_bundle(channel)
    apk_link = _channel_apk_link_name(channel)
    web_link = _channel_web_link_name(channel)
    apk_meta = download_meta(public_root, apk_filename) or {}
    web_meta = download_meta(public_root, web_filename) or {}
    chain_meta = download_meta(public_root, CHAIN_BOOTSTRAP_BUNDLE) or {}
    mesh_key = f"downloads/{apk_filename}"
    mesh = _android_mesh_asset_meta(mesh_key)
    payload: Dict[str, Any] = {
        "ok": True,
        "release_channel": channel,
        "lan_scoped_stable": bool(lan_key),
        "lan_key": lan_key,
        "version": apk_version,
        "apk_version": apk_version,
        "apk_filename": apk_filename,
        "apk_url": f"{base}/downloads/{apk_filename}",
        "apk_url_latest": f"{base}/downloads/{apk_link}",
        "sha256": apk_meta.get("sha256"),
        "size_bytes": apk_meta.get("size_bytes"),
        "web_bundle_version": web_version,
        "web_bundle_filename": web_filename,
        "web_bundle_url": f"{base}/downloads/{web_filename}",
        "web_bundle_url_latest": f"{base}/downloads/{web_link}",
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