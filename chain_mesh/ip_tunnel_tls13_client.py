"""TLS 1.3 client flight helpers for BSM4 mesh handshake lab."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import struct
import time
from typing import Any, Dict, List, Optional, Tuple

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from chain_mesh import db as mesh_db
from chain_mesh import ip_tunnel_openssl as tls_o
from chain_mesh import ip_tunnel_tls as tls_mod

SESSION_TTL_SEC = 300
CIPHER_TLS_AES_128_GCM_SHA256 = 0x1301
CIPHER_TLS_AES_256_GCM_SHA384 = 0x1302

_CIPHER_CFG = {
    CIPHER_TLS_AES_128_GCM_SHA256: {
        "hash": hashlib.sha256,
        "hash_len": 32,
        "key_len": 16,
        "iv_len": 12,
    },
    CIPHER_TLS_AES_256_GCM_SHA384: {
        "hash": hashlib.sha384,
        "hash_len": 48,
        "key_len": 32,
        "iv_len": 12,
    },
}


def _migrate_handshake_session_columns(conn) -> None:
    existing = {
        row["name"]
        for row in conn.execute(
            "PRAGMA table_info(chain_mesh_tls_handshake_sessions)"
        )
    }
    if "server_flight_b64" not in existing:
        conn.execute(
            "ALTER TABLE chain_mesh_tls_handshake_sessions "
            "ADD COLUMN server_flight_b64 TEXT NOT NULL DEFAULT ''"
        )
    if "cipher" not in existing:
        conn.execute(
            "ALTER TABLE chain_mesh_tls_handshake_sessions "
            "ADD COLUMN cipher INTEGER NOT NULL DEFAULT 0"
        )
    if "handshake_complete" not in existing:
        conn.execute(
            "ALTER TABLE chain_mesh_tls_handshake_sessions "
            "ADD COLUMN handshake_complete INTEGER NOT NULL DEFAULT 0"
        )


def _init_handshake_tables() -> None:
    with mesh_db._conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS chain_mesh_tls_handshake_sessions (
                handshake_id TEXT PRIMARY KEY,
                client_hello_b64 TEXT NOT NULL,
                private_key_b64 TEXT NOT NULL,
                host TEXT NOT NULL DEFAULT '',
                server_flight_b64 TEXT NOT NULL DEFAULT '',
                cipher INTEGER NOT NULL DEFAULT 0,
                handshake_complete INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_mesh_tls_hs_created
                ON chain_mesh_tls_handshake_sessions(created_at DESC);
            """
        )
        _migrate_handshake_session_columns(conn)


_init_handshake_tables()


def _purge_stale_sessions() -> None:
    cutoff = int(time.time()) - SESSION_TTL_SEC
    with mesh_db._conn() as conn:
        conn.execute(
            "DELETE FROM chain_mesh_tls_handshake_sessions WHERE created_at < ?",
            (cutoff,),
        )


def _hkdf_extract(salt: bytes, ikm: bytes, hash_mod) -> bytes:
    n = hash_mod().digest_size
    if not salt:
        salt = bytes(n)
    if not ikm:
        ikm = bytes(n)
    return hmac.new(salt, ikm, hash_mod).digest()


def _hkdf_expand_label(
    secret: bytes, label: str, context: bytes, length: int, hash_mod
) -> bytes:
    hkdf_label = (
        struct.pack(">H", length)
        + struct.pack("B", len(b"tls13 " + label.encode()))
        + b"tls13 "
        + label.encode()
        + struct.pack("B", len(context))
        + context
    )
    out = b""
    t = b""
    counter = 1
    while len(out) < length:
        t = hmac.new(
            secret, t + hkdf_label + struct.pack("B", counter), hash_mod
        ).digest()
        out += t
        counter += 1
    return out[:length]


def _derive_secret(
    secret: bytes, label: str, messages: bytes, hash_mod
) -> bytes:
    transcript_hash = hash_mod(messages).digest()
    return _hkdf_expand_label(
        secret, label, transcript_hash, hash_mod().digest_size, hash_mod
    )


