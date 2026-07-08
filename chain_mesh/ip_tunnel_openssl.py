"""OpenSSL-backed TLS ClientHello template for mesh handshake (lab + production)."""

from __future__ import annotations

import base64
import re
import socket
import subprocess
from typing import Any, Dict, Optional, Tuple

from chain_mesh import ip_tunnel_tls as tls

LAB_HOST = "127.0.0.1"
LAB_PORT = 18443
LAB_SNI = "bloodstone-tls-lab"


def resolve_connect_host(connect_host: str) -> str:
    """Resolve hostname to IPv4 for openssl -connect and mesh dst_ip hints."""
    host = (connect_host or "").strip()
    if not host:
        return LAB_HOST
    if _is_ipv4(host):
        return host
    try:
        infos = socket.getaddrinfo(host, None, socket.AF_INET, socket.SOCK_STREAM)
        if infos:
            return str(infos[0][4][0])
    except socket.gaierror:
        pass
    return host


def _is_ipv4(addr: str) -> bool:
    parts = (addr or "").split(".")
    if len(parts) != 4:
        return False
    try:
        return all(0 <= int(p) <= 255 for p in parts)
    except ValueError:
        return False


def _parse_client_hello_handshake(record: bytes) -> bytearray:
    records = tls.parse_tls_records(record)
    if not records or records[0][5] != 0x01:
        raise ValueError("expected ClientHello TLS record")
    body = bytearray(records[0][5:])
    hs_len = (body[1] << 16) | (body[2] << 8) | body[3]
    if len(body) < 4 + hs_len:
        raise ValueError("ClientHello handshake truncated")
    return body


def _pack_client_hello_record(hs_body: bytearray) -> bytes:
    hs = bytes(hs_body[4:])
    hs_len = len(hs)
    header = bytearray(hs_body[:4])
    header[1] = (hs_len >> 16) & 0xFF
    header[2] = (hs_len >> 8) & 0xFF
    header[3] = hs_len & 0xFF
    handshake = bytes(header) + hs
    record = bytes([0x16, 0x03, 0x01]) + len(handshake).to_bytes(2, "big") + handshake
    return record


def _walk_client_hello_extensions(hs_body: bytearray) -> Tuple[int, int, list]:
    """Return (ext_block_start, ext_total_len, list of (type, start, len))."""
    hs = hs_body[4:]
    pos = 2 + 32
    pos += 1 + hs[pos]
    pos += 2 + ((hs[pos] << 8) | hs[pos + 1])
    pos += 1 + hs[pos]
    ext_total = (hs[pos] << 8) | hs[pos + 1]
    ext_start = pos + 2
    end = ext_start + ext_total
    entries = []
    p = ext_start
    while p + 4 <= end:
        ext_type = (hs[p] << 8) | hs[p + 1]
        ext_len = (hs[p + 2] << 8) | hs[p + 3]
        entries.append((ext_type, p, ext_len))
        p += 4 + ext_len
    return ext_start, ext_total, entries


def patch_client_hello_sni(record: bytes, sni_host: str) -> bytes:
    """Replace SNI hostname in a ClientHello record (rebuilds extensions if length changes)."""
    host_b = sni_host.encode("ascii")
    body = _parse_client_hello_handshake(record)
    hs = bytearray(body[4:])
    ext_start, ext_total, entries = _walk_client_hello_extensions(body)
    sni_idx = next((i for i, e in enumerate(entries) if e[0] == 0), None)
    if sni_idx is None:
        raise ValueError("ClientHello missing SNI extension")

    _, sni_off, sni_len = entries[sni_idx]
    old_sni = hs[sni_off : sni_off + sni_len]
    new_sni = bytearray([0x00, 0x00])
    new_sni += len(host_b).to_bytes(2, "big")
    new_sni += b"\x00"
    new_sni += len(host_b).to_bytes(2, "big")
    new_sni += host_b

    before = hs[:sni_off]
    after = hs[sni_off + sni_len : ext_start + ext_total]
    new_hs = before + new_sni + after
    delta = len(new_sni) - sni_len
    new_ext_total = ext_total + delta
    ext_len_pos = ext_start - 2
    new_hs[ext_len_pos : ext_len_pos + 2] = new_ext_total.to_bytes(2, "big")
    new_body = bytearray(body[:4]) + new_hs
    return _pack_client_hello_record(new_body)


