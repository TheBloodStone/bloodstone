"""Curated systemd units for the mining admin restart panel."""

from __future__ import annotations

import subprocess
from typing import Dict, List, Optional

# Whitelist only — prevents arbitrary systemctl targets from the admin UI.
SERVICE_UNITS: Dict[str, str] = {
    "stratum-neoscrypt": "bloodstone-stratum-neoscrypt.service",
    "stratum-yespower": "bloodstone-stratum-yespower.service",
    "stratum-sha256": "bloodstone-stratum-sha256.service",
    "stratum-rod-neoscrypt": "bloodstone-stratum-rod-neoscrypt.service",
    "stratum-ws": "bloodstone-stratum-ws.service",
    "miner-web": "bloodstone-miner-web.service",
    "neoscrypt-pool-miner": "bloodstone-neoscrypt-pool-miner.service",
    "yespower-miner": "bloodstone-yespower-miner.service",
    "bloodstoned": "bloodstoned.service",
    "spacexpansed": "spacexpansed.service",
    "electrumx": "bloodstone-electrumx.service",
    "portal": "bloodstone-portal.service",
    "wallet-web": "bloodstone-wallet-web.service",
    "explorer": "bloodstone-explorer.service",
    "faucet": "bloodstone-faucet.service",
    "dex": "bloodstone-dex.service",
    "support": "bloodstone-support.service",
}

SERVICE_SECTIONS: List[Dict] = [
    {
        "id": "mining",
        "title": "Mining & stratum",
        "description": "Browser miner WebSocket bridge, stratum servers, and pool CPU miners.",
        "services": [
            "stratum-ws",
            "stratum-neoscrypt",
            "stratum-yespower",
            "stratum-sha256",
            "stratum-rod-neoscrypt",
            "miner-web",
            "neoscrypt-pool-miner",
            "yespower-miner",
        ],
    },
    {
        "id": "nodes",
        "title": "Blockchain nodes",
        "description": "Full nodes and ElectrumX for STONE and ROD.",
        "services": [
            "bloodstoned",
            "spacexpansed",
            "electrumx",
        ],
    },
    {
        "id": "portal",
        "title": "Portal & web apps",
        "description": "Public site, wallet, explorer, faucet, and support.",
        "services": [
            "portal",
            "wallet-web",
            "explorer",
            "faucet",
            "dex",
            "support",
        ],
    },
]

SERVICE_LABELS: Dict[str, str] = {
    "stratum-neoscrypt": "Neoscrypt stratum",
    "stratum-yespower": "Yespower stratum",
    "stratum-sha256": "SHA256d stratum",
    "stratum-rod-neoscrypt": "ROD neoscrypt stratum",
    "stratum-ws": "Stratum WebSocket bridge",
    "miner-web": "Mining dashboard (this app)",
    "neoscrypt-pool-miner": "Neoscrypt pool CPU miner",
    "yespower-miner": "Yespower pool CPU miner",
    "bloodstoned": "Bloodstone node (STONE)",
    "spacexpansed": "SpaceXpanse ROD node",
    "electrumx": "ElectrumX (STONE)",
    "portal": "Bloodstone portal",
    "wallet-web": "Web wallet",
    "explorer": "Block explorer",
    "faucet": "Faucet",
    "dex": "GleecDEX page",
    "support": "Support tickets",
}

RESTART_GROUPS: Dict[str, Dict] = {
    "all-stratum": {
        "label": "Restart all stratum pools",
        "services": [
            "stratum-neoscrypt",
            "stratum-yespower",
            "stratum-sha256",
            "stratum-rod-neoscrypt",
        ],
    },
    "mining-stack": {
        "label": "Restart mining stack",
        "description": "All stratum pools, WebSocket bridge, and mining dashboard.",
        "services": [
            "stratum-neoscrypt",
            "stratum-yespower",
            "stratum-sha256",
            "stratum-rod-neoscrypt",
            "stratum-ws",
            "miner-web",
        ],
    },
    "browser-mining": {
        "label": "Fix browser miner",
        "description": "Neoscrypt + yespower stratum, WebSocket bridge, and mining dashboard.",
        "services": [
            "stratum-neoscrypt",
            "stratum-yespower",
            "stratum-ws",
            "miner-web",
        ],
    },
}


def _unit_for(service_id: str) -> Optional[str]:
    return SERVICE_UNITS.get(service_id)


def service_status(unit: str) -> str:
    try:
        out = subprocess.check_output(
            ["systemctl", "is-active", unit],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        return out or "unknown"
    except subprocess.CalledProcessError as exc:
        return (exc.output or "").strip() or "inactive"
    except FileNotFoundError:
        return "unavailable"


def restart_unit(unit: str) -> None:
    if not unit.endswith(".service"):
        raise ValueError("invalid unit name")
    subprocess.run(
        ["systemctl", "restart", unit],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        timeout=120,
    )


def restart_service(service_id: str) -> str:
    unit = _unit_for(service_id)
    if not unit:
        raise ValueError(f"unknown service: {service_id}")
    restart_unit(unit)
    return unit


def restart_group(group_id: str) -> List[str]:
    group = RESTART_GROUPS.get(group_id)
    if not group:
        raise ValueError(f"unknown group: {group_id}")
    restarted = []
    for service_id in group["services"]:
        unit = restart_service(service_id)
        restarted.append(unit)
    return restarted


def admin_service_sections() -> List[Dict]:
    sections = []
    for section in SERVICE_SECTIONS:
        items = []
        for service_id in section["services"]:
            unit = _unit_for(service_id)
            if not unit:
                continue
            status = service_status(unit)
            items.append(
                {
                    "id": service_id,
                    "label": SERVICE_LABELS.get(service_id, service_id),
                    "unit": unit,
                    "status": status,
                    "healthy": status == "active",
                }
            )
        sections.append(
            {
                "id": section["id"],
                "title": section["title"],
                "description": section.get("description", ""),
                "services": items,
            }
        )
    return sections


def admin_restart_groups() -> List[Dict]:
    return [
        {
            "id": group_id,
            "label": meta["label"],
            "description": meta.get("description", ""),
        }
        for group_id, meta in RESTART_GROUPS.items()
    ]