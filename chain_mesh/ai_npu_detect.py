"""Wave O — auto-detect Hailo / Coral NPU hardware on Pi edge nodes."""

from __future__ import annotations

import glob
import os
from typing import Any, Dict, List

def _detect_enable() -> bool:
    return os.environ.get("AI_NPU_DETECT_ENABLE", "1").strip().lower() not in (
        "0",
        "false",
        "no",
    )

_HAILO_DEV_PATTERNS = (
    "/dev/hailo0",
    "/dev/hailo",
    "/dev/hailo_chardev",
)
_CORAL_DEV_PATTERNS = (
    "/dev/apex_0",
    "/dev/apex_1",
    "/dev/apex_2",
    "/dev/apex_3",
)


def _device_exists(path: str) -> bool:
    return bool(path) and os.path.exists(path)


def _matching_devices(patterns: tuple) -> List[str]:
    found: List[str] = []
    for pattern in patterns:
        if "*" in pattern:
            found.extend(sorted(glob.glob(pattern)))
        elif _device_exists(pattern):
            found.append(pattern)
    return found


def detect_npu_hardware() -> Dict[str, Any]:
    if not _detect_enable():
        return {
            "ok": True,
            "enabled": False,
            "devices": [],
            "hardware": {},
            "runtimes": [],
        }

    hailo = _matching_devices(_HAILO_DEV_PATTERNS)
    coral = _matching_devices(_CORAL_DEV_PATTERNS)
    devices = hailo + coral
    hardware: Dict[str, Any] = {"kind": "cpu"}
    runtimes: List[str] = []

    if hailo:
        hardware = {"kind": "hailo", "devices": hailo}
        runtimes.extend(["onnx", "cpu-inference"])
    if coral:
        hardware = {"kind": "coral", "devices": coral} if not hailo else {
            "kind": "hybrid",
            "hailo": hailo,
            "coral": coral,
        }
        if "tflite" not in runtimes:
            runtimes.append("tflite")
        if "cpu-inference" not in runtimes:
            runtimes.append("cpu-inference")

    env_runtimes = [
        r.strip().lower()
        for r in (os.environ.get("AI_LOCAL_RUNTIMES") or "").split(",")
        if r.strip()
    ]
    for rt in env_runtimes:
        if rt not in runtimes:
            runtimes.append(rt)

    return {
        "ok": True,
        "enabled": True,
        "devices": devices,
        "hardware": hardware,
        "runtimes": runtimes,
        "hailo_devices": hailo,
        "coral_devices": coral,
    }


def suggested_flops_per_sec(hardware: Dict[str, Any]) -> int:
    kind = str(hardware.get("kind") or "").lower()
    if kind in ("hailo", "hybrid"):
        return int(os.environ.get("AI_HAILO_FLOPS_PER_SEC", "2000000000"))
    if kind == "coral":
        return int(os.environ.get("AI_CORAL_FLOPS_PER_SEC", "1500000000"))
    return int(os.environ.get("AI_FLOPS_PER_SEC", "500000000"))