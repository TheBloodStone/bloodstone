"""Read and write key=value service settings files."""

from __future__ import annotations

import os
from typing import Dict, Iterable, Optional


def read_kv(path: str, defaults: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    values = dict(defaults or {})
    if not os.path.isfile(path):
        return values
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            values[key.strip()] = val.strip()
    return values


def write_kv(
    path: str,
    updates: Dict[str, str],
    preserve_keys: Optional[Iterable[str]] = None,
    header: Optional[str] = None,
) -> None:
    preserve = set(preserve_keys or [])
    existing = read_kv(path)
    merged = dict(existing)
    for key, val in updates.items():
        if key in preserve and key in existing:
            continue
        merged[key] = str(val).strip()

    lines = []
    if header:
        lines.extend(header.rstrip().splitlines())
        lines.append("")
    for key in sorted(merged):
        lines.append(f"{key}={merged[key]}")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    os.replace(tmp, path)