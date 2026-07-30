"""Per-fork local daemon download + start/stop for Multi-Fork Qt (Windows-first)."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import subprocess
import sys
import threading
import time
import zipfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from urllib.request import Request, urlopen

from . import settings_store as store
from .catalog import DEFAULT_RPC, conf_search_paths, resolve_public_peers

_IS_WIN = sys.platform.startswith("win")

PUBLIC_ROOT = os.environ.get(
    "BLOODSTONE_PUBLIC_ROOT", "https://bloodstone.rocks"
).rstrip("/")
MANIFEST_URL = os.environ.get(
    "MFQ_DAEMON_MANIFEST_URL",
    f"{PUBLIC_ROOT}/downloads/mfq-daemons/manifest.json",
)
DOWNLOADS_BASE = os.environ.get(
    "MFQ_DAEMON_DOWNLOADS_BASE",
    f"{PUBLIC_ROOT}/downloads/mfq-daemons",
)

LogFn = Callable[[str], None]
ProgressFn = Callable[[str, int], None]  # ticker, pct 0-100


def daemons_root() -> Path:
    p = store.config_dir() / "daemons"
    p.mkdir(parents=True, exist_ok=True)
    return p


def datadir_for(ticker: str) -> Path:
    t = ticker.upper()
    # Prefer app-local datadirs so multi-fork stays self-contained
    p = store.config_dir() / "datadirs" / t.lower()
    p.mkdir(parents=True, exist_ok=True)
    return p


def pack_dir(ticker: str) -> Path:
    return daemons_root() / ticker.upper()


def _default_ports(ticker: str) -> Dict[str, int]:
    meta = DEFAULT_RPC.get(ticker.upper()) or {}
    return {
        "rpc_port": int(meta.get("rpc_port") or 0),
        "p2p_port": int(meta.get("p2p_port") or 0),
    }


def conf_filename_for(ticker: str) -> str:
    """On-disk conf name written into the datadir.

    STONE / LRGK / AZURE Windows binaries all still default to bloodstone.conf
    (forked from Bloodstone). Using a single canonical name avoids silent
    ignores when -conf path handling differs across builds.
    """
    t = (ticker or "").upper()
    # Keep a human alias file too, but the file the node actually reads is this.
    return "bloodstone.conf"


def find_bundled_daemons_root(
    *,
    start_paths: Optional[List[Path]] = None,
) -> Optional[Path]:
    """Locate install tree that contains daemons/STONE (or AZURE/LRGK).

    Handles portable layout, NSIS install under LOCALAPPDATA, launch.bat
    (cwd=app/), and desktop shortcuts that do not set cwd to the install root.
    """
    seen = set()
    candidates: List[Path] = []
    for p in start_paths or []:
        if p:
            candidates.append(Path(p))
    # Walk parents of this module: .../app/bloodstone_mfq → .../app → install root
    try:
        here = Path(__file__).resolve()
        candidates.append(here)
        candidates.extend(here.parents)
    except Exception:
        pass
    if getattr(sys, "frozen", False):
        try:
            candidates.append(Path(sys.executable).resolve().parent)
        except Exception:
            pass
    try:
        candidates.append(Path(sys.argv[0]).resolve().parent)
    except Exception:
        pass
    candidates.append(Path.cwd())

    for c in candidates:
        try:
            c = c.resolve()
        except Exception:
            continue
        if c in seen:
            continue
        seen.add(c)
        # Direct: <root>/daemons/STONE
        d = c / "daemons"
        if d.is_dir() and (
            (d / "STONE").is_dir()
            or (d / "LRGK").is_dir()
            or (d / "AZURE").is_dir()
            or any(d.iterdir())
        ):
            return c
        # Nested under app/
        d2 = c / "app" / "daemons"
        if d2.is_dir():
            return c / "app"
        # Parent of app/ (when start path is .../app)
        if c.name.lower() == "app":
            parent = c.parent
            if (parent / "daemons").is_dir():
                return parent
    return None


class DaemonManager:
    """Download, install, and run one local node process per ticker."""

    def __init__(self, log: Optional[LogFn] = None):
        self._log = log or (lambda m: None)
        self._lock = threading.RLock()
        self._procs: Dict[str, subprocess.Popen] = {}
        self._manifest: Dict[str, Any] = {"coins": {}, "at": 0.0}
        self._bundled_root: Optional[Path] = None

    def set_log(self, fn: LogFn) -> None:
        self._log = fn

    def set_bundled_root(self, path: Optional[str]) -> None:
        """Directory that may contain bundled daemons/STONE etc. (install tree)."""
        self._bundled_root = Path(path) if path else None

    def log(self, msg: str) -> None:
        try:
            self._log(msg)
        except Exception:
            pass

    # ── manifest / install state ───────────────────────────
    def fetch_manifest(self, *, force: bool = False) -> Dict[str, Any]:
        now = time.time()
        if (
            not force
            and self._manifest.get("coins")
            and now - float(self._manifest.get("at") or 0) < 60
        ):
            return self._manifest
        try:
            req = Request(MANIFEST_URL, headers={"User-Agent": "Bloodstone-MultiForkQt"})
            with urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if isinstance(data, dict):
                self._manifest = data
                self._manifest["at"] = now
                return self._manifest
        except Exception as exc:
            self.log(f"Daemon manifest fetch failed: {exc}")
        # Fallback built-in catalogue
        self._manifest = {
            "at": now,
            "schema": "bloodstone/mfq-daemons/v1",
            "coins": {
                "STONE": {
                    "ticker": "STONE",
                    "name": "Bloodstone",
                    "version": "0.7.7",
                    "url": f"{DOWNLOADS_BASE}/STONE-win64.zip",
                    "sha256_url": f"{DOWNLOADS_BASE}/STONE-win64.zip.sha256",
                    "daemon": "bloodstoned.exe",
                    "cli": "bloodstone-cli.exe",
                    "rpc_port": 18332,
                    "p2p_port": 17333,
                    "platform": "win64",
                },
                "AZURE": {
                    "ticker": "AZURE",
                    "name": "Azure Guardian Coin",
                    "version": "0.1.0",
                    "url": f"{DOWNLOADS_BASE}/AZURE-win64.zip",
                    "sha256_url": f"{DOWNLOADS_BASE}/AZURE-win64.zip.sha256",
                    "daemon": "azured.exe",
                    "cli": "azure-cli.exe",
                    "rpc_port": 49825,
                    "p2p_port": 29825,
                    "platform": "win64",
                },
                "LRGK": {
                    "ticker": "LRGK",
                    "name": "Lil Raghnok Coin",
                    "version": "0.1.0",
                    "url": f"{DOWNLOADS_BASE}/LRGK-win64.zip",
                    "sha256_url": f"{DOWNLOADS_BASE}/LRGK-win64.zip.sha256",
                    "daemon": "lrgkd.exe",
                    "cli": "lrgk-cli.exe",
                    "rpc_port": 53685,
                    "p2p_port": 33685,
                    "platform": "win64",
                },
            },
        }
        return self._manifest

    def pack_meta(self, ticker: str) -> Dict[str, Any]:
        man = self.fetch_manifest()
        coins = man.get("coins") or {}
        t = ticker.upper()
        if t in coins and isinstance(coins[t], dict):
            return dict(coins[t])
        ports = _default_ports(t)
        return {
            "ticker": t,
            "name": t,
            "url": f"{DOWNLOADS_BASE}/{t}-win64.zip",
            "daemon": f"{t.lower()}d.exe" if t != "STONE" else "bloodstoned.exe",
            "cli": f"{t.lower()}-cli.exe" if t != "STONE" else "bloodstone-cli.exe",
            "rpc_port": ports["rpc_port"],
            "p2p_port": ports["p2p_port"],
            "platform": "win64",
        }

    def is_installed(self, ticker: str) -> bool:
        return self.daemon_path(ticker) is not None

    def pack_json(self, ticker: str) -> Dict[str, Any]:
        """Read pack.json next to the installed daemon if present."""
        t = ticker.upper()
        for d in (pack_dir(t),):
            for name in ("pack.json", f"{t}-win64/pack.json"):
                p = d / name
                if p.is_file():
                    try:
                        return json.loads(p.read_text(encoding="utf-8"))
                    except Exception:
                        pass
            # nested extract folder
            try:
                for p in d.rglob("pack.json"):
                    try:
                        return json.loads(p.read_text(encoding="utf-8"))
                    except Exception:
                        continue
            except OSError:
                pass
        return {}

    def is_placeholder_fork_binary(self, ticker: str) -> bool:
        """True when LRGK/AZURE pack is a renamed bloodstoned (wrong addresses)."""
        t = ticker.upper()
        if t == "STONE":
            return False
        meta = self.pack_json(t)
        # Explicit identity from real packs (0.1.1+)
        identity = str(meta.get("identity") or "").lower()
        if identity.startswith("real-") or meta.get("usable_for_wallets") is True:
            if "placeholder" not in identity and "renamed" not in identity:
                return False
        if meta.get("usable_for_wallets") is False:
            return True
        note = str(meta.get("note") or "").lower()
        if "renamed" in note and "bloodstone" in note:
            return True
        if "replace with true" in note:
            return True
        if "placeholder" in identity or "placeholder" in note:
            return True
        # Hash-compare to STONE pack when both installed
        try:
            stone = self.daemon_path("STONE")
            mine = self.daemon_path(t)
            if stone and mine and stone.is_file() and mine.is_file():
                if stone.stat().st_size == mine.stat().st_size:
                    hs = hashlib.sha256(stone.read_bytes()).hexdigest()
                    hm = hashlib.sha256(mine.read_bytes()).hexdigest()
                    if hs == hm:
                        return True
        except OSError:
            pass
        return False

    def daemon_path(self, ticker: str) -> Optional[Path]:
        t = ticker.upper()
        meta = self.pack_meta(t)
        preferred = [
            str(meta.get("daemon") or ""),
            "daemon.exe",
            f"{t.lower()}d.exe",
        ]
        # Only STONE should accept bloodstoned.exe as its primary binary.
        if t == "STONE":
            preferred.append("bloodstoned.exe")
        preferred_l = [n.lower() for n in preferred if n]

        search_dirs = [pack_dir(t)]
        if self._bundled_root:
            search_dirs.extend(
                [
                    self._bundled_root / "daemons" / t,
                    self._bundled_root / "daemons" / t.lower(),
                    self._bundled_root / "bin" / t,
                ]
            )
        for d in search_dirs:
            if not d or not d.is_dir():
                continue
            # Prefer exact preferred names (flat or one nesting level)
            for name in preferred:
                if not name:
                    continue
                for p in (d / name, d / f"{t}-win64" / name, d / t / name):
                    if p.is_file():
                        return p
            # recursive: score preferred names first, then any *d.exe
            try:
                candidates: List[Path] = []
                for p in d.rglob("*.exe"):
                    bn = p.name.lower()
                    if "cli" in bn or "qt" in bn or "wallet" in bn:
                        continue
                    if t != "STONE" and bn == "bloodstoned.exe":
                        # Never treat bloodstoned as a fork daemon by filename
                        continue
                    if bn in preferred_l:
                        return p
                    if bn.endswith("d.exe") or bn == "daemon.exe":
                        candidates.append(p)
                if candidates:
                    # Prefer deeper names matching ticker
                    for p in candidates:
                        if t.lower() in p.name.lower():
                            return p
                    return candidates[0]
            except OSError:
                pass
        return None

    def _flatten_pack_dir(self, out: Path, ticker: str) -> None:
        """Flatten STONE-win64/ nesting after zip extract so daemon.exe is top-level."""
        t = ticker.upper()
        nested = out / f"{t}-win64"
        if nested.is_dir():
            for item in nested.iterdir():
                dest = out / item.name
                if dest.exists():
                    if dest.is_dir():
                        shutil.rmtree(dest, ignore_errors=True)
                    else:
                        try:
                            dest.unlink()
                        except OSError:
                            pass
                shutil.move(str(item), str(dest))
            try:
                nested.rmdir()
            except OSError:
                pass

    def _pid_file(self, ticker: str) -> Path:
        return datadir_for(ticker) / "mfq-daemon.pid"

    def _write_pid_file(self, ticker: str, pid: int) -> None:
        try:
            self._pid_file(ticker).write_text(str(int(pid)) + "\n", encoding="utf-8")
        except OSError:
            pass

    def _read_pid_file(self, ticker: str) -> Optional[int]:
        p = self._pid_file(ticker)
        try:
            if p.is_file():
                return int(p.read_text(encoding="utf-8").strip().split()[0])
        except (OSError, ValueError, IndexError):
            pass
        return None

    def _pid_alive(self, pid: Optional[int]) -> bool:
        if not pid or pid <= 0:
            return False
        try:
            if _IS_WIN:
                # OpenProcess / tasklist is heavy; os.kill(pid, 0) works on Win py3.8+
                os.kill(pid, 0)
                return True
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError, PermissionError, SystemError):
            # PermissionError often means process exists but not owned
            try:
                if _IS_WIN:
                    # tasklist fallback
                    out = subprocess.check_output(
                        ["tasklist", "/FI", f"PID eq {int(pid)}", "/NH"],
                        stderr=subprocess.DEVNULL,
                        text=True,
                        timeout=5,
                    )
                    return str(pid) in (out or "")
            except Exception:
                pass
            return False

    def _datadir_conf_paths(self, ticker: str) -> List[Path]:
        """Possible conf files in the MFQ datadir for this ticker."""
        t = ticker.upper()
        ddir = datadir_for(t)
        names = {
            "STONE": ["bloodstone.conf"],
            "AZURE": ["bloodstone.conf", "azure.conf"],
            "LRGK": ["bloodstone.conf", "lrgk.conf"],
        }.get(t, [conf_filename_for(t), f"{t.lower()}.conf"])
        # De-dupe while preserving order
        out: List[Path] = []
        seen = set()
        for n in names:
            p = ddir / n
            key = str(p)
            if key not in seen:
                seen.add(key)
                out.append(p)
        return out

    def _read_live_rpc_kv(self, ticker: str) -> Dict[str, str]:
        """Merge rpc_overrides + datadir conf so reattach keeps fallback ports."""
        t = ticker.upper()
        kv: Dict[str, str] = {}
        # Datadir conf first (source of truth for a running node)
        for p in self._datadir_conf_paths(t):
            if p.is_file():
                kv.update(self._read_kv_file(p))
        ov = (store.rpc_overrides() or {}).get(t) or {}
        conf_path = str(ov.get("conf") or "")
        if conf_path and Path(conf_path).is_file():
            kv.update(self._read_kv_file(Path(conf_path)))
        # Explicit overrides win only for user/password when present
        if ov.get("rpc_user"):
            kv["rpcuser"] = str(ov["rpc_user"])
        if ov.get("rpc_password"):
            kv["rpcpassword"] = str(ov["rpc_password"])
        if ov.get("rpc_host"):
            kv["rpcconnect"] = str(ov["rpc_host"])
        # Port: prefer conf (may be Hyper-V fallback) over stale catalog default
        # but if override matches a port that answers, probe will find it.
        if ov.get("rpc_port") and not kv.get("rpcport"):
            kv["rpcport"] = str(int(ov["rpc_port"]))
        return kv

    def _try_rpc_once(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        *,
        timeout: float = 1.5,
    ) -> Optional[Dict[str, Any]]:
        if not port or not user or not password:
            return None
        try:
            import requests

            r = requests.post(
                f"http://{host}:{int(port)}/",
                json={
                    "jsonrpc": "1.0",
                    "id": "mfq-probe",
                    "method": "getblockchaininfo",
                    "params": [],
                },
                auth=(user, password),
                timeout=timeout,
            )
            if r.status_code == 200 and not (r.json() or {}).get("error"):
                info = (r.json() or {}).get("result") or {}
                return {
                    "online": True,
                    "rpc_port": int(port),
                    "rpc_host": host,
                    "rpc_user": user,
                    "rpc_password": password,
                    "blocks": info.get("blocks"),
                }
        except Exception:
            pass
        return None

    def _rpc_probe_running(self, ticker: str) -> Dict[str, Any]:
        """True if local RPC answers (tries conf + override + candidate ports)."""
        t = ticker.upper()
        kv = self._read_live_rpc_kv(t)
        user = str(kv.get("rpcuser") or "")
        password = str(kv.get("rpcpassword") or "")
        host = str(
            kv.get("rpcconnect")
            or kv.get("rpcbind")
            or "127.0.0.1"
        )
        if host in ("0.0.0.0", "::", "[::]"):
            host = "127.0.0.1"
        if not user or not password:
            return {"online": False}

        ports: List[int] = []
        for raw in (
            kv.get("rpcport"),
            ((store.rpc_overrides() or {}).get(t) or {}).get("rpc_port"),
        ):
            try:
                p = int(raw or 0)
            except (TypeError, ValueError):
                p = 0
            if p and p not in ports:
                ports.append(p)
        # Also try known candidates — recovers after ensure_conf reset the
        # stored port back to the catalog default while the node still
        # listens on a Hyper-V fallback port.
        preferred = int(
            (self.pack_meta(t).get("rpc_port") or _default_ports(t)["rpc_port"] or 0)
        )
        for p in self._rpc_port_candidates(t, preferred):
            if p not in ports:
                ports.append(p)

        for port in ports:
            hit = self._try_rpc_once(host, port, user, password)
            if hit:
                # Heal overrides so UI keeps talking to the live port
                try:
                    self._persist_rpc_settings(
                        t,
                        rpc_user=user,
                        rpc_password=password,
                        rpc_port=int(hit["rpc_port"]),
                        rpc_host=host,
                    )
                except Exception:
                    pass
                return hit
        return {"online": False}

    def _persist_rpc_settings(
        self,
        ticker: str,
        *,
        rpc_user: str,
        rpc_password: str,
        rpc_port: int,
        rpc_host: str = "127.0.0.1",
    ) -> None:
        """Write app rpc template + settings overrides (no daemon conf rewrite)."""
        t = ticker.upper()
        rpc_tpl = store.rpc_dir() / f"{t.lower()}.conf"
        store.write_conf_template(
            t,
            rpc_user=rpc_user,
            rpc_password=rpc_password,
            rpc_port=int(rpc_port),
            rpc_host=rpc_host or "127.0.0.1",
            path=str(rpc_tpl),
        )
        ov = store.rpc_overrides()
        ov[t] = {
            "rpc_host": rpc_host or "127.0.0.1",
            "rpc_port": int(rpc_port),
            "rpc_user": rpc_user,
            "rpc_password": rpc_password,
            "conf": str(rpc_tpl),
        }
        store.set_rpc_overrides(ov)
        conf_ov = store.conf_overrides()
        conf_ov[t] = str(rpc_tpl)
        store.set_conf_overrides(conf_ov)

    def reattach_running(self, ticker: str) -> Optional[Dict[str, Any]]:
        """If a daemon is already up, resync UI credentials without rewriting ports.

        Critical: ensure_conf() must NOT reset rpcport/port to catalog defaults
        while azured/bloodstoned still listen on a Hyper-V fallback port —
        that is what made wallets “disconnect after startup”.
        """
        t = ticker.upper()
        st = self.status(t)
        if not st.get("running"):
            # Last chance: RPC may be up without a tracked pid
            probe = self._rpc_probe_running(t)
            if not probe.get("online"):
                return None
            st = {**st, "running": True}

        probe = self._rpc_probe_running(t)
        kv = self._read_live_rpc_kv(t)
        user = str(
            (probe or {}).get("rpc_user")
            or kv.get("rpcuser")
            or f"{t.lower()}rpc"
        )
        password = str(
            (probe or {}).get("rpc_password") or kv.get("rpcpassword") or ""
        )
        host = str((probe or {}).get("rpc_host") or "127.0.0.1")
        port = int((probe or {}).get("rpc_port") or kv.get("rpcport") or 0)
        if port and user and password:
            self._persist_rpc_settings(
                t,
                rpc_user=user,
                rpc_password=password,
                rpc_port=port,
                rpc_host=host,
            )
        conf_path = str(self._datadir_conf_paths(t)[0])
        for p in self._datadir_conf_paths(t):
            if p.is_file():
                conf_path = str(p)
                break
        self.log(
            f"{t} reattached "
            f"(pid {st.get('pid') or '?'} rpc :{port or '?'})"
        )
        return {
            **st,
            "running": True,
            "conf_path": conf_path,
            "datadir": str(datadir_for(t)),
            "rpc_user": user,
            "rpc_password": password,
            "rpc_port": port,
            "rpc_host": host,
            "p2p_port": int(kv.get("port") or 0) or None,
        }

    def status(self, ticker: str) -> Dict[str, Any]:
        t = ticker.upper()
        proc = self._procs.get(t)
        running = bool(proc and proc.poll() is None)
        pid = proc.pid if running and proc else None
        # Reattach: pid file / RPC probe when process not in this session
        if not running:
            fpid = self._read_pid_file(t)
            if self._pid_alive(fpid):
                running = True
                pid = fpid
            else:
                probe = self._rpc_probe_running(t)
                if probe.get("online"):
                    running = True
                    pid = fpid or pid
        path = self.daemon_path(t)
        pack = self.pack_meta(t)
        # Prefer live RPC port from overrides when known
        ov = (store.rpc_overrides() or {}).get(t) or {}
        if ov.get("rpc_port"):
            try:
                pack = dict(pack)
                pack["rpc_port"] = int(ov["rpc_port"])
            except (TypeError, ValueError):
                pass
        return {
            "ticker": t,
            "installed": path is not None,
            "daemon_path": str(path) if path else None,
            "running": running,
            "pid": pid,
            "datadir": str(datadir_for(t)),
            "pack": pack,
        }

    def status_all(self, tickers: List[str]) -> List[Dict[str, Any]]:
        return [self.status(t) for t in tickers]

    # ── download / install ─────────────────────────────────
    def ensure_installed(
        self,
        ticker: str,
        *,
        progress: Optional[ProgressFn] = None,
        force: bool = False,
    ) -> Path:
        t = ticker.upper()
        existing = self.daemon_path(t)
        if existing and not force:
            # Auto-heal: never keep a renamed-bloodstoned fork pack
            if t == "STONE" or not self.is_placeholder_fork_binary(t):
                return existing
            self.log(f"{t}: installed pack is a Bloodstone placeholder; replacing…")
            force = True

        if force:
            out = pack_dir(t)
            if out.exists():
                shutil.rmtree(out, ignore_errors=True)

        # Prefer bundled real pack (no network) before download
        bundled = self._copy_bundled(t)
        if bundled and (t == "STONE" or not self.is_placeholder_fork_binary(t)):
            return bundled

        meta = self.pack_meta(t)
        url = str(meta.get("url") or "")
        if not url:
            raise RuntimeError(f"No download URL for {t} daemon pack")

        dest_zip = daemons_root() / f"{t}-win64.zip"
        self.log(f"Downloading {t} daemon pack…")
        self._download(url, dest_zip, ticker=t, progress=progress)

        # SHA256 — prefer manifest field, then sidecar URL
        expected = str(meta.get("sha256") or "").strip().lower()
        if not expected:
            sha_url = meta.get("sha256_url") or (url + ".sha256")
            try:
                expected = self._fetch_text(str(sha_url)).split()[0].strip().lower()
            except Exception as exc:
                self.log(f"SHA URL fetch skipped for {t}: {exc}")
                expected = ""
        if expected:
            got = hashlib.sha256(dest_zip.read_bytes()).hexdigest()
            if got != expected:
                raise RuntimeError(
                    f"SHA256 mismatch for {t} pack: got {got[:12]}… want {expected[:12]}…"
                )
            self.log(f"{t} pack SHA256 OK")

        out = pack_dir(t)
        if out.exists():
            shutil.rmtree(out, ignore_errors=True)
        out.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(dest_zip, "r") as zf:
            zf.extractall(out)
        self._flatten_pack_dir(out, t)
        path = self.daemon_path(t)
        if not path:
            raise RuntimeError(f"Daemon binary not found after extracting {t} pack")
        self.log(f"Installed {t} daemon → {path}")
        return path

    def _copy_bundled(self, ticker: str) -> Optional[Path]:
        t = ticker.upper()
        if not self._bundled_root:
            # Last-chance discovery (shortcut launches often miss set_bundled_root)
            root = find_bundled_daemons_root()
            if root:
                self._bundled_root = root
                self.log(f"Discovered bundled daemons root: {root}")
            else:
                return None
        # force look only under bundled
        for sub in (
            self._bundled_root / "daemons" / t,
            self._bundled_root / "daemons" / t.lower(),
            self._bundled_root / "daemons" / f"{t}-win64",
        ):
            if not sub.is_dir():
                continue
            dest = pack_dir(t)
            if dest.exists():
                shutil.rmtree(dest, ignore_errors=True)
            dest.mkdir(parents=True, exist_ok=True)
            # Copy tree (files + nested folders), then flatten
            for item in sub.rglob("*"):
                if not item.is_file():
                    continue
                rel = item.relative_to(sub)
                target = dest / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, target)
            self._flatten_pack_dir(dest, t)
            found = self.daemon_path(t)
            if found:
                # Prefer installed copy under pack_dir
                if not str(found).startswith(str(dest)):
                    # daemon_path may still point at bundled; re-resolve after copy
                    found = None
                    for name in (
                        (self.pack_meta(t).get("daemon") or ""),
                        "daemon.exe",
                        f"{t.lower()}d.exe",
                        "bloodstoned.exe" if t == "STONE" else "",
                    ):
                        if name and (dest / name).is_file():
                            found = dest / name
                            break
                    if not found:
                        try:
                            found = next(dest.rglob("*d.exe"))
                        except StopIteration:
                            found = None
                if found:
                    self.log(f"Using bundled {t} daemon → {found}")
                    return found
        return None

    def _fetch_text(self, url: str) -> str:
        req = Request(url, headers={"User-Agent": "Bloodstone-MultiForkQt"})
        with urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8", errors="replace")

    def _download(
        self,
        url: str,
        dest: Path,
        *,
        ticker: str,
        progress: Optional[ProgressFn] = None,
    ) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        req = Request(url, headers={"User-Agent": "Bloodstone-MultiForkQt"})
        with urlopen(req, timeout=300) as resp:
            total = int(resp.headers.get("Content-Length") or 0)
            got = 0
            with open(tmp, "wb") as fh:
                while True:
                    chunk = resp.read(256 * 1024)
                    if not chunk:
                        break
                    fh.write(chunk)
                    got += len(chunk)
                    if progress and total:
                        progress(ticker, min(100, int(got * 100 / total)))
        tmp.replace(dest)
        if progress:
            progress(ticker, 100)

    # ── conf + process ─────────────────────────────────────
    def _read_kv_file(self, path: Path) -> Dict[str, str]:
        existing: Dict[str, str] = {}
        if not path.is_file():
            return existing
        try:
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                existing[k.strip()] = v.strip()
        except OSError:
            pass
        return existing

    def ensure_conf(
        self,
        ticker: str,
        *,
        rpc_port: Optional[int] = None,
        p2p_port: Optional[int] = None,
        rewrite: bool = True,
        pick_free_ports: bool = True,
    ) -> Dict[str, Any]:
        """Write datadir conf with credentials; return rpc settings.

        Important:
        - When the daemon is already running, call reattach_running() instead
          (or pass rewrite=False) so Hyper-V fallback ports are not reset.
        - Existing conf rpcport/port/credentials are preserved unless the
          caller explicitly passes rpc_port / p2p_port.
        """
        t = ticker.upper()
        meta = self.pack_meta(t)
        ports = _default_ports(t)
        ddir = datadir_for(t)
        ddir.mkdir(parents=True, exist_ok=True)

        # Canonical name matches BITCOIN_CONF_FILENAME in all three win64 builds.
        conf_name = conf_filename_for(t)
        conf_path = ddir / conf_name
        # Also merge credentials from older MFQ conf names if present
        alias_names = {
            "STONE": ["bloodstone.conf"],
            "AZURE": ["azure.conf", "bloodstone.conf"],
            "LRGK": ["lrgk.conf", "bloodstone.conf"],
        }.get(t, [f"{t.lower()}.conf", "bloodstone.conf"])

        existing: Dict[str, str] = {}
        for an in alias_names:
            existing.update(self._read_kv_file(ddir / an))
        existing.update(self._read_kv_file(conf_path))

        user = existing.get("rpcuser") or f"{t.lower()}rpc"
        password = existing.get("rpcpassword") or secrets.token_hex(16)
        if t == "STONE" and not existing.get("rpcuser"):
            user = "bloodstone"

        # Preserve live conf ports (Hyper-V fallback) unless caller forces them.
        try:
            existing_rpc = int(existing.get("rpcport") or 0)
        except (TypeError, ValueError):
            existing_rpc = 0
        try:
            existing_p2p = int(existing.get("port") or 0)
        except (TypeError, ValueError):
            existing_p2p = 0

        if rpc_port is None:
            rpc_port = existing_rpc or int(
                meta.get("rpc_port") or ports["rpc_port"] or 0
            )
        else:
            rpc_port = int(rpc_port)
        if p2p_port is None:
            p2p_port = existing_p2p or int(
                meta.get("p2p_port") or ports["p2p_port"] or 0
            )
        else:
            p2p_port = int(p2p_port)

        # All official seed peers (addnode=) — never a single exclusive connect=.
        peers = resolve_public_peers(t, meta=meta)

        # Only re-pick P2P when starting fresh (no conf port yet) or caller
        # asked for free-port selection. Never steal the port a live daemon
        # already holds — that rewrote conf to 17334/29826 and broke restarts.
        if pick_free_ports and not existing_p2p:
            p2p_candidates = {
                "STONE": [17333, 17334, 18333],
                "AZURE": [29825, 29826, 39825, 29835, 41012],
                "LRGK": [33685, 33686, 43685, 41023],
            }.get(t, [p2p_port, p2p_port + 1, p2p_port + 10])
            if p2p_port not in p2p_candidates:
                p2p_candidates = [p2p_port] + list(p2p_candidates)
            chosen_p2p = p2p_port
            for cand in p2p_candidates:
                if self._port_bindable(int(cand)):
                    chosen_p2p = int(cand)
                    break
            if chosen_p2p != p2p_port:
                self.log(
                    f"{t}: P2P port {p2p_port} busy/excluded; using {chosen_p2p}"
                )
                p2p_port = chosen_p2p

        if rewrite:
            lines = [
                f"# Managed by Bloodstone Multi-Fork Qt — {t}",
                "server=1",
                "listen=1",
                "txindex=0",
                f"port={p2p_port}",
                f"rpcport={rpc_port}",
                "rpcallowip=127.0.0.1",
                f"rpcuser={user}",
                f"rpcpassword={password}",
                "fallbackfee=0.0001",
                "maxtipage=999999999",
                # Keep dnsseed on for STONE (fixed/DNS seed path); forks have no DNS seeds.
                f"dnsseed={'1' if t == 'STONE' else '0'}",
                "discover=1",
                # Survive brief network stalls / low peer count on young forks (AZURE)
                "maxconnections=32",
            ]
            # One addnode= line per seed so the wallet keeps all official peers.
            for peer in peers:
                lines.append(f"addnode={peer}")
            if peers:
                self.log(f"{t}: seed addnodes → {', '.join(peers)}")
            body = "\n".join(lines) + "\n"
            conf_path.write_text(body, encoding="utf-8")
            # Human-friendly aliases so users browsing the datadir see ticker.conf
            for an in alias_names:
                if an == conf_name:
                    continue
                try:
                    (ddir / an).write_text(body, encoding="utf-8")
                except OSError:
                    pass
            # Drop stale settings.json that can re-apply old rpcport/rpcbind
            settings_json = ddir / "settings.json"
            if settings_json.is_file():
                try:
                    raw = settings_json.read_text(encoding="utf-8", errors="replace")
                    if any(
                        k in raw
                        for k in (
                            "rpcport",
                            "rpcbind",
                            "rpcuser",
                            "rpcpassword",
                            "server",
                        )
                    ):
                        bak = ddir / "settings.json.mfq-bak"
                        try:
                            settings_json.replace(bak)
                        except OSError:
                            settings_json.unlink()
                        self.log(
                            f"{t}: moved settings.json aside (could override RPC ports)"
                        )
                except OSError:
                    pass

        self._persist_rpc_settings(
            t,
            rpc_user=user,
            rpc_password=password,
            rpc_port=rpc_port,
            rpc_host="127.0.0.1",
        )

        return {
            "conf_path": str(conf_path),
            "datadir": str(ddir),
            "rpc_user": user,
            "rpc_password": password,
            "rpc_port": rpc_port,
            "rpc_host": "127.0.0.1",
            "p2p_port": p2p_port,
        }

    def _clear_stale_lock(self, ddir: str) -> None:
        """Remove .lock if no live process holds it (common after crash)."""
        lock = Path(ddir) / ".lock"
        if not lock.is_file():
            return
        # On Windows, if we can open exclusively the previous node is gone
        try:
            if _IS_WIN:
                # Best-effort: if lock is old and no tracked proc, remove
                age = time.time() - lock.stat().st_mtime
                if age > 30:
                    lock.unlink(missing_ok=True)  # type: ignore[arg-type]
                    self.log(f"Removed stale lock in {ddir}")
            else:
                # Linux: try non-blocking flock style — simply unlink if no pid file live
                lock.unlink(missing_ok=True)  # type: ignore[arg-type]
        except TypeError:
            # py3.7 compat
            try:
                if lock.is_file():
                    lock.unlink()
            except OSError:
                pass
        except OSError:
            pass

    def _port_bindable(self, port: int) -> bool:
        """True if we can bind 127.0.0.1:port (catches Windows excluded ranges).

        connect() is NOT enough: Hyper-V excluded ports refuse bind but nothing
        listens, so connect looks 'free' while azured still fails HTTP start.
        """
        if not port or port < 1024 or port > 65535:
            return False
        try:
            import socket

            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("127.0.0.1", int(port)))
            return True
        except OSError:
            return False

    def _rpc_port_candidates(self, ticker: str, preferred: int) -> List[int]:
        """Ordered RPC ports to try for this coin (avoid cross-coin clashes)."""
        t = ticker.upper()
        reserved = {
            "STONE": 18332,
            "AZURE": 49825,
            "LRGK": 53685,
        }
        # Prefer documented port, then safer alternatives away from Hyper-V
        # dynamic exclusions (often mid-40k/50k blocks on Win10/11).
        extras = {
            "STONE": [18332, 18432, 18532, 19001],
            "AZURE": [49825, 18445, 28425, 29425, 38425, 41011, 42011],
            "LRGK": [53685, 18455, 28455, 38455, 41022],
        }.get(t, [preferred, preferred + 1, preferred + 10])
        out: List[int] = []
        for p in [preferred] + extras:
            p = int(p or 0)
            if not p or p in out:
                continue
            # Never steal another coin's preferred port unless we are that coin
            clash = False
            for other, oport in reserved.items():
                if other != t and p == oport:
                    clash = True
                    break
            if clash:
                continue
            out.append(p)
        return out

    def _pick_rpc_port(self, ticker: str, preferred: int) -> int:
        for p in self._rpc_port_candidates(ticker, preferred):
            if self._port_bindable(p):
                if p != preferred:
                    self.log(
                        f"{ticker}: preferred RPC {preferred} not bindable; using {p}"
                    )
                return p
        # Last resort: OS-assigned ephemeral, then free it for the daemon
        try:
            import socket

            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", 0))
                p = int(s.getsockname()[1])
            self.log(f"{ticker}: using ephemeral RPC port {p}")
            return p
        except OSError:
            return int(preferred)

    def _who_holds_port(self, port: int) -> str:
        """Best-effort description of whatever blocks TCP port."""
        if not port:
            return ""
        if self._port_bindable(port):
            return ""
        # Identify which of our managed daemons use this port
        for tick, meta_ports in (
            ("STONE", 18332),
            ("AZURE", 49825),
            ("LRGK", 53685),
        ):
            try:
                pmeta = self.pack_meta(tick)
                p = int(pmeta.get("rpc_port") or meta_ports)
            except Exception:
                p = meta_ports
            if p == int(port):
                st = self.status(tick)
                if st.get("running"):
                    return f"{tick} daemon already running (pid {st.get('pid')})"
        # Foreign or zombie / Windows excluded range
        if _IS_WIN:
            try:
                out = subprocess.check_output(
                    [
                        "cmd",
                        "/c",
                        f'netstat -ano | findstr ":{int(port)}"',
                    ],
                    stderr=subprocess.DEVNULL,
                    text=True,
                    timeout=5,
                )
                line = (out or "").strip().splitlines()[:1]
                if line:
                    return f"TCP {port} busy: {line[0].strip()[:120]}"
            except Exception:
                pass
            return (
                f"TCP {port} not bindable (in use or Windows excluded port range "
                f"— common with Hyper-V)"
            )
        else:
            try:
                out = subprocess.check_output(
                    ["ss", "-lntp"],
                    stderr=subprocess.DEVNULL,
                    text=True,
                    timeout=5,
                )
                for line in out.splitlines():
                    if f":{int(port)}" in line:
                        return f"TCP {port} busy: {line.strip()[:120]}"
            except Exception:
                pass
        return f"TCP {port} not bindable"

    def _scrub_datadir_runtime(self, ddir: str) -> None:
        """Remove stale pid/lock files left by crashed nodes."""
        d = Path(ddir)
        for name in (
            ".lock",
            "azured.pid",
            "lrgkd.pid",
            "bloodstoned.pid",
            "bitcoind.pid",
            "spacexpansed.pid",
            "mfq-stderr.log",
        ):
            p = d / name
            try:
                if p.is_file():
                    # keep recent stderr for a moment — only wipe pid/lock always
                    if name == "mfq-stderr.log":
                        continue
                    p.unlink()
            except OSError:
                pass
        self._clear_stale_lock(ddir)

    def start(
        self,
        ticker: str,
        *,
        progress: Optional[ProgressFn] = None,
        allow_placeholder: bool = False,
    ) -> Dict[str, Any]:
        t = ticker.upper()
        with self._lock:
            # Prefer reattach — never rewrite conf ports on a live node.
            reattached = self.reattach_running(t)
            if reattached and reattached.get("running"):
                # Confirm RPC still answers; if not, fall through to restart.
                if reattached.get("rpc_port") and reattached.get("rpc_password"):
                    hit = self._try_rpc_once(
                        str(reattached.get("rpc_host") or "127.0.0.1"),
                        int(reattached["rpc_port"]),
                        str(reattached.get("rpc_user") or ""),
                        str(reattached.get("rpc_password") or ""),
                    )
                    if hit:
                        return {**reattached, **hit, "running": True}
                # Pid alive but RPC dead — do not start a second copy; report.
                if reattached.get("pid") and self._pid_alive(reattached.get("pid")):
                    self.log(
                        f"{t}: process alive (pid {reattached.get('pid')}) "
                        f"but RPC not answering — not double-starting"
                    )
                    return {**reattached, "running": True}

            # Drop dead tracked handles
            old = self._procs.get(t)
            if old is not None and old.poll() is not None:
                self._procs.pop(t, None)

            path = self.ensure_installed(t, progress=progress)
            if t != "STONE" and self.is_placeholder_fork_binary(t) and not allow_placeholder:
                raise RuntimeError(
                    f"{t} Windows daemon pack is a renamed Bloodstone (STONE) binary. "
                    f"It produces STONE addresses (S…/stone1…), not valid {t} addresses. "
                    f"Do not create wallets against it. "
                    f"Point Multi-Fork Qt at a real {t} node (RPC), or install a true "
                    f"{t} win64 build when published. Pack path: {path}"
                )

            # Prefer the rpcport already written for this datadir (Hyper-V
            # fallback). Only then try catalog defaults / alternates.
            meta = self.pack_meta(t)
            ports = _default_ports(t)
            preferred_rpc = int(meta.get("rpc_port") or ports["rpc_port"] or 0)
            existing_kv = self._read_live_rpc_kv(t)
            try:
                existing_rpc = int(existing_kv.get("rpcport") or 0)
            except (TypeError, ValueError):
                existing_rpc = 0
            candidates = self._rpc_port_candidates(t, preferred_rpc)
            if existing_rpc:
                candidates = [existing_rpc] + [
                    p for p in candidates if p != existing_rpc
                ]
            last_fail = ""
            from . import __version__ as _mfq_ver

            for attempt, try_port in enumerate(candidates):
                if not self._port_bindable(try_port):
                    # Port busy — might already be OUR daemon on this port.
                    hit = None
                    user = existing_kv.get("rpcuser") or ""
                    password = existing_kv.get("rpcpassword") or ""
                    if user and password:
                        hit = self._try_rpc_once(
                            "127.0.0.1", try_port, user, password
                        )
                    if hit:
                        self.log(
                            f"{t}: rpcport={try_port} already serving our node — reattach"
                        )
                        self._persist_rpc_settings(
                            t,
                            rpc_user=user,
                            rpc_password=password,
                            rpc_port=try_port,
                        )
                        return {
                            **self.status(t),
                            **hit,
                            "running": True,
                            "datadir": str(datadir_for(t)),
                            "conf_path": str(self._datadir_conf_paths(t)[0]),
                        }
                    last_fail = self._who_holds_port(try_port) or f"port {try_port} not bindable"
                    self.log(f"{t}: skip rpcport={try_port} ({last_fail})")
                    continue

                # Explicit rpc_port: write conf for THIS start only.
                # pick_free_ports=False preserves existing P2P when present.
                creds = self.ensure_conf(
                    t,
                    rpc_port=try_port,
                    pick_free_ports=not bool(existing_kv.get("port")),
                )
                ddir = creds["datadir"]
                conf = creds["conf_path"]
                self._scrub_datadir_runtime(ddir)

                log_path = Path(ddir) / "mfq-daemon.log"
                conf_name = Path(conf).name
                rpc_port = int(creds["rpc_port"])
                rpc_user = str(creds["rpc_user"])
                rpc_password = str(creds["rpc_password"])

                # Pin RPC on CLI (overrides azured default 53685 = LRGK clash).
                # Use rpcbind=127.0.0.1 only (skip ::1) — more reliable on Win.
                args = [
                    str(path),
                    f"-datadir={ddir}",
                    f"-conf={conf_name}",
                    f"-debuglogfile={log_path.name}",
                    "-printtoconsole=0",
                    "-server=1",
                    f"-rpcport={rpc_port}",
                    f"-rpcuser={rpc_user}",
                    f"-rpcpassword={rpc_password}",
                    "-rpcallowip=127.0.0.1",
                    "-rpcbind=127.0.0.1",
                ]
                self.log(
                    f"Starting {t} (MFQ {_mfq_ver}): {path.name} "
                    f"-datadir={ddir} -rpcport={rpc_port} attempt={attempt+1}"
                )

                err_path = Path(ddir) / "mfq-stderr.log"
                try:
                    err_path.write_bytes(b"")
                except OSError:
                    pass
                err_fh = open(err_path, "ab")
                creationflags = 0
                if _IS_WIN:
                    # CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS
                    # so azured keeps running when Multi-Fork Qt is closed.
                    creationflags = 0x08000000 | 0x00000200 | 0x00000008
                try:
                    try:
                        proc = subprocess.Popen(
                            args,
                            stdout=err_fh,
                            stderr=subprocess.STDOUT,
                            cwd=str(path.parent),
                            creationflags=creationflags if _IS_WIN else 0,
                            start_new_session=(not _IS_WIN),
                        )
                    except TypeError:
                        proc = subprocess.Popen(
                            args,
                            stdout=err_fh,
                            stderr=subprocess.STDOUT,
                            cwd=str(path.parent),
                            start_new_session=True,
                        )
                finally:
                    try:
                        err_fh.close()
                    except Exception:
                        pass

                self._procs[t] = proc
                try:
                    self._write_pid_file(t, proc.pid)
                except Exception:
                    pass

                deadline = time.time() + 20.0
                last_err = ""
                rpc_ok = False
                while time.time() < deadline:
                    if proc.poll() is not None:
                        tail = ""
                        try:
                            tail = err_path.read_text(
                                encoding="utf-8", errors="replace"
                            )[-1500:]
                        except OSError:
                            pass
                        debug_log = Path(ddir) / "debug.log"
                        bind_lines = ""
                        if debug_log.is_file():
                            try:
                                dtxt = debug_log.read_text(
                                    encoding="utf-8", errors="replace"
                                )
                                if not tail:
                                    tail = dtxt[-1500:]
                                bind_lines = "\n".join(
                                    ln
                                    for ln in dtxt.splitlines()
                                    if "Binding RPC" in ln
                                    or "HTTP" in ln
                                    or "rpc" in ln.lower()
                                    and "error" in ln.lower()
                                )[-800:]
                            except OSError:
                                pass
                        self._procs.pop(t, None)
                        low = (tail or "").lower()
                        last_fail = (
                            f"exit {proc.returncode} rpcport={rpc_port}\n"
                            f"{tail or '(no log)'}\n{bind_lines}"
                        )
                        if (
                            "unable to start http server" in low
                            or "binding rpc" in low
                        ):
                            self.log(
                                f"{t}: HTTP bind failed on {rpc_port}; trying next port"
                            )
                            break  # next candidate
                        # Another MFQ/instance already holds the datadir — reattach.
                        if (
                            "cannot obtain a lock" in low
                            or "lock file" in low
                            or "is probably already running" in low
                        ):
                            self.log(
                                f"{t}: datadir lock held — reattaching to existing node"
                            )
                            reatt = self.reattach_running(t)
                            if reatt and reatt.get("running"):
                                return reatt
                        raise RuntimeError(
                            f"{t} daemon exited immediately (code {proc.returncode}) "
                            f"[MFQ {_mfq_ver}]. binary={path} datadir={ddir}\n"
                            f"{last_fail}"
                        )
                    try:
                        import requests

                        r = requests.post(
                            f"http://127.0.0.1:{rpc_port}/",
                            json={
                                "jsonrpc": "1.0",
                                "id": "mfq-start",
                                "method": "getblockchaininfo",
                                "params": [],
                            },
                            auth=(rpc_user, rpc_password),
                            timeout=2.0,
                        )
                        if r.status_code == 200 and not (r.json() or {}).get("error"):
                            self.log(f"{t} RPC up on :{rpc_port}")
                            rpc_ok = True
                            break
                        last_err = f"HTTP {r.status_code}"
                    except Exception as exc:
                        last_err = str(exc)[:160]
                    time.sleep(0.5)
                else:
                    # still running, RPC slow — accept
                    if proc.poll() is None:
                        self.log(
                            f"{t} process running (pid {proc.pid}) "
                            f"RPC not ready yet: {last_err}"
                        )
                        rpc_ok = True

                if rpc_ok and proc.poll() is None:
                    result = {**self.status(t), **creds}
                    result["log_path"] = str(log_path)
                    result["stderr_path"] = str(err_path)
                    result["mfq_version"] = str(_mfq_ver)
                    if not result.get("running"):
                        raise RuntimeError(
                            f"{t} daemon failed to stay running after start. "
                            f"See {err_path}"
                        )
                    return result

                # ensure dead before next attempt
                if proc.poll() is None:
                    try:
                        proc.terminate()
                        proc.wait(timeout=5)
                    except Exception:
                        try:
                            proc.kill()
                        except Exception:
                            pass
                self._procs.pop(t, None)

            raise RuntimeError(
                f"{t} could not start HTTP/RPC server [MFQ {_mfq_ver}].\n"
                f"Tried ports: {candidates}\n"
                f"Last error:\n{last_fail}\n\n"
                f"STONE/LRGK working while AZURE fails is usually Windows "
                f"blocking port 49825 (Hyper-V excluded range). MFQ retries "
                f"alternate ports automatically — if you still see this, "
                f"reboot PC or run as admin once:\n"
                f"  netsh interface ipv4 show excludedportrange protocol=tcp\n"
                f"binary={path}"
            )

    def stop(self, ticker: str, *, timeout: float = 15.0) -> Dict[str, Any]:
        t = ticker.upper()
        with self._lock:
            proc = self._procs.get(t)
            pid = None
            if proc and proc.poll() is None:
                pid = proc.pid
            if pid is None:
                pid = self._read_pid_file(t)
            if pid is None and not proc:
                # Try stop via RPC if we only know credentials
                try:
                    ov = (store.rpc_overrides() or {}).get(t) or {}
                    if ov.get("rpc_port") and ov.get("rpc_user") and ov.get("rpc_password"):
                        import requests

                        requests.post(
                            f"http://127.0.0.1:{int(ov['rpc_port'])}/",
                            json={
                                "jsonrpc": "1.0",
                                "id": "mfq-stop",
                                "method": "stop",
                                "params": [],
                            },
                            auth=(str(ov["rpc_user"]), str(ov["rpc_password"])),
                            timeout=5,
                        )
                        time.sleep(1.0)
                except Exception:
                    pass
                self._procs.pop(t, None)
                try:
                    self._pid_file(t).unlink(missing_ok=True)  # type: ignore[arg-type]
                except Exception:
                    pass
                return self.status(t)

            self.log(f"Stopping {t} daemon (pid {pid})…")
            # Prefer clean RPC stop
            try:
                ov = (store.rpc_overrides() or {}).get(t) or {}
                if ov.get("rpc_port") and ov.get("rpc_user") and ov.get("rpc_password"):
                    import requests

                    requests.post(
                        f"http://127.0.0.1:{int(ov['rpc_port'])}/",
                        json={
                            "jsonrpc": "1.0",
                            "id": "mfq-stop",
                            "method": "stop",
                            "params": [],
                        },
                        auth=(str(ov["rpc_user"]), str(ov["rpc_password"])),
                        timeout=5,
                    )
                    time.sleep(1.2)
            except Exception:
                pass
            if proc and proc.poll() is None:
                try:
                    proc.terminate()
                except Exception:
                    pass
                try:
                    proc.wait(timeout=timeout)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
            elif pid and self._pid_alive(pid):
                try:
                    if _IS_WIN:
                        subprocess.run(
                            ["taskkill", "/PID", str(pid), "/F"],
                            capture_output=True,
                            timeout=10,
                        )
                    else:
                        os.kill(pid, 15)
                except Exception:
                    pass
            self._procs.pop(t, None)
            try:
                self._pid_file(t).unlink(missing_ok=True)  # type: ignore[arg-type]
            except Exception:
                pass
            return self.status(t)

    def stop_all(self) -> None:
        # Include reattached daemons (pid file / RPC) not just this session's Popen map.
        tickers = set(self._procs.keys())
        try:
            for t, ov in (store.rpc_overrides() or {}).items():
                if ov:
                    tickers.add(str(t).upper())
        except Exception:
            pass
        for t in ("STONE", "AZURE", "LRGK"):
            tickers.add(t)
        for t in list(tickers):
            try:
                if self.status(t).get("running"):
                    self.stop(t)
            except Exception:
                pass

    def activate(
        self,
        ticker: str,
        *,
        progress: Optional[ProgressFn] = None,
    ) -> Dict[str, Any]:
        """Download if needed, write conf, start daemon — used on coin select."""
        t = ticker.upper()
        self.log(f"Activating local daemon for {t}…")
        if not self._bundled_root:
            root = find_bundled_daemons_root()
            if root:
                self.set_bundled_root(str(root))
                self.log(f"Bundled daemons root: {root}")
        result = self.start(t, progress=progress)
        self.log(
            f"{t}: installed={result.get('installed')} running={result.get('running')} "
            f"rpc=127.0.0.1:{result.get('rpc_port')}"
        )
        return result


# Singleton used by UI
_manager: Optional[DaemonManager] = None


def get_manager() -> DaemonManager:
    global _manager
    if _manager is None:
        _manager = DaemonManager()
    return _manager
