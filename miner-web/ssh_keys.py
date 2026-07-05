"""SSH key inventory and admin helpers for the mining VPS."""

from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

SSH_DIR = os.environ.get("BLOODSTONE_SSH_DIR", "/root/.ssh")
REGISTRY_PATH = os.environ.get(
    "BLOODSTONE_SSH_REGISTRY", "/var/lib/bloodstone/ssh-key-registry.json"
)
_PUBKEY_PREFIXES = ("ssh-ed25519 ", "ssh-rsa ", "ecdsa-sha2-nistp256 ", "ssh-dss ")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _safe_name(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", (name or "").strip()).strip("-")
    if not cleaned:
        raise ValueError("Key name is required (letters, numbers, . _ - only).")
    if cleaned.startswith("."):
        raise ValueError("Invalid key name.")
    return cleaned[:64]


def _read_registry() -> Dict[str, Any]:
    try:
        with open(REGISTRY_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write_registry(data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(REGISTRY_PATH) or ".", exist_ok=True)
    tmp = f"{REGISTRY_PATH}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, REGISTRY_PATH)


def _fingerprint(pub_path: str) -> str:
    try:
        out = subprocess.check_output(
            ["ssh-keygen", "-lf", pub_path],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        return out.split()[1] if out else ""
    except (subprocess.CalledProcessError, FileNotFoundError, IndexError):
        return ""


def _parse_authorized_line(line: str) -> Optional[Dict[str, str]]:
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    parts = line.split()
    if len(parts) < 2:
        return None
    key_type, key_data = parts[0], parts[1]
    comment = " ".join(parts[2:]) if len(parts) > 2 else ""
    return {
        "line": line,
        "key_type": key_type,
        "key_data": key_data,
        "comment": comment,
        "fingerprint": _fingerprint_from_blob(f"{key_type} {key_data}"),
    }


def _fingerprint_from_blob(pub_blob: str) -> str:
    try:
        proc = subprocess.run(
            ["ssh-keygen", "-lf", "-"],
            input=pub_blob + "\n",
            capture_output=True,
            text=True,
            check=False,
        )
        out = (proc.stdout or "").strip()
        return out.split()[1] if out else ""
    except (FileNotFoundError, IndexError):
        return ""


def validate_public_key(line: str) -> str:
    cleaned = " ".join((line or "").strip().split())
    if not cleaned:
        raise ValueError("Public key line is empty.")
    if not cleaned.startswith(_PUBKEY_PREFIXES):
        raise ValueError("Unsupported or invalid public key format.")
    parts = cleaned.split()
    if len(parts) < 2:
        raise ValueError("Public key line is incomplete.")
    return cleaned


def list_key_pairs() -> List[Dict[str, Any]]:
    pairs: List[Dict[str, Any]] = []
    registry = _read_registry()
    if not os.path.isdir(SSH_DIR):
        return pairs
    for entry in sorted(os.listdir(SSH_DIR)):
        if not entry.endswith(".pub"):
            continue
        pub_path = os.path.join(SSH_DIR, entry)
        priv_path = pub_path[:-4]
        if not os.path.isfile(priv_path):
            continue
        try:
            with open(pub_path, encoding="utf-8") as fh:
                pub_line = fh.read().strip()
        except OSError:
            pub_line = ""
        meta = registry.get(entry, {})
        pairs.append(
            {
                "name": entry[:-4],
                "public_path": pub_path,
                "private_path": priv_path,
                "public_key": pub_line,
                "fingerprint": _fingerprint(pub_path),
                "created_at": meta.get("created_at", ""),
                "comment": meta.get("comment", ""),
            }
        )
    return pairs


def list_authorized_keys() -> List[Dict[str, str]]:
    path = os.path.join(SSH_DIR, "authorized_keys")
    if not os.path.isfile(path):
        return []
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError:
        return []
    out: List[Dict[str, str]] = []
    for line in lines:
        parsed = _parse_authorized_line(line)
        if parsed:
            out.append(parsed)
    return out


def admin_snapshot() -> Dict[str, Any]:
    return {
        "ssh_dir": SSH_DIR,
        "key_pairs": list_key_pairs(),
        "authorized_keys": list_authorized_keys(),
        "server_host": os.environ.get("MINER_VPS_IP", "64.188.22.190"),
        "secondary_host": os.environ.get(
            "BLOODSTONE_SECONDARY_VPS_HOST", "192.119.82.145"
        ),
    }


def generate_key_pair(name: str, comment: str = "") -> Dict[str, str]:
    safe = _safe_name(name)
    os.makedirs(SSH_DIR, exist_ok=True)
    priv_path = os.path.join(SSH_DIR, safe)
    pub_path = f"{priv_path}.pub"
    if os.path.exists(priv_path) or os.path.exists(pub_path):
        raise ValueError(f"Key '{safe}' already exists.")
    label = (comment or f"bloodstone-{safe}").strip() or f"bloodstone-{safe}"
    subprocess.run(
        [
            "ssh-keygen",
            "-t",
            "ed25519",
            "-f",
            priv_path,
            "-N",
            "",
            "-C",
            label,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    os.chmod(priv_path, 0o600)
    os.chmod(pub_path, 0o644)
    with open(pub_path, encoding="utf-8") as fh:
        pub_line = fh.read().strip()
    registry = _read_registry()
    registry[f"{safe}.pub"] = {
        "created_at": _now_iso(),
        "comment": label,
        "name": safe,
    }
    _write_registry(registry)
    return {
        "name": safe,
        "public_key": pub_line,
        "fingerprint": _fingerprint(pub_path),
        "private_path": priv_path,
        "public_path": pub_path,
    }


def add_authorized_key(public_key: str) -> Dict[str, str]:
    line = validate_public_key(public_key)
    os.makedirs(SSH_DIR, exist_ok=True)
    path = os.path.join(SSH_DIR, "authorized_keys")
    existing = list_authorized_keys()
    fp = _fingerprint_from_blob(line)
    if any(row.get("fingerprint") == fp and fp for row in existing):
        raise ValueError("That public key is already authorized on this server.")
    with open(path, "a", encoding="utf-8") as fh:
        if os.path.getsize(path) > 0:
            fh.write("\n")
        fh.write(line + "\n")
    os.chmod(path, 0o600)
    return {"public_key": line, "fingerprint": fp}


def revoke_authorized_key(fingerprint: str) -> bool:
    fp = (fingerprint or "").strip()
    if not fp:
        raise ValueError("Fingerprint is required.")
    path = os.path.join(SSH_DIR, "authorized_keys")
    if not os.path.isfile(path):
        return False
    with open(path, encoding="utf-8") as fh:
        lines = fh.readlines()
    kept = []
    removed = False
    for raw in lines:
        parsed = _parse_authorized_line(raw)
        if parsed and parsed.get("fingerprint") == fp:
            removed = True
            continue
        kept.append(raw)
    if not removed:
        raise ValueError("Authorized key not found.")
    with open(path, "w", encoding="utf-8") as fh:
        fh.writelines(kept)
    os.chmod(path, 0o600)
    return True


def read_public_key_file(name: str) -> str:
    safe = _safe_name(name)
    pub_path = os.path.join(SSH_DIR, f"{safe}.pub")
    if not os.path.isfile(pub_path):
        raise FileNotFoundError(f"Public key '{safe}' not found.")
    with open(pub_path, encoding="utf-8") as fh:
        return fh.read().strip()