def _traffic_keys(
    secret: bytes, label: str, messages: bytes, cipher: int
) -> Tuple[bytes, bytes]:
    cfg = _CIPHER_CFG[cipher]
    hs_secret = _derive_secret(secret, label, messages, cfg["hash"])
    key = _hkdf_expand_label(hs_secret, "key", b"", cfg["key_len"], cfg["hash"])
    iv = _hkdf_expand_label(hs_secret, "iv", b"", cfg["iv_len"], cfg["hash"])
    return key, iv


def _make_nonce(iv: bytes, seq: int) -> bytes:
    seq_bytes = struct.pack(">Q", seq)
    return iv[:4] + bytes(iv[i] ^ seq_bytes[i - 4] for i in range(4, 12))


def _aead_decrypt(
    key: bytes,
    iv: bytes,
    seq: int,
    ciphertext: bytes,
    record_header: bytes,
) -> bytes:
    nonce = _make_nonce(iv, seq)
    return AESGCM(key).decrypt(nonce, ciphertext, record_header)


def _aead_encrypt(
    key: bytes,
    iv: bytes,
    seq: int,
    plaintext: bytes,
    record_header: bytes,
) -> bytes:
    nonce = _make_nonce(iv, seq)
    return AESGCM(key).encrypt(nonce, plaintext, record_header)


def _handshake_message_from_record(record: bytes) -> bytes:
    """Handshake message bytes (type + length + body) from a TLS record."""
    return record[5:]


def _parse_server_hello(server_flight: bytes) -> Dict[str, Any]:
    records = tls_mod.parse_tls_records(server_flight)
    for rec in records:
        if rec[0] != tls_mod.TLS_HANDSHAKE or len(rec) < 6 or rec[5] != 0x02:
            continue
        body = rec[5:]
        hs_len = (body[1] << 16) | (body[2] << 8) | body[3]
        hs = body[4 : 4 + hs_len]
        pos = 2
        server_random = hs[pos : pos + 32]
        pos += 32
        sid_len = hs[pos]
        pos += 1 + sid_len
        cipher = (hs[pos] << 8) | hs[pos + 1]
        pos += 2
        pos += 1  # compression
        if pos + 2 > len(hs):
            raise ValueError("ServerHello extensions missing")
        ext_len = (hs[pos] << 8) | hs[pos + 1]
        pos += 2
        ext_end = pos + ext_len
        server_public = None
        while pos + 4 <= ext_end:
            ext_type = (hs[pos] << 8) | hs[pos + 1]
            e_len = (hs[pos + 2] << 8) | hs[pos + 3]
            pos += 4
            ext = hs[pos : pos + e_len]
            pos += e_len
            if ext_type == 0x0033 and len(ext) >= 4:
                k_len = (ext[2] << 8) | ext[3]
                if len(ext) >= 4 + k_len:
                    server_public = ext[4 : 4 + k_len]
        if not server_public:
            raise ValueError("ServerHello missing key_share")
        return {
            "record": rec,
            "server_random": server_random,
            "cipher": cipher,
            "server_public": server_public,
        }
    raise ValueError("ServerHello not found in server flight")





def _decrypt_server_handshakes(
    server_flight: bytes,
    *,
    client_hello: bytes,
    server_hello_record: bytes,
    handshake_secret: bytes,
    cipher: int,
) -> Tuple[bytes, List[bytes]]:
    cfg = _CIPHER_CFG[cipher]
    transcript = _handshake_message_from_record(
        client_hello
    ) + _handshake_message_from_record(server_hello_record)
    s_key, s_iv = _traffic_keys(
        handshake_secret, "s hs traffic", transcript, cipher
    )
    records = tls_mod.parse_tls_records(server_flight)
    plaintext_parts: List[bytes] = []
    seq = 0
    for rec in records:
        if rec[0] != tls_mod.TLS_APPLICATION_DATA:
            continue
        header = rec[:5]
        ciphertext = rec[5:]
        inner = _aead_decrypt(s_key, s_iv, seq, ciphertext, header)
        seq += 1
        content_type = inner[-1]
        hs_plain = inner[:-1]
        if content_type != tls_mod.TLS_HANDSHAKE:
            continue
        pos = 0
        while pos + 4 <= len(hs_plain):
            msg_len = (hs_plain[pos + 1] << 16) | (hs_plain[pos + 2] << 8) | hs_plain[pos + 3]
            msg = hs_plain[pos : pos + 4 + msg_len]
            plaintext_parts.append(msg)
            pos += 4 + msg_len
    transcript_full = transcript + b"".join(plaintext_parts)
    return transcript_full, plaintext_parts


