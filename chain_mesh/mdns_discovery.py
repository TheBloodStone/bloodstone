"""mDNS discovery for Bloodstone DTN + LAN mesh (_bloodstone-dtn._tcp / _bloodstone-lan._tcp)."""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple

MDNS_DTN_SERVICE_TYPE = "_bloodstone-dtn._tcp.local."
MDNS_LAN_SERVICE_TYPE = "_bloodstone-lan._tcp.local."
MDNS_BROWSE_SEC = float(os.environ.get("DTN_MDNS_BROWSE_SEC", "3.0"))
MDNS_ENABLED = os.environ.get("DTN_MDNS_ENABLE", "1").strip() not in ("0", "false", "no")


def _now() -> int:
    return int(time.time())


def _node_id() -> str:
    return (os.environ.get("DTN_NODE_ID") or socket.gethostname() or "pi-edge").strip()[:64]


def _web_port() -> int:
    return int(os.environ.get("DTN_LAN_WEB_PORT", "8887"))


def _region() -> str:
    return (os.environ.get("DTN_DEFAULT_REGION", "global") or "global").strip()[:32]


def _lan_ip() -> str:
    explicit = (os.environ.get("DTN_MDNS_HOST") or os.environ.get("DTN_LAN_IP") or "").strip()
    if explicit:
        return explicit
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def _decode_prop(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _peer_url(
    host: str,
    port: int,
    *,
    tls: Optional[bool] = None,
    tls_port: Optional[int] = None,
) -> str:
    from chain_mesh import dtn_tls as tls_mod

    return tls_mod.peer_url(host, port, tls=tls, tls_port=tls_port)


def _zeroconf_available() -> bool:
    try:
        import zeroconf  # noqa: F401

        return True
    except ImportError:
        return False


def _avahi_available() -> bool:
    return os.path.isfile("/usr/bin/avahi-publish-service") and os.path.isfile(
        "/usr/bin/avahi-browse"
    )


def register_dtn_service(
    *,
    node_id: str = "",
    port: Optional[int] = None,
    region: str = "",
    host: str = "",
) -> Dict[str, Any]:
    """Register local _bloodstone-dtn._tcp mDNS service (Pi broadcast)."""
    if not MDNS_ENABLED:
        return {"ok": False, "error": "DTN_MDNS_ENABLE=0"}

    nid = (node_id or _node_id()).strip()[:64]
    reg = (region or _region()).strip()[:32]
    ip = (host or _lan_ip()).strip()
    web_port = int(port or _web_port())

    if _zeroconf_available():
        return _register_zeroconf(nid, ip, web_port, reg)

    if _avahi_available():
        return _register_avahi(nid, ip, web_port, reg)

    return {"ok": False, "error": "zeroconf or avahi required for mDNS register"}


def _register_zeroconf(node_id: str, ip: str, port: int, region: str) -> Dict[str, Any]:
    from zeroconf import IPVersion, ServiceInfo, Zeroconf

    try:
        addr = socket.inet_aton(ip)
    except OSError:
        return {"ok": False, "error": f"invalid LAN ip: {ip}"}

    hostname = (socket.gethostname() or "bloodstone").split(".")[0]
    service_name = f"{node_id}.{MDNS_DTN_SERVICE_TYPE}"
    from chain_mesh import dtn_tls as tls_mod

    props = {
        b"v": b"1",
        b"node_id": node_id.encode(),
        b"region": region.encode(),
        b"role": b"dtn",
        b"path": b"/api/convergence/dtn/status",
    }
    if tls_mod.DTN_TLS_PEER:
        props[b"tls"] = b"1"
        props[b"tls_port"] = str(tls_mod.DTN_LAN_TLS_PORT).encode()
    info = ServiceInfo(
        MDNS_DTN_SERVICE_TYPE,
        service_name,
        addresses=[addr],
        port=port,
        properties=props,
        server=f"{hostname}.local.",
    )
    zc = Zeroconf(ip_version=IPVersion.V4Only)
    zc.register_service(info)
    return {
        "ok": True,
        "backend": "zeroconf",
        "service_type": MDNS_DTN_SERVICE_TYPE,
        "service_name": service_name,
        "host": ip,
        "port": port,
        "node_id": node_id,
        "region": region,
        "zeroconf": zc,
        "service_info": info,
    }


_AVAHI_PROC: Optional[subprocess.Popen] = None


def _register_avahi(node_id: str, ip: str, port: int, region: str) -> Dict[str, Any]:
    global _AVAHI_PROC
    if _avahi_running():
        return {
            "ok": True,
            "backend": "avahi",
            "already_running": True,
            "node_id": node_id,
            "host": ip,
            "port": port,
        }
    name = re.sub(r"[^a-zA-Z0-9\-]", "-", node_id)[:48]
    from chain_mesh import dtn_tls as tls_mod

    cmd = [
        "avahi-publish-service",
        f"Bloodstone DTN {name}",
        "_bloodstone-dtn._tcp",
        str(port),
        f"node_id={node_id}",
        f"region={region}",
        "role=dtn",
        "v=1",
        f"host={ip}",
    ]
    if tls_mod.DTN_TLS_PEER:
        cmd.extend(["tls=1", f"tls_port={tls_mod.DTN_LAN_TLS_PORT}"])
    _AVAHI_PROC = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return {
        "ok": True,
        "backend": "avahi",
        "pid": _AVAHI_PROC.pid,
        "node_id": node_id,
        "host": ip,
        "port": port,
        "command": cmd,
    }


def _avahi_running() -> bool:
    global _AVAHI_PROC
    return _AVAHI_PROC is not None and _AVAHI_PROC.poll() is None


def browse_dtn_services(*, timeout_sec: Optional[float] = None) -> List[Dict[str, Any]]:
    """Browse LAN for _bloodstone-dtn._tcp services."""
    if not MDNS_ENABLED:
        return []
    wait = float(timeout_sec if timeout_sec is not None else MDNS_BROWSE_SEC)
    if _zeroconf_available():
        return _browse_zeroconf(wait)
    if _avahi_available():
        return _browse_avahi()
    return []


def _browse_zeroconf(timeout_sec: float) -> List[Dict[str, Any]]:
    from zeroconf import ServiceBrowser, ServiceStateChange, Zeroconf

    found: List[Dict[str, Any]] = []
    seen = set()

    class _Listener:
        def add_service(self, zc, type_, name) -> None:
            info = zc.get_service_info(type_, name, timeout=1500)
            if not info:
                return
            self._record(info, name)

        def update_service(self, zc, type_, name) -> None:
            info = zc.get_service_info(type_, name, timeout=1500)
            if info:
                self._record(info, name)

        def remove_service(self, zc, type_, name) -> None:
            return

        def _record(self, info, name: str) -> None:
            if not info.addresses:
                return
            ip = socket.inet_ntoa(info.addresses[0])
            key = f"{ip}:{info.port}:{name}"
            if key in seen:
                return
            seen.add(key)
            props = {_decode_prop(k): _decode_prop(v) for k, v in (info.properties or {}).items()}
            tls_hint = props.get("tls") in ("1", "true", "yes")
            tls_port = None
            if props.get("tls_port", "").isdigit():
                tls_port = int(props["tls_port"])
            found.append(
                {
                    "service_name": name,
                    "host": ip,
                    "port": int(info.port),
                    "base_url": _peer_url(
                        ip,
                        info.port,
                        tls=tls_hint if props.get("tls") else None,
                        tls_port=tls_port,
                    ),
                    "node_id": props.get("node_id") or name.split(".", 1)[0],
                    "region": props.get("region") or "global",
                    "tls": tls_hint,
                    "tls_port": tls_port,
                    "properties": props,
                    "source": "mdns",
                }
            )

    zc = Zeroconf()
    listener = _Listener()
    ServiceBrowser(zc, MDNS_DTN_SERVICE_TYPE, listener)
    time.sleep(max(0.5, timeout_sec))
    zc.close()
    return found


def _browse_avahi() -> List[Dict[str, Any]]:
    try:
        proc = subprocess.run(
            ["avahi-browse", "-art", "_bloodstone-dtn._tcp"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (subprocess.SubprocessError, FileNotFoundError):
        return []

    found: List[Dict[str, Any]] = []
    seen = set()
    for line in (proc.stdout or "").splitlines():
        if not line.startswith("="):
            continue
        parts = line.split(";")
        if len(parts) < 8:
            continue
        host = parts[7].strip()
        try:
            port = int(parts[8].strip())
        except (IndexError, ValueError):
            continue
        name = parts[3].strip() if len(parts) > 3 else ""
        props_raw = parts[9].strip() if len(parts) > 9 else ""
        props: Dict[str, str] = {}
        for chunk in re.split(r"[\t\s]+", props_raw):
            if "=" in chunk:
                k, v = chunk.split("=", 1)
                props[k.strip()] = v.strip().strip('"')
        key = f"{host}:{port}"
        if key in seen:
            continue
        seen.add(key)
        tls_hint = props.get("tls") in ("1", "true", "yes")
        tls_port = None
        if props.get("tls_port", "").isdigit():
            tls_port = int(props["tls_port"])
        found.append(
            {
                "service_name": name,
                "host": host,
                "port": port,
                "base_url": _peer_url(
                    host,
                    port,
                    tls=tls_hint if props.get("tls") else None,
                    tls_port=tls_port,
                ),
                "node_id": props.get("node_id") or name,
                "region": props.get("region") or "global",
                "tls": tls_hint,
                "tls_port": tls_port,
                "properties": props,
                "source": "mdns",
            }
        )
    return found


def discover_mdns_dtn_peers(*, register: bool = True) -> Dict[str, Any]:
    """Browse mDNS and optionally register peers in DTN peer table."""
    from chain_mesh import dtn_sync as dtn

    services = browse_dtn_services()
    registered = 0
    peers: List[Dict[str, Any]] = []
    local_id = _node_id()

    for svc in services:
        url = str(svc.get("base_url") or "")
        nid = str(svc.get("node_id") or "")
        if not url:
            continue
        if nid == local_id:
            continue
        peers.append(svc)
        if register:
            try:
                dtn.register_dtn_peer(
                    base_url=url,
                    node_id=nid,
                    region=str(svc.get("region") or ""),
                    source="mdns",
                    tls_hint=svc.get("tls"),
                    tls_port=svc.get("tls_port"),
                )
                registered += 1
            except ValueError:
                continue

    return {
        "ok": True,
        "service_type": MDNS_DTN_SERVICE_TYPE,
        "services_found": len(services),
        "peers_registered": registered,
        "services": peers,
    }


def mdns_status(*, include_browse: bool = False) -> Dict[str, Any]:
    from chain_mesh import dtn_tls as tls

    return {
        "ok": True,
        "enabled": MDNS_ENABLED,
        "service_type": MDNS_DTN_SERVICE_TYPE,
        "lan_service_type": MDNS_LAN_SERVICE_TYPE,
        "node_id": _node_id(),
        "lan_ip": _lan_ip(),
        "web_port": _web_port(),
        "tls_port": tls.DTN_LAN_TLS_PORT,
        "peer_tls": tls.DTN_TLS_PEER,
        "region": _region(),
        "zeroconf": _zeroconf_available(),
        "avahi": _avahi_available(),
        "avahi_running": _avahi_running(),
        "browse_sec": MDNS_BROWSE_SEC,
        "services": browse_dtn_services() if include_browse else None,
    }