def patch_client_hello_random(record: bytes, client_random: bytes) -> bytes:
    if len(client_random) != 32:
        raise ValueError("client_random must be 32 bytes")
    body = _parse_client_hello_handshake(record)
    hs = bytearray(body[4:])
    hs[2:34] = client_random
    new_body = bytearray(body[:4]) + hs
    return _pack_client_hello_record(new_body)


def patch_client_hello_key_share(record: bytes, public_key: bytes) -> bytes:
    if len(public_key) != 32:
        raise ValueError("X25519 public_key must be 32 bytes")
    needle = b"\x00\x1d\x00\x20"
    idx = record.find(needle)
    if idx < 0 or idx + 4 + len(public_key) > len(record):
        raise ValueError("ClientHello missing X25519 key_share")
    patched = bytearray(record)
    patched[idx + 4 : idx + 4 + len(public_key)] = public_key
    return bytes(patched)


def build_client_hello_openssl(
    *,
    host: str = LAB_SNI,
    connect_host: str = LAB_HOST,
    port: int = LAB_PORT,
) -> Dict[str, Any]:
    """Capture a valid ClientHello via openssl -msg (for mesh handshake flight 1)."""
    sni = (host or LAB_SNI).strip()
    resolved = resolve_connect_host(connect_host or LAB_HOST)
    port = int(port or LAB_PORT)
    target = f"{resolved}:{port}"
    proc = subprocess.run(
        [
            "openssl",
            "s_client",
            "-connect",
            target,
            "-servername",
            sni,
            "-groups",
            "X25519",
            "-msg",
        ],
        input="",
        capture_output=True,
        text=True,
        timeout=12,
        check=False,
    )
    hex_lines: list[str] = []
    capture = False
    expected_hs_len: Optional[int] = None
    for line in (proc.stdout or "").splitlines():
        if "ClientHello" in line and "Handshake" in line:
            m = re.search(r"\[length\s+([0-9a-fA-F]+)\]", line)
            if m:
                expected_hs_len = int(m.group(1), 16)
            capture = True
            continue
        if capture:
            if line.startswith("<<<") or (
                line.startswith(">>>") and "ClientHello" not in line
            ):
                break
            hex_lines.extend(re.findall(r"[0-9a-fA-F]{2}", line))
    if not hex_lines:
        err = (proc.stderr or proc.stdout or "").strip()[-200:]
        raise ValueError(f"openssl -msg did not yield ClientHello bytes: {err}")
    if hex_lines[0] != "01":
        for i, byte in enumerate(hex_lines):
            if byte == "01":
                hex_lines = hex_lines[i:]
                break
    if expected_hs_len and len(hex_lines) < expected_hs_len:
        err = (proc.stderr or proc.stdout or "").strip()[-200:]
        raise ValueError(
            f"openssl ClientHello truncated ({len(hex_lines)} < {expected_hs_len}): {err}"
        )
    if expected_hs_len:
        hex_lines = hex_lines[:expected_hs_len]
    hs = bytes.fromhex("".join(hex_lines))
    record = bytes([0x16, 0x03, 0x01]) + len(hs).to_bytes(2, "big") + hs
    parsed_sni = tls.parse_tls_sni(record) or ""
    if parsed_sni and parsed_sni != sni:
        record = patch_client_hello_sni(record, sni)
    return {
        "ok": True,
        "host": sni,
        "connect_host": connect_host or LAB_HOST,
        "connect_ip": resolved,
        "port": port,
        "client_hello_b64": base64.b64encode(record).decode("ascii"),
        "length": len(record),
        "sni": tls.parse_tls_sni(record) or sni,
        "source": "openssl-msg",
    }