def _compute_session_crypto(
    *,
    client_hello: bytes,
    private_key: X25519PrivateKey,
    server_flight: bytes,
) -> Dict[str, Any]:
    sh = _parse_server_hello(server_flight)
    cipher = int(sh["cipher"])
    if cipher not in _CIPHER_CFG:
        raise ValueError(f"unsupported cipher suite 0x{cipher:04x}")
    server_pub = X25519PublicKey.from_public_bytes(sh["server_public"])
    shared = private_key.exchange(server_pub)
    cfg = _CIPHER_CFG[cipher]
    hash_mod = cfg["hash"]

    early_secret = _hkdf_extract(b"", b"", hash_mod)
    derived = _hkdf_expand_label(
        early_secret, "derived", hash_mod(b"").digest(), cfg["hash_len"], hash_mod
    )
    handshake_secret = _hkdf_extract(derived, shared, hash_mod)
    transcript_to_sh = _handshake_message_from_record(
        client_hello
    ) + _handshake_message_from_record(sh["record"])
    transcript_full, _ = _decrypt_server_handshakes(
        server_flight,
        client_hello=client_hello,
        server_hello_record=sh["record"],
        handshake_secret=handshake_secret,
        cipher=cipher,
    )
    # RFC 8446: master = HKDF-Extract(
    #   Derive-Secret(handshake_secret, "derived", ""), zeros)
    derived_empty = _derive_secret(handshake_secret, "derived", b"", hash_mod)
    master_secret = _hkdf_extract(
        derived_empty, bytes(cfg["hash_len"]), hash_mod
    )
    # Application traffic uses Transcript-Hash(CH..ServerFinished) as context.
    s_app_key, s_app_iv = _traffic_keys(
        master_secret, "s ap traffic", transcript_full, cipher
    )
    c_app_key, c_app_iv = _traffic_keys(
        master_secret, "c ap traffic", transcript_full, cipher
    )
    return {
        "cipher": cipher,
        "handshake_secret": handshake_secret,
        "transcript_full": transcript_full,
        "server_hello_record": sh["record"],
        "s_app_key": s_app_key,
        "s_app_iv": s_app_iv,
        "c_app_key": c_app_key,
        "c_app_iv": c_app_iv,
    }


def encrypt_client_app_data(
    *,
    handshake_id: str = "",
    server_flight_b64: str = "",
    plaintext_b64: str = "",
    client_hello_b64: str = "",
    private_key_b64: str = "",
    seq_offset: int = 0,
) -> Dict[str, Any]:
    """Encrypt TLS 1.3 client application_data (e.g. HTTP request) after handshake."""
    if handshake_id:
        with mesh_db._conn() as conn:
            row = conn.execute(
                "SELECT * FROM chain_mesh_tls_handshake_sessions WHERE handshake_id = ?",
                (handshake_id.strip(),),
            ).fetchone()
        if not row:
            raise ValueError("handshake session not found or expired")
        client_hello = base64.b64decode(row["client_hello_b64"])
        private_key = X25519PrivateKey.from_private_bytes(
            base64.b64decode(row["private_key_b64"])
        )
        server_flight = base64.b64decode(
            server_flight_b64 or row["server_flight_b64"] or ""
        )
    else:
        client_hello = base64.b64decode(client_hello_b64)
        private_key = X25519PrivateKey.from_private_bytes(
            base64.b64decode(private_key_b64)
        )
        server_flight = base64.b64decode(server_flight_b64)
    if not server_flight:
        raise ValueError("server_flight_b64 required")
    plaintext = base64.b64decode(plaintext_b64)
    if not plaintext:
        raise ValueError("plaintext_b64 required")

    state = _compute_session_crypto(
        client_hello=client_hello,
        private_key=private_key,
        server_flight=server_flight,
    )
    inner = plaintext + bytes([tls_mod.TLS_APPLICATION_DATA])
    ciphertext_len = len(inner) + 16
    header = bytes([tls_mod.TLS_APPLICATION_DATA, 0x03, 0x03]) + struct.pack(
        ">H", ciphertext_len
    )
    ciphertext = _aead_encrypt(
        state["c_app_key"],
        state["c_app_iv"],
        int(seq_offset),
        inner,
        header,
    )
    record = header + ciphertext
    return {
        "ok": True,
        "handshake_id": handshake_id or None,
        "cipher": f"0x{int(state['cipher']):04x}",
        "seq": int(seq_offset),
        "length": len(record),
        "app_data_b64": base64.b64encode(record).decode("ascii"),
    }


