"""TLS record helpers for BSM4 end-to-end passthrough."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

TLS_HANDSHAKE = 0x16
TLS_CHANGE_CIPHER_SPEC = 0x14
TLS_ALERT = 0x15
TLS_APPLICATION_DATA = 0x17

TLS_CLIENT_HELLO = 0x01
TLS_SERVER_HELLO = 0x02
TLS_ENCRYPTED_EXTENSIONS = 0x08
TLS_CERTIFICATE = 0x0B
TLS_FINISHED = 0x14


def is_tls_record(payload: bytes) -> bool:
    """True if payload looks like a TLS record (v1.x)."""
    if not payload or len(payload) < 5:
        return False
    if payload[0] not in (
        TLS_HANDSHAKE,
        TLS_CHANGE_CIPHER_SPEC,
        TLS_ALERT,
        TLS_APPLICATION_DATA,
    ):
        return False
    major = payload[1]
    return major == 0x03 and payload[2] in (0x00, 0x01, 0x02, 0x03, 0x04)


def tls_record_type_name(record_type: int) -> str:
    return {
        TLS_HANDSHAKE: "handshake",
        TLS_CHANGE_CIPHER_SPEC: "change_cipher_spec",
        TLS_ALERT: "alert",
        TLS_APPLICATION_DATA: "application_data",
    }.get(record_type, f"tls-{record_type}")


def parse_tls_records(payload: bytes) -> List[bytes]:
    """Split a TCP payload into individual TLS records."""
    records: List[bytes] = []
    pos = 0
    while pos + 5 <= len(payload):
        rec_len = (payload[pos + 3] << 8) | payload[pos + 4]
        end = pos + 5 + rec_len
        if end > len(payload):
            break
        records.append(payload[pos:end])
        pos = end
    return records


def parse_tls_sni(payload: bytes) -> Optional[str]:
    """Extract SNI hostname from a TLS ClientHello record."""
    if not is_tls_record(payload) or payload[0] != TLS_HANDSHAKE:
        return None
    try:
        rec_len = (payload[3] << 8) | payload[4]
        body = payload[5 : 5 + rec_len]
        if len(body) < 4 or body[0] != TLS_CLIENT_HELLO:
            return None
        pos = 4
        pos += 2  # client version
        pos += 32  # random
        if pos >= len(body):
            return None
        sid_len = body[pos]
        pos += 1 + sid_len
        if pos + 2 > len(body):
            return None
        cs_len = (body[pos] << 8) | body[pos + 1]
        pos += 2 + cs_len
        if pos >= len(body):
            return None
        comp_len = body[pos]
        pos += 1 + comp_len
        if pos + 2 > len(body):
            return None
        ext_total = (body[pos] << 8) | body[pos + 1]
        pos += 2
        end = pos + ext_total
        while pos + 4 <= end and pos + 4 <= len(body):
            ext_type = (body[pos] << 8) | body[pos + 1]
            ext_len = (body[pos + 2] << 8) | body[pos + 3]
            pos += 4
            ext_data = body[pos : pos + ext_len]
            pos += ext_len
            if ext_type == 0 and len(ext_data) >= 5:
                name_len = (ext_data[3] << 8) | ext_data[4]
                host = ext_data[5 : 5 + name_len]
                return host.decode("ascii", errors="replace")
    except Exception:
        return None
    return None


def handshake_phase_summary(payload: bytes) -> Dict[str, Any]:
    """Summarize TLS handshake records in a TCP payload."""
    records = parse_tls_records(payload)
    phases: List[str] = []
    has_alert = False
    sni = None
    for rec in records:
        if rec[0] == TLS_ALERT:
            has_alert = True
            phases.append("alert")
            continue
        if rec[0] != TLS_HANDSHAKE or len(rec) < 6:
            phases.append(tls_record_type_name(rec[0]))
            continue
        hs_type = rec[5]
        if hs_type == TLS_CLIENT_HELLO:
            phases.append("ClientHello")
            sni = parse_tls_sni(rec) or sni
        elif hs_type == TLS_SERVER_HELLO:
            phases.append("ServerHello")
        elif hs_type == TLS_CERTIFICATE:
            phases.append("Certificate")
        elif hs_type == TLS_ENCRYPTED_EXTENSIONS:
            phases.append("EncryptedExtensions")
        elif hs_type == TLS_FINISHED:
            phases.append("Finished")
        else:
            phases.append(f"hs-{hs_type:02x}")
    return {
        "records": len(records),
        "phases": phases,
        "has_alert": has_alert,
        "has_server_hello": "ServerHello" in phases,
        "sni": sni,
    }


def summarize_tls_payload(payload: bytes) -> str:
    if not payload:
        return "tls (empty)"
    if not is_tls_record(payload):
        return f"tls? ({payload[0]:02x})"
    info = handshake_phase_summary(payload)
    if info["phases"]:
        extra = " + ".join(info["phases"][:4])
        if len(info["phases"]) > 4:
            extra += f" (+{len(info['phases']) - 4})"
        if info.get("sni"):
            extra = f"{extra} sni={info['sni']}"
        rec = payload[0]
        ver = f"{payload[1]}.{payload[2]:02d}"
        return f"tls {tls_record_type_name(rec)} v{ver} {extra}"
    rec_type = payload[0]
    ver = f"{payload[1]}.{payload[2]:02d}"
    name = tls_record_type_name(rec_type)
    extra = ""
    if rec_type == TLS_HANDSHAKE and len(payload) > 5:
        hs = payload[5]
        if hs == TLS_CLIENT_HELLO:
            sni = parse_tls_sni(payload)
            extra = f" ClientHello sni={sni or '?'}"
        elif hs == TLS_SERVER_HELLO:
            extra = " ServerHello"
        else:
            extra = f" hs={hs:02x}"
    return f"tls {name} v{ver}{extra}"