def decrypt_server_app_data(
    *,
    handshake_id: str = "",
    server_flight_b64: str = "",
    app_data_b64: str = "",
    client_hello_b64: str = "",
    private_key_b64: str = "",
    seq_offset: int = 0,
) -> Dict[str, Any]:
    """Decrypt TLS 1.3 server application_data records after handshake."""
    if handshake_id:
        with mesh_db._conn() as conn:
            row = conn.execute(
                "SELECT * FROM chain_mesh_tls_handshake_sessions WHERE handshake_id = ?",
                (handshake_id.strip(),),
            ).fetchone()
        if not row:
            raise ValueError("handshake session not found or expired")
        client_hello = base64.b64decode(row["client_hello_b64"])
        private_key = X25519PrivateKey.from_private_bytes(
            base64.b64decode(row["private_key_b64"])
        )
        server_flight = base64.b64decode(
            server_flight_b64 or row["server_flight_b64"] or ""
        )
    else:
        client_hello = base64.b64decode(client_hello_b64)
        private_key = X25519PrivateKey.from_private_bytes(
            base64.b64decode(private_key_b64)
        )
        server_flight = base64.b64decode(server_flight_b64)
    if not server_flight:
        raise ValueError("server_flight_b64 required")
    app_bytes = base64.b64decode(app_data_b64)
    if not app_bytes:
        raise ValueError("app_data_b64 required")

    state = _compute_session_crypto(
        client_hello=client_hello,
        private_key=private_key,
        server_flight=server_flight,
    )
    s_key = state["s_app_key"]
    s_iv = state["s_app_iv"]
    plaintext_parts: List[bytes] = []
    seq = int(seq_offset)
    records = 0
    ticket_records = 0
    for rec in tls_mod.parse_tls_records(app_bytes):
        if rec[0] != tls_mod.TLS_APPLICATION_DATA:
            continue
        header = rec[:5]
        inner = _aead_decrypt(s_key, s_iv, seq, rec[5:], header)
        seq += 1
        records += 1
        content_type = inner[-1]
        body = inner[:-1]
        if content_type == tls_mod.TLS_HANDSHAKE:
            ticket_records += 1
            continue
        if content_type == tls_mod.TLS_APPLICATION_DATA:
            plaintext_parts.append(body)
    plaintext = b"".join(plaintext_parts)
    preview = plaintext[:512].decode("utf-8", errors="replace")
    return {
        "ok": True,
        "handshake_id": handshake_id or None,
        "cipher": f"0x{int(state['cipher']):04x}",
        "records": records,
        "ticket_records": ticket_records,
        "seq_offset": int(seq_offset),
        "next_seq": seq,
        "bytes": len(plaintext),
        "plaintext_b64": base64.b64encode(plaintext).decode("ascii"),
        "preview": preview,
        "is_http": preview.startswith("HTTP/") or preview.startswith("<"),
    }


def build_client_hello_session(
    *,
    host: str = "",
    connect_host: str = "",
    port: int = 0,
) -> Dict[str, Any]:
    """Build ClientHello with server-stored X25519 key for flight 2."""
    _purge_stale_sessions()
    host = host or tls_o.LAB_SNI
    connect_host = connect_host or tls_o.LAB_HOST
    port = int(port or tls_o.LAB_PORT)

    hello_meta = tls_o.build_client_hello_openssl(
        host=host, connect_host=connect_host, port=port
    )
    template = base64.b64decode(hello_meta["client_hello_b64"])

    private_key = X25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    client_random = secrets.token_bytes(32)
    record = tls_o.patch_client_hello_random(template, client_random)
    client_hello = tls_o.patch_client_hello_key_share(record, public_key)

    handshake_id = secrets.token_hex(16)
    now = int(time.time())
    with mesh_db._conn() as conn:
        conn.execute(
            """
            INSERT INTO chain_mesh_tls_handshake_sessions
                (handshake_id, client_hello_b64, private_key_b64, host, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                handshake_id,
                base64.b64encode(client_hello).decode(),
                base64.b64encode(
                    private_key.private_bytes(
                        encoding=serialization.Encoding.Raw,
                        format=serialization.PrivateFormat.Raw,
                        encryption_algorithm=serialization.NoEncryption(),
                    )
                ).decode(),
                host,
                now,
            ),
        )

    return {
        "ok": True,
        "handshake_id": handshake_id,
        "host": host,
        "connect_host": hello_meta.get("connect_host") or connect_host,
        "connect_ip": hello_meta.get("connect_ip") or connect_host,
        "port": port,
        "sni": hello_meta.get("sni") or host,
        "client_hello_b64": base64.b64encode(client_hello).decode(),
        "length": len(client_hello),
        "source": "tls13-session",
    }


def build_client_flight2(
    *,
    handshake_id: str,
    server_flight_b64: str,
) -> Dict[str, Any]:
    """Compute TLS 1.3 client flight 2 (CCS + encrypted Finished) for mesh relay."""
    _purge_stale_sessions()
    handshake_id = (handshake_id or "").strip()
    if not handshake_id:
        raise ValueError("handshake_id required")
    if not server_flight_b64:
        raise ValueError("server_flight_b64 required")

    with mesh_db._conn() as conn:
        row = conn.execute(
            "SELECT * FROM chain_mesh_tls_handshake_sessions WHERE handshake_id = ?",
            (handshake_id,),
        ).fetchone()
    if not row:
        raise ValueError("handshake session not found or expired")

    client_hello = base64.b64decode(row["client_hello_b64"])
    private_key = X25519PrivateKey.from_private_bytes(
        base64.b64decode(row["private_key_b64"])
    )
    server_flight = base64.b64decode(server_flight_b64)

    state = _compute_session_crypto(
        client_hello=client_hello,
        private_key=private_key,
        server_flight=server_flight,
    )
    cipher = int(state["cipher"])
    cfg = _CIPHER_CFG[cipher]
    hash_mod = cfg["hash"]
    sh = _parse_server_hello(server_flight)
    transcript_to_sh = _handshake_message_from_record(
        client_hello
    ) + _handshake_message_from_record(sh["record"])
    transcript_full = state["transcript_full"]
    handshake_secret = state["handshake_secret"]

    c_key, c_iv = _traffic_keys(
        handshake_secret, "c hs traffic", transcript_to_sh, cipher
    )
    c_hs_secret = _derive_secret(
        handshake_secret, "c hs traffic", transcript_to_sh, hash_mod
    )
    finished_key = _hkdf_expand_label(
        c_hs_secret, "finished", b"", cfg["hash_len"], hash_mod
    )
    verify_data = hmac.new(
        finished_key, hash_mod(transcript_full).digest(), hash_mod
    ).digest()

    finished_hs = bytes([0x14]) + struct.pack(">I", len(verify_data))[1:] + verify_data
    finished_inner = finished_hs + bytes([tls_mod.TLS_HANDSHAKE])
    ciphertext_len = len(finished_inner) + 16
    header = bytes([tls_mod.TLS_APPLICATION_DATA, 0x03, 0x03]) + struct.pack(
        ">H", ciphertext_len
    )
    ciphertext = _aead_encrypt(c_key, c_iv, 0, finished_inner, header)
    finished_record = header + ciphertext

    ccs_record = bytes([tls_mod.TLS_CHANGE_CIPHER_SPEC, 0x03, 0x03, 0x00, 0x01, 0x01])
    flight2 = ccs_record + finished_record

    with mesh_db._conn() as conn:
        conn.execute(
            """
            UPDATE chain_mesh_tls_handshake_sessions
            SET server_flight_b64 = ?, cipher = ?, handshake_complete = 1
            WHERE handshake_id = ?
            """,
            (
                base64.b64encode(server_flight).decode(),
                cipher,
                handshake_id,
            ),
        )

    return {
        "ok": True,
        "handshake_id": handshake_id,
        "client_flight2_b64": base64.b64encode(flight2).decode(),
        "length": len(flight2),
        "cipher": f"0x{cipher:04x}",
        "transcript_messages": len(tls_mod.parse_tls_records(client_hello)) + 1,
        "summary": f"CCS + ClientFinished ({len(flight2)} B)